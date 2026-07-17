<script setup lang="ts">
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import type { KpiCard } from '../types/vm'

const store = useCockpitStore()

const cards = computed((): KpiCard[] => {
  return store.vm?.kpi?.cards_by_period?.[store.period] || []
})
</script>
<template>
  <div class="kpi-host">
    <div class="kpi-grid">
      <div v-for="(c, i) in cards" :key="i" class="kpi-card">
        <div class="kpi-h">
          <span class="kpi-lab">{{ c.label }}</span>
          <span v-if="c.period_tag" class="kpi-period">{{ c.period_tag }}</span>
        </div>
        <div class="kpi-v">
          <b>{{ c.value_disp }}</b><span class="kpi-u">{{ c.value_unit || '万' }}</span>
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
        <div v-if="c.bu_orders?.length" class="kpi-bus">
          <div v-for="(b, k) in c.bu_orders" :key="k" class="kpi-bu-row" :title="b.tip">
            <div class="kpi-bu-h">
              <span>{{ b.name }}</span>
              <span>{{ b.amount_disp }}</span>
              <span class="badge" :class="b.cls">{{ b.badge_disp }}</span>
            </div>
            <div class="kpi-bu-track" :class="b.cls"><i :style="{ width: b.bar_w + '%' }"></i></div>
          </div>
        </div>
        <div v-if="c.feet?.length" class="kpi-foot">
          <div v-for="(f, fi) in c.feet" :key="fi" class="kpi-peak">
            <span>{{ f.kind === 'peak' ? '全年峰值 · ' + f.label : f.label }}</span>
            <b>{{ f.value_disp }}</b>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
