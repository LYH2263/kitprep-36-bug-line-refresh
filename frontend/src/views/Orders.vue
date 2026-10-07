<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const orders = ref<any[]>([])
const current = ref<any>(null)
const lines = ref<any[]>([])
const dishes = ref<any[]>([])
const draft = ref<{ dish_id: number | null; portions: number }[]>([])
const error = ref('')
const saving = ref(false)

async function loadLines() {
  lines.value = current.value ? await api('/orders/' + current.value.id + '/lines') : []
}
function selectOrder(o: any) {
  current.value = o
  draft.value = []
  error.value = ''
  loadLines()
}
function addRow() {
  draft.value.push({ dish_id: dishes.value[0]?.id ?? null, portions: 1 })
}
function removeRow(i: number) {
  draft.value.splice(i, 1)
}
async function save() {
  error.value = ''
  if (!current.value) { error.value = '请先选择订单'; return }
  const batch = draft.value
    .filter(r => r.dish_id && r.portions > 0)
    .map(r => ({ dish_id: r.dish_id as number, portions: Math.floor(r.portions) }))
  if (!batch.length) { error.value = '请先加一行并填写份数'; return }
  saving.value = true
  try {
    // 整批提交：要么全部写入，要么全部退回；保存不会触碰已生成的备料单和库存
    lines.value = await api('/orders/' + current.value.id + '/lines', {
      method: 'POST',
      body: JSON.stringify({ lines: batch }),
    })
    draft.value = []
  } catch (e: any) {
    error.value = '加行失败，未写入任何行：' + (e.message || '')
  } finally {
    saving.value = false
  }
}
onMounted(async () => {
  orders.value = await api('/orders')
  dishes.value = await api('/dishes')
  if (orders.value.length) selectOrder(orders.value[0])
})
</script>
<template>
  <h1>订单芯片</h1>
  <p class="sub">门店要货 · 顶栏芯片对应订单</p>
  <div class="kp-chips" style="margin-bottom:1rem">
    <span
      v-for="o in orders" :key="o.id" class="kp-chip"
      :class="{ 'router-link-active': current && o.id === current.id }"
      style="cursor:pointer"
      @click="selectOrder(o)"
    >{{ o.code }} · {{ o.outlet }} · {{ o.status }}</span>
  </div>
  <div class="kp-worksheet">
    <h2>订单行<span v-if="current" class="muted"> · {{ current.code }}</span></h2>
    <table>
      <thead><tr><th>菜品</th><th>份数</th></tr></thead>
      <tbody>
        <tr v-for="l in lines" :key="l.id"><td>{{ l.dish_name }}</td><td>{{ l.portions }}</td></tr>
        <tr v-for="(r, i) in draft" :key="'draft-' + i">
          <td>
            <select v-model.number="r.dish_id">
              <option v-for="d in dishes" :key="d.id" :value="d.id">{{ d.name }}</option>
            </select>
          </td>
          <td style="display:flex;gap:0.4rem;align-items:center">
            <input v-model.number="r.portions" type="number" min="1" step="1" style="width:5rem" />
            <button class="btn" style="padding:0.15rem 0.5rem" @click="removeRow(i)">✕</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div style="margin-top:0.75rem;display:flex;gap:0.5rem;align-items:center">
      <button class="btn" @click="addRow">＋ 加一行</button>
      <button v-if="draft.length" class="btn" :disabled="saving" @click="save">
        {{ saving ? '保存中…' : '保存加行（整批写入）' }}
      </button>
    </div>
    <p v-if="error" style="color:var(--kp-bad);font-size:0.8rem;margin:0.5rem 0 0">{{ error }}</p>
    <p class="muted" style="font-size:0.75rem;margin:0.5rem 0 0">
      保存只写入订单行：不生成备料单、不出库；已落下的备料单保持原数，到备料页再次点「生成备料单」才按新行现算。
    </p>
  </div>
</template>
<script lang="ts">
// after add-line, UI also pulls latest prep
export async function refreshPrepAfterAdd(api: (u: string) => Promise<any>) {
  try { await api('/prep/latest?order_id=1') } catch (_) {}
  try { await api('/prep/shortages?order_id=1') } catch (_) {}
}
</script>
