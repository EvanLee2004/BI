<script setup lang="ts">
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import SciFiPanel from './SciFiPanel.vue'
import CountUpNumber from './CountUpNumber.vue'
import type { KpiCard } from '../types/vm'

const store = useCockpitStore()

const cards = computed((): KpiCard[] => {
  return store.vm?.kpi?.cards_by_period?.[store.period] || []
})
/** 3.6.0：税前利润主卡 + 其余紧凑副卡；BU 进度独立条，不强制五卡等高 */
const hero = computed(() => {
  const list = cards.value
  return (
    list.find((c) => /税前|利润/.test(String(c.label || ''))) ||
    list[0] ||
    null
  )
})
const secondary = computed(() => {
  const h = hero.value
  return cards.value.filter((c) => c !== h)
})
const buProgress = computed(() => {
  for (const c of cards.value) {
    if (c.bu_orders?.length) return c.bu_orders
  }
  return [] as NonNullable<KpiCard['bu_orders']>
})
/** 周期变化时触发 count-up 重播 */
const playKey = computed(() => store.period)
</script>
<template>
  <div class="kpi-host kpi-host--hero">
    <div v-if="hero" class="kpi-hero">
      <SciFiPanel :tag="hero.period_tag || ''" panel-class="kpi-card kpi-card--hero">
        <template #header>
          <span class="kpi-title-row">
            <span>{{ hero.label }}</span>
            <span v-if="hero.hint" class="kpi-hint">{{ hero.hint }}</span>
          </span>
          <span v-if="hero.period_tag" class="tag">{{ hero.period_tag }}</span>
        </template>
        <div class="kpi-v">
          <CountUpNumber
            :value="Number(hero.value) || 0"
            :value-disp="String(hero.value_disp ?? '')"
            :play-key="playKey"
          />
          <span class="kpi-u">{{ hero.value_unit || '万' }}</span>
          <span v-if="hero.delta?.show" class="kpi-delta" :class="hero.delta.cls">{{ hero.delta.text }}</span>
        </div>
        <div v-for="(s, j) in hero.subs || []" :key="'hs' + j" class="kpi-sub">
          <span>{{ s.label }}</span><b>{{ s.value_disp }}</b>
        </div>
        <div v-if="hero.target && !hero.target.empty" class="kpi-tgt" :class="hero.target.cls">
          <div class="kpi-tgt-lab">
            <span>{{ hero.target.label }}</span>
            <span v-if="hero.target.kind === 'margin'">{{ hero.target.cur_disp }} / {{ hero.target.tgt_disp }}</span>
            <span v-else>{{ hero.target.done_disp }} / {{ hero.target.tgt_disp }}</span>
            <span class="kpi-tgt-pct">{{ hero.target.pct_disp }}</span>
          </div>
          <div class="kpi-bar"><i :style="{ width: (hero.target.bar_w || 0) + '%' }"></i></div>
        </div>
      </SciFiPanel>
    </div>
    <div class="kpi-secondary">
      <SciFiPanel
        v-for="(c, i) in secondary"
        :key="i"
        :tag="c.period_tag || ''"
        panel-class="kpi-card kpi-card--compact"
      >
        <template #header>
          <span class="kpi-title-row">
            <span>{{ c.label }}</span>
            <span v-if="c.hint" class="kpi-hint">{{ c.hint }}</span>
          </span>
          <span v-if="c.period_tag" class="tag">{{ c.period_tag }}</span>
        </template>
        <div class="kpi-v">
          <CountUpNumber :value="Number(c.value) || 0" :value-disp="String(c.value_disp ?? '')" :play-key="playKey" />
          <span class="kpi-u">{{ c.value_unit || '万' }}</span>
          <span v-if="c.delta?.show" class="kpi-delta" :class="c.delta.cls">{{ c.delta.text }}</span>
        </div>
        <div v-for="(s, j) in c.subs || []" :key="'s' + j" class="kpi-sub">
          <span>{{ s.label }}</span><b>{{ s.value_disp }}</b>
        </div>
        <div v-if="c.target && !c.target.empty" class="kpi-tgt" :class="c.target.cls">
          <div class="kpi-tgt-lab">
            <span>{{ c.target.label }}</span>
            <span v-if="c.target.kind === 'margin'">{{ c.target.cur_disp }} / {{ c.target.tgt_disp }}</span>
            <span v-else>{{ c.target.done_disp }} / {{ c.target.tgt_disp }}</span>
            <span class="kpi-tgt-pct">{{ c.target.pct_disp }}</span>
          </div>
          <div class="kpi-bar"><i :style="{ width: (c.target.bar_w || 0) + '%' }"></i></div>
        </div>
        <div v-else-if="c.target?.empty" class="kpi-tgt empty muted">未设{{ c.target.label }}</div>
        <div v-if="c.feet?.length" class="kpi-foot">
          <div v-for="(f, fi) in c.feet" :key="fi" class="kpi-peak">
            <span>{{ f.kind === 'peak' ? '全年峰值 · ' + f.label : f.label }}</span>
            <b>{{ f.value_disp }}</b>
          </div>
        </div>
      </SciFiPanel>
    </div>
    <div v-if="buProgress.length" class="kpi-bu-strip" data-testid="kpi-bu-progress">
      <div class="kpi-bu-strip__title">BU 下单进度</div>
      <div v-for="(b, k) in buProgress" :key="k" class="kpi-bu-row" :title="b.tip">
        <div class="kpi-bu-h">
          <span>{{ b.name }}</span>
          <span>{{ b.amount_disp }}</span>
          <span class="badge" :class="b.cls">{{ b.badge_disp }}</span>
        </div>
        <div class="kpi-bu-track" :class="b.cls"><i :style="{ width: b.bar_w + '%' }"></i></div>
      </div>
    </div>
  </div>
</template>
