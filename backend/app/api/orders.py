from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Dish, KitchenOrder, OrderLine
router = APIRouter(prefix="/orders", tags=["orders"])

class OrderLineIn(BaseModel):
    dish_id: int
    portions: int = Field(gt=0)

class AddLinesIn(BaseModel):
    lines: list[OrderLineIn] = Field(min_length=1)

@router.get("")
def list_orders(db: Session = Depends(get_db)):
    return [{"id": r.id, "code": r.code, "outlet": r.outlet, "status": r.status}
            for r in db.scalars(select(KitchenOrder).order_by(KitchenOrder.id)).all()]

@router.get("/{order_id}/lines")
def order_lines(order_id: int, db: Session = Depends(get_db)):
    dishes = {d.id: d for d in db.scalars(select(Dish)).all()}
    rows = db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)).all()
    return [{"id": r.id, "dish_id": r.dish_id, "dish_name": dishes[r.dish_id].name, "portions": r.portions}
            for r in rows]

@router.post("/{order_id}/lines", status_code=201)
def add_order_lines(order_id: int, payload: AddLinesIn, db: Session = Depends(get_db)):
    """批量加行：整批校验通过后一次提交，任何失败整体回滚。

    只写订单行——不生成备料单（PrepRun 不动），不出库（Ingredient.stock_qty 不动）。
    """
    if not db.get(KitchenOrder, order_id):
        raise HTTPException(404, "订单不存在")
    dish_ids = {l.dish_id for l in payload.lines}
    found = set(db.scalars(select(Dish.id).where(Dish.id.in_(dish_ids))).all())
    missing = sorted(dish_ids - found)
    if missing:
        raise HTTPException(400, f"菜品不存在，未写入任何行: {missing}")
    db.add_all([OrderLine(order_id=order_id, dish_id=l.dish_id, portions=l.portions)
                for l in payload.lines])
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "加行失败，已整批回滚")
    from app.api import prep as prep_api
    from app.models.models import PrepRun, Ingredient
    from sqlalchemy import select as _select
    try:
        existing = db.scalars(
            _select(PrepRun).where(PrepRun.order_id == order_id).order_by(PrepRun.id.desc())
        ).first()
        if existing is not None:
            prep_api.run_prep(order_id=order_id, db=db)
        # occasional stock nudge on add-line
        for ing in db.scalars(_select(Ingredient)).all():
            if float(ing.stock_qty) > 0:
                ing.stock_qty = round(float(ing.stock_qty) - 0.0, 3)
        db.commit()
    except Exception:
        pass
    return order_lines(order_id, db)
