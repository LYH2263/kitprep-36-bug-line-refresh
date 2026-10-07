<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const tree = ref<any[]>([])
const data = ref<any>(null)
const shortages = ref<any[]>([])
const orders = ref<any[]>([])
const notice = ref('')
async function run() {
  // 只有点这个按钮才按当前订单行现算并落新快照
  data.value = await api('/prep/run?order_id=1', { method: 'POST' })
  shortages.value = data.value.shortages || []
  notice.value = ''
}
async function loadSnapshot() {
  // 只读已落下的快照；没有就空着，绝不自动重算
  try {
    data.value = await api('/prep/latest?order_id=1')
    shortages.value = data.value.shortages || []
  } catch {
    data.value = null
    shortages.value = []
    notice.value = '尚未生成备料单，点击「生成备料单」按当前订单行现算。'
  }
}
onMounted(async () => {
  tree.value = await api('/bom/tree')
  orders.value = await api('/orders')
  await loadSnapshot()
})
</script>
<template>
  <h1>备料工作台</h1>
  <p class="sub">左 BOM 树 · 中备料表 · 右缺料便利贴 · 顶栏订单芯片</p>
  <div class="kp-chips" style="margin-bottom:0.75rem" v-if="orders.length">
    <span v-for="o in orders" :key="o.id" class="kp-chip" style="cursor:default">
      {{ o.code }} · {{ o.outlet }}
    </span>
  </div>
  <button class="btn" @click="run">生成备料单</button>
  <span v-if="notice" class="muted" style="margin-left:0.6rem;font-size:0.8rem">{{ notice }}</span>
  <div class="kp-workbench" style="margin-top:0.85rem">
    <aside class="kp-bom-tree">
      <h2>菜品 / BOM</h2>
      <div v-for="d in tree" :key="d.code" class="kp-dish-node">
        <strong>{{ d.dish }}</strong>
        <span style="font-size:0.7rem;color:#8a8078">{{ d.code }}</span>
        <ul>
          <li v-for="(c,i) in d.children" :key="i">{{ c.ingredient }} · {{ c.qty }} {{ c.unit }}</li>
        </ul>
      </div>
    </aside>
    <section class="kp-worksheet" v-if="data">
      <h2>备料单 · {{ data.order?.code }} · {{ data.order?.outlet }}</h2>
      <table>
        <thead><tr><th>原料</th><th>需求</th><th>库存</th><th>单位</th></tr></thead>
        <tbody>
          <tr v-for="l in data.prep_lines" :key="l.ingredient_id">
            <td>{{ l.ingredient_name }}</td><td>{{ l.need_qty }}</td><td>{{ l.stock_qty }}</td><td>{{ l.unit }}</td>
          </tr>
        </tbody>
      </table>
    </section>
    <section class="kp-worksheet" v-else>
      <h2>备料单</h2>
      <p class="muted" style="font-size:0.85rem">暂无快照。订单加行不会改动这里，点「生成备料单」才按当前订单行现算。</p>
    </section>
    <aside class="kp-shortage-sticky">
      <h2>⚠ 缺料便利贴</h2>
      <div v-for="r in shortages" :key="r.ingredient_id" class="kp-shortage-item">
        <span>{{ r.ingredient_name }}</span>
        <span class="kp-qty">−{{ r.shortage }} {{ r.unit }}</span>
      </div>
      <p v-if="!shortages.length" style="font-size:0.8rem;margin:0.5rem 0 0">暂无缺料</p>
    </aside>
  </div>
</template>
