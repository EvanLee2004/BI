<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { jget } from '../api'
import { useClientPager } from '../composables/useClientPager'

const router = useRouter()

/* 3.7.2：下单未填部门产品线下线；费用未分类（台账）保留 */
const cards = [
  { key: 'expense_unclassified', label: '费用未分类（台账）', desc: '收单台账没填对应报表大类，暂未计入费用', path: '/admin/review/unclassified' },
  { key: 'adjust_expired', label: '过期疑似调整', desc: '源头已改、我的调整未套用，需拍板听谁的', path: '/admin/review/ledger' },
  { key: 'adjust_missing', label: '调整失配', desc: '调整定位键在源头找不到了（行删了/键变了）', path: '/admin/review/ledger' },
  { key: '__conflict', label: '冲突待确认', desc: '智云改了 vs 这里改了（R4 上线后启用）', disabled: true },
]

const tableRows = computed(() => cards.filter((c) => !c.disabled))
const { page, pages, pageRows, pageInfo, prevPage, nextPage } = useClientPager(tableRows)

const ex = ref<Record<string, number>>({})
const loading = ref(false)
/** 3.7.4：接口失败不得伪装成 0 / 无待处理 */
const loadError = ref('')
const loadedOk = ref(false)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    ex.value = await jget('/api/v1/admin/exceptions')
    loadedOk.value = true
  } catch {
    loadedOk.value = false
    loadError.value = '加载失败，可重试'
    // 保留上次成功数据；首次失败则保持空对象但不渲染为「无待处理」
  } finally {
    loading.value = false
  }
}

function go(c: (typeof cards)[0]) {
  if (c.disabled || !c.path || loadError.value) return
  router.push(c.path)
}

function onCardKey(e: KeyboardEvent, c: (typeof cards)[0]) {
  if (c.disabled || loadError.value) return
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    go(c)
  }
}

function cardCount(key: string): string {
  if (loadError.value && !loadedOk.value) return '—'
  return String(ex.value[key] || 0)
}

function cardStatus(key: string): string {
  if (loadError.value && !loadedOk.value) return '加载失败，可重试'
  const n = ex.value[key] || 0
  return n ? (cards.find((c) => c.key === key)?.desc || '') : '✓ 无待处理'
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="admin-note">分诊台：0=绿=不用管；有数=点卡片进对应清单。处理动作与「数据调整」同一套调整机制。清单页表头带 Excel 式列筛选。</div>
    <div
      v-if="loadError"
      class="ov-error"
      data-testid="exceptions-load-error"
      role="alert"
    >
      <span>{{ loadError }}</span>
      <button type="button" class="ov-retry" data-testid="exceptions-retry" @click="load">
        重试
      </button>
    </div>
    <div class="ov-grid">
      <button
        v-for="c in cards"
        :key="c.key"
        type="button"
        class="ovcard"
        :class="{
          disabled: c.disabled,
          ok: !loadError && !c.disabled && loadedOk && !(ex[c.key] || 0),
          bad: !loadError && !c.disabled && loadedOk && (ex[c.key] || 0) > 0,
          err: !c.disabled && !!loadError && !loadedOk,
        }"
        :disabled="c.disabled"
        :aria-label="c.label"
        @click="go(c)"
        @keydown="onCardKey($event, c)"
      >
        <template v-if="c.disabled">
          <div class="lab">{{ c.label }}</div>
          <div class="muted">{{ c.desc }}</div>
        </template>
        <template v-else>
          <div class="row">
            <span class="n">{{ cardCount(c.key) }}</span>
            <span class="lab">{{ c.label }}</span>
          </div>
          <div class="muted">{{ cardStatus(c.key) }}</div>
        </template>
      </button>
    </div>
    <!-- 任务书61·E2：总览表；2.2.5 统一翻页控件（行数少时恒为 1 页） -->
    <div class="toolbar" style="margin-top: 14px">
      <span class="muted">{{ pageInfo }}</span>
      <el-button size="small" :disabled="page <= 1" @click="prevPage">上一页</el-button>
      <el-button size="small" :disabled="page >= pages" @click="nextPage">下一页</el-button>
    </div>
    <el-table
      class="ov-table"
      :data="pageRows"
      border
      stripe
      size="small"
      style="margin-top: 8px; width: 100%"
    >
      <el-table-column
        prop="label"
        label="异常类型"
        min-width="160"
        :filters="cards.filter((c) => !c.disabled).map((c) => ({ text: c.label, value: c.label }))"
        :filter-method="(v: string, row: (typeof cards)[0]) => row.label === v"
      />
      <el-table-column label="待处理数" width="120">
        <template #default="{ row }">{{
          loadError && !loadedOk ? '—' : ex[row.key] || 0
        }}</template>
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
      闭环：若调整与智云源头不一致，会变「过期疑似」——去「数据修正」选听源头或坚持我的数。
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
  display: block;
  width: 100%;
  text-align: left;
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid var(--admin-line);
  background: var(--admin-panel2);
  cursor: pointer;
  color: inherit;
  font: inherit;
}
.ovcard:focus-visible {
  outline: 2px solid var(--admin-accent);
  outline-offset: 2px;
}
.ovcard.disabled { opacity: 0.45; cursor: default; }
.ovcard.ok { border-color: var(--admin-ok-border); }
.ovcard.bad { border-color: var(--admin-bad-border); }
.ovcard.err { border-color: var(--admin-bad-border); }
.row { display: flex; align-items: center; gap: 8px; }
.n { font-size: 22px; font-weight: 800; color: var(--admin-warn-num); }
.ovcard.ok .n { color: var(--admin-ok-num); }
.lab { font-weight: 700; }
.muted { margin-top: 4px; font-size: 12.5px; color: var(--admin-mut); }
.ov-error {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--admin-bad-border);
  background: var(--admin-panel2);
  color: var(--admin-warn-num);
  font-size: 13px;
  font-weight: 600;
}
.ov-retry {
  margin-left: auto;
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid var(--admin-line);
  background: var(--admin-panel);
  cursor: pointer;
  color: inherit;
  font: inherit;
}
.ov-retry:focus-visible {
  outline: 2px solid var(--admin-accent);
  outline-offset: 2px;
}
</style>
