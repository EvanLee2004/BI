<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { jget } from '../api'

const router = useRouter()

const cards = [
  { key: 'order_unfilled_dept', label: '下单未填部门', desc: '智云源头没填部门，排名灰显待归类', path: '/admin/review/orderdept' },
  { key: 'expense_unclassified', label: '费用未分类（台账）', desc: '收单台账没填对应报表大类，暂未计入费用', path: '/admin/review/unclassified' },
  { key: 'adjust_expired', label: '过期疑似调整', desc: '源头已改、我的调整未套用，需拍板听谁的', path: '/admin/review/ledger' },
  { key: 'adjust_missing', label: '调整失配', desc: '调整定位键在源头找不到了（行删了/键变了）', path: '/admin/review/ledger' },
  { key: '__conflict', label: '冲突待确认', desc: '智云改了 vs 这里改了（R4 上线后启用）', disabled: true },
]

const ex = ref<Record<string, number>>({})
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    ex.value = await jget('/api/exceptions')
  } catch {
    ex.value = {}
  } finally {
    loading.value = false
  }
}

function go(c: (typeof cards)[0]) {
  if (c.disabled || !c.path) return
  router.push(c.path)
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="admin-note">分诊台：0=绿=不用管；有数=点卡片进对应清单。处理动作与「数据调整」同一套调整机制。清单页表头带 Excel 式列筛选。</div>
    <div class="ov-grid">
      <div
        v-for="c in cards"
        :key="c.key"
        class="ovcard"
        :class="{ disabled: c.disabled, ok: !c.disabled && !(ex[c.key] || 0), bad: !c.disabled && (ex[c.key] || 0) > 0 }"
        @click="go(c)"
      >
        <template v-if="c.disabled">
          <div class="lab">{{ c.label }}</div>
          <div class="muted">{{ c.desc }}</div>
        </template>
        <template v-else>
          <div class="row">
            <span class="n">{{ ex[c.key] || 0 }}</span>
            <span class="lab">{{ c.label }}</span>
          </div>
          <div class="muted">{{ (ex[c.key] || 0) ? c.desc : '✓ 无待处理' }}</div>
        </template>
      </div>
    </div>
    <!-- 任务书61·E2：总览表（卡片外补一览表+列筛选；子页 OrderDept/Unclassified/Ledger 已加列筛选） -->
    <el-table
      class="ov-table"
      :data="cards.filter((c) => !c.disabled)"
      border
      stripe
      size="small"
      style="margin-top: 16px; width: 100%"
    >
      <el-table-column
        prop="label"
        label="异常类型"
        min-width="160"
        :filters="cards.filter((c) => !c.disabled).map((c) => ({ text: c.label, value: c.label }))"
        :filter-method="(v: string, row: (typeof cards)[0]) => row.label === v"
      />
      <el-table-column label="待处理数" width="120">
        <template #default="{ row }">{{ ex[row.key] || 0 }}</template>
      </el-table-column>
      <el-table-column
        prop="desc"
        label="说明"
        min-width="240"
        show-overflow-tooltip
      />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="go(row)">进入</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="admin-note" style="margin-top: 14px">
      闭环：在「下单未填部门」归类后，若销售在智云补了部门，会变「过期疑似」——去「数据修正」选听源头或坚持我的数。
    </div>
  </div>
</template>

<style scoped>
.ov-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.ovcard {
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid var(--admin-line, #2a364d);
  background: var(--admin-panel2, #1a2438);
  cursor: pointer;
}
.ovcard.disabled { opacity: 0.45; cursor: default; }
.ovcard.ok { border-color: #14532d; }
.ovcard.bad { border-color: #7c2d12; }
.row { display: flex; align-items: center; gap: 8px; }
.n { font-size: 22px; font-weight: 800; color: #fb923c; }
.ovcard.ok .n { color: #4ade80; }
.lab { font-weight: 700; }
.muted { margin-top: 4px; font-size: 12.5px; color: var(--admin-mut, #94a3b8); }
</style>
