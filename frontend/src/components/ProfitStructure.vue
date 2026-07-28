<script setup lang="ts">
/** 板块三：收入与毛利结构 — 取数 + 组装 RankList（Layer 3 无自写样式） */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import SciFiPanel from './SciFiPanel.vue'
import RankList from './base/RankList.vue'
import type { ProfitRankPeriod, RankItem, RankSide } from '../types/vm'
import type { RankListItem } from './base/RankList.vue'

const store = useCockpitStore()

const pack = computed((): ProfitRankPeriod | null => {
  return store.vm?.rankings?.profit_rank_by_period?.[store.period] || null
})

const COST_META_LABEL = '系统成本率'
const COST_META_TITLE = '系统成本率 = 项目成本 ÷ 交付收入'

function toListItems(side: RankSide | undefined): RankListItem[] {
  return (side?.items || []).map((it) => ({
    i: it.i,
    name: it.name,
    bar_w: it.bar_w,
    revenue_disp: it.revenue_disp,
    cost_pct_disp: it.cost_pct_disp,
  }))
}

function fetchFull(side: RankSide) {
  return async (): Promise<RankListItem[]> => {
    const local = side.full_items || []
    if (local.length) {
      return local.map((it, idx) => ({
        i: it.i ?? idx + 1,
        name: it.name,
        bar_w: it.bar_w,
        revenue_disp: it.revenue_disp,
        cost_pct_disp: it.cost_pct_disp,
      }))
    }
    const dim = side.dim === 'customer' ? 'customer' : 'sales'
    const start = pack.value?.start || ''
    const end = pack.value?.end || ''
    const buQ =
      store.scope === 'bu' && store.buName
        ? `&bu=${encodeURIComponent(store.buName)}`
        : ''
    // 2.7.0：收入毛利榜走 v1；旧 /api/v1/rankings/profit 仍兼容同实现
    const r = await fetch(
      `/api/v1/rankings/profit?dim=${encodeURIComponent(dim)}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&top=5000${buQ}`,
      { credentials: 'same-origin' },
    )
    if (!r.ok) {
      console.warn('[rankings/profit]', r.status)
      throw new Error('加载排名失败')
    }
    const d = (await r.json()) as { items?: RankItem[] }
    return (d.items || []).map((it, idx) => ({
      i: it.i ?? idx + 1,
      name: it.name,
      revenue_disp: it.revenue_disp,
      cost_pct_disp: it.cost_pct_disp,
      bar_w: it.bar_w,
    }))
  }
}
</script>
<template>
  <div>
    <div
      v-if="pack"
      id="profitRankViews"
      class="pr-grid grid-2e"
      :data-start="pack.start"
      :data-end="pack.end"
    >
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
        <RankList
          :items="toListItems(side)"
          :empty="!side || side.empty"
          :others="side?.others || null"
          :full-items="side?.full_items || []"
          :fetch-full="side ? fetchFull(side) : undefined"
          :modal-title="(side?.title || '') + ' · 完整排名'"
          :show-meta="side?.show_meta !== false"
          :meta-label="side?.show_meta !== false ? COST_META_LABEL : undefined"
          :meta-title="COST_META_TITLE"
        />
      </SciFiPanel>
    </div>
    <div class="pr-formula">
      <span class="pr-f-h">计算逻辑</span>
      <span class="pr-f-item"><b>交付金额</b> = 智云含税原数</span>
      <span class="pr-f-item"><b>交付收入</b> = 交付金额 ÷ 1.06</span>
      <span class="pr-f-item"><b>系统成本率</b> = 项目成本 ÷ 交付收入</span>
      <span class="pr-f-item"><b>集中度</b> = 前5大交付收入 ÷ 期内总交付收入</span>
    </div>
  </div>
</template>
