<script setup lang="ts">
/** 板块三：收入与毛利结构 — 真组件 + 其余弹窗 */
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import SciFiPanel from './SciFiPanel.vue'
import type { ProfitRankPeriod, RankItem, RankSide } from '../types/vm'

const store = useCockpitStore()

const pack = computed((): ProfitRankPeriod | null => {
  return store.vm?.rankings?.profit_rank_by_period?.[store.period] || null
})

const modal = ref(false)
const modalTitle = ref('')
const modalItems = ref<RankItem[]>([])
const modalTag = ref('')
const showMeta = ref(true)

/**
 * 2.6.5 A-1：首包 embed_full=False 不下发 full_items → 必须按需拉 /api/profit_ranking。
 * 整体会话无 bu；BU 会话带 bu=本 BU（后端隔离，不可越权）。
 */
async function openOthers(side: RankSide) {
  const title = (side.title || '') + ' · 完整排名'
  modalTitle.value = title
  showMeta.value = side.show_meta !== false
  const local = side.full_items || []
  if (local.length) {
    modalTag.value = ''
    modalItems.value = local
    modal.value = true
    return
  }
  modalTag.value = '加载中…'
  modalItems.value = []
  modal.value = true
  try {
    const dim = side.dim === 'customer' ? 'customer' : 'sales'
    const start = pack.value?.start || ''
    const end = pack.value?.end || ''
    const buQ =
      store.scope === 'bu' && store.buName
        ? `&bu=${encodeURIComponent(store.buName)}`
        : ''
    const r = await fetch(
      `/api/profit_ranking?dim=${encodeURIComponent(dim)}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&top=5000${buQ}`,
      { credentials: 'same-origin' },
    )
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const d = (await r.json()) as { items?: RankItem[] }
    const items = (d.items || []).map((it, idx) => ({
      ...it,
      i: it.i ?? idx + 1,
    }))
    modalTag.value = items.length ? '' : '本期无数据'
    modalItems.value = items
  } catch {
    modalTag.value = '加载失败'
    modalItems.value = []
  }
}
function close() {
  modal.value = false
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>
<template>
  <div>
    <div v-if="pack" id="profitRankViews" class="pr-grid grid-2e" :data-start="pack.start" :data-end="pack.end">
      <SciFiPanel
        v-for="side in [pack.sales, pack.customer]"
        :key="side?.dim"
        :data-dim="side?.dim"
      >
        <template #header>
          <span>{{ side?.title }}</span>
          <span v-if="side?.conc_disp" class="conc">{{ side.conc_disp }}</span>
          <span class="tag">确认口径</span>
        </template>
        <div v-if="!side || side.empty" class="ev-empty">本期无数据</div>
        <div v-else class="ev-list rk-list">
          <div v-for="it in side.items" :key="it.i + it.name" class="ev-row rk-row">
            <span class="rk-no">{{ it.i }}</span>
            <span class="ev-name" :title="it.name">{{ it.name }}</span>
            <span class="ev-track"><i :style="{ width: (it.bar_w || 0) + '%' }"></i></span>
            <span class="ev-amt">{{ it.revenue_disp }}</span>
            <span v-if="side.show_meta !== false && it.margin_disp" class="rk-meta">{{ it.margin_disp }}</span>
          </div>
          <div
            v-if="side.others"
            class="ev-row rk-row rk-others pr-more"
            data-testid="profit-rank-others"
            @click="openOthers(side)"
          >
            <span class="rk-no">…</span>
            <span class="ev-name"
              >其余 {{ side.others.names }} 个 <span class="rk-open">点开展示明细 ›</span></span
            >
            <span class="ev-track"></span>
            <span class="ev-amt">{{ side.others.amt_disp }}</span>
          </div>
        </div>
      </SciFiPanel>
    </div>
    <div class="pr-formula">
      <span class="pr-f-h">计算逻辑</span>
      <span class="pr-f-item"><b>交付金额</b> = 智云含税原数</span>
      <span class="pr-f-item"><b>交付收入</b> = 交付金额 ÷ 1.06</span>
      <span class="pr-f-item"><b>系统成本率</b> = 项目成本 ÷ 交付收入</span>
      <span class="pr-f-item"><b>集中度</b> = 前5大交付收入 ÷ 期内总交付收入</span>
    </div>
    <Teleport to="body">
      <div
        v-if="modal"
        class="rkm-mask"
        style="display: flex"
        data-testid="profit-rank-modal"
        @click.self="close"
      >
        <div class="rkm">
          <div class="rkm-h">
            <b>{{ modalTitle }}</b>
            <span v-if="modalTag" class="tag" data-testid="profit-rank-modal-tag">{{ modalTag }}</span>
            <button type="button" class="ghost mini" @click="close">关闭</button>
          </div>
          <div class="rkm-list">
            <div class="ev-list" data-testid="profit-rank-modal-list">
              <div v-for="it in modalItems" :key="'p' + it.i + it.name" class="ev-row rk-row">
                <span class="rk-no">{{ it.i }}</span>
                <span class="ev-name">{{ it.name }}</span>
                <span class="ev-track"></span>
                <span class="ev-amt">{{ it.revenue_disp }}</span>
                <span v-if="showMeta && it.margin_disp" class="rk-meta">{{ it.margin_disp }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
