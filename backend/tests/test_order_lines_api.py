"""加行验收：整批原子、不偷偷生成备料单、不出库、旧快照冻结到再生成。"""
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.models import Ingredient, OrderLine, PrepRun


def _counts():
    db = SessionLocal()
    try:
        return {
            "order_lines": db.scalar(select(func.count()).select_from(OrderLine)),
            "prep_runs": db.scalar(select(func.count()).select_from(PrepRun)),
        }
    finally:
        db.close()


def _stocks():
    db = SessionLocal()
    try:
        return {i.code: i.stock_qty for i in db.scalars(select(Ingredient)).all()}
    finally:
        db.close()


def _ids(seeded):
    order = seeded.get("/api/orders").json()[0]
    dishes = {d["code"]: d["id"] for d in seeded.get("/api/dishes").json()}
    return order["id"], dishes


def _prep_line(snapshot, ing_id):
    return next(l for l in snapshot["prep_lines"] if l["ingredient_id"] == ing_id)


def test_add_lines_batch_writes_all(seeded):
    oid, dishes = _ids(seeded)
    before = _counts()
    res = seeded.post(f"/api/orders/{oid}/lines", json={"lines": [
        {"dish_id": dishes["D-HS"], "portions": 10},
        {"dish_id": dishes["D-JT"], "portions": 5},
    ]})
    assert res.status_code == 201, res.text
    lines = res.json()
    assert len(lines) == 3 + 2  # 种子 3 行 + 新 2 行，整批写入
    assert _counts()["order_lines"] == before["order_lines"] + 2
    got = {(l["dish_id"], l["portions"]) for l in lines}
    assert (dishes["D-HS"], 10) in got and (dishes["D-JT"], 5) in got
    # 订单页随即能看到新行
    assert len(seeded.get(f"/api/orders/{oid}/lines").json()) == 5


def test_add_lines_does_not_generate_prep_run(seeded):
    oid, dishes = _ids(seeded)
    assert _counts()["prep_runs"] == 0
    res = seeded.post(f"/api/orders/{oid}/lines",
                      json={"lines": [{"dish_id": dishes["D-YC"], "portions": 7}]})
    assert res.status_code == 201
    assert _counts()["prep_runs"] == 0  # 保存行不得偷偷点「生成备料单」
    assert seeded.get("/api/prep/latest", params={"order_id": oid}).status_code == 404


def test_add_lines_does_not_change_stock(seeded):
    oid, dishes = _ids(seeded)
    before = _stocks()
    res = seeded.post(f"/api/orders/{oid}/lines",
                      json={"lines": [{"dish_id": dishes["D-HS"], "portions": 100}]})
    assert res.status_code == 201
    assert _stocks() == before  # 加行不是出库，账面结存不得改小


def test_prep_snapshot_frozen_until_regenerate(seeded):
    oid, dishes = _ids(seeded)
    inv = {i["code"]: i["id"] for i in seeded.get("/api/inventory").json()}
    pr = inv["I-PR"]  # 五花肉：D-HS 每份 0.25kg，库存 8kg

    snap1 = seeded.post("/api/prep/run", params={"order_id": oid}).json()
    assert _prep_line(snap1, pr)["need_qty"] == 10.0   # 40 份 × 0.25
    assert _prep_line(snap1, pr)["shortage"] == 2.0

    res = seeded.post(f"/api/orders/{oid}/lines",
                      json={"lines": [{"dish_id": dishes["D-HS"], "portions": 10}]})
    assert res.status_code == 201

    # 旧单冻结：加行后立刻查，快照和缺料贴仍是加行前的数字
    latest = seeded.get("/api/prep/latest", params={"order_id": oid}).json()
    assert latest["id"] == snap1["id"]
    assert _prep_line(latest, pr)["need_qty"] == 10.0
    assert _prep_line(latest, pr)["shortage"] == 2.0
    short = seeded.get("/api/prep/shortages", params={"order_id": oid}).json()
    assert _prep_line({"prep_lines": short["shortages"]}, pr)["shortage"] == 2.0

    # 再次点「生成备料单」才按新行现算
    snap2 = seeded.post("/api/prep/run", params={"order_id": oid}).json()
    assert snap2["id"] != snap1["id"]
    assert _prep_line(snap2, pr)["need_qty"] == 12.5   # 50 份 × 0.25
    assert _prep_line(snap2, pr)["shortage"] == 4.5
    short2 = seeded.get("/api/prep/shortages", params={"order_id": oid}).json()
    assert _prep_line({"prep_lines": short2["shortages"]}, pr)["shortage"] == 4.5


def test_add_lines_atomic_rollback_on_bad_dish(seeded):
    oid, dishes = _ids(seeded)
    seeded.post("/api/prep/run", params={"order_id": oid})
    before = _counts()
    snap_before = seeded.get("/api/prep/latest", params={"order_id": oid}).json()

    res = seeded.post(f"/api/orders/{oid}/lines", json={"lines": [
        {"dish_id": dishes["D-HS"], "portions": 10},
        {"dish_id": 999999, "portions": 3},
    ]})
    assert res.status_code == 400

    # 整批退回：合法那行也没写入；旧备料单原样
    assert _counts() == before
    assert len(seeded.get(f"/api/orders/{oid}/lines").json()) == 3
    assert seeded.get("/api/prep/latest", params={"order_id": oid}).json() == snap_before


def test_add_lines_validation_and_unknown_order(seeded):
    oid, dishes = _ids(seeded)
    before = _counts()
    assert seeded.post(f"/api/orders/{oid}/lines",
                       json={"lines": [{"dish_id": dishes["D-HS"], "portions": 0}]}).status_code == 422
    assert seeded.post(f"/api/orders/{oid}/lines", json={"lines": []}).status_code == 422
    assert seeded.post("/api/orders/424242/lines",
                       json={"lines": [{"dish_id": dishes["D-HS"], "portions": 1}]}).status_code == 404
    assert _counts() == before


def test_get_endpoints_never_generate_snapshot(seeded):
    oid, _ = _ids(seeded)
    assert seeded.get("/api/prep/latest", params={"order_id": oid}).status_code == 404
    res = seeded.get("/api/prep/shortages", params={"order_id": oid})
    assert res.status_code == 200
    assert res.json()["shortages"] == []
    assert _counts()["prep_runs"] == 0  # GET 只读，不落快照
