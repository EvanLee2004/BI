<script setup lang="ts">
/** 期间费用构成：环形用 VM donut 序列；同时保留 body HTML 四态兜底。 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'

const store = useCockpitStore()
const exp = computed(() => (store.vm?.expense || {}) as Record<string, unknown>)
const items = computed(() => {
  const by = (exp.value.donut_by_period as Record<string, { name: string; value: number; value_disp: string; pct_disp: string }[]>) || {}
  return by[store.period] || []
})
const htmlFallback = computed(() => {
  const body = (exp.value.body_by_period as Record<string, string>) || {}
  return body[store.period] || ''
})
const option = computed(() => {
  const data = items.value
  return {
    tooltip: {
      trigger: 'item',
      formatter: (p: { dataIndex: number; name: string }) => {
        const it = data[p.dataIndex]
        return `${p.name}<br/>${it?.value_disp || '—'}万（${it?.pct_disp || '—'}）`
      },
    },
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        data: data.map((d) => ({ name: d.name, value: d.value })),
        label: {
          formatter: (p: { dataIndex: number; name: string }) => {
            const it = data[p.dataIndex]
            return `${p.name}\n${it?.pct_disp || ''}`
          },
        },
        animationType: 'scale',
        animationDuration: 600,
      },
    ],
  }
})
</script>
<template>
  <div class="card" style="margin-top:16px">
    <div class="card-h">期间费用构成 <span class="tag">环形 · ECharts</span></div>
    <div v-if="items.length" class="ev-body">
      <EchartsHost :option="option" />
      <div class="legend" style="display:flex;flex-wrap:wrap;gap:8px 14px;justify-content:center;margin-top:8px">
        <span v-for="it in items" :key="it.name" class="muted" style="font-size:11px">
          {{ it.name }} {{ it.value_disp }}万（{{ it.pct_disp }}）
        </span>
      </div>
    </div>
    <div v-else v-html="htmlFallback"></div>
  </div>
</template>
