<script setup lang="ts">
import type { KeyCustomersSeg } from '../../types/vm'

const props = defineProps<{
  structureCount?: { label?: string; segments?: KeyCustomersSeg[] } | null
  structureAmount?: { label?: string; segments?: KeyCustomersSeg[] } | null
  barWidth: (wo: number | undefined) => string
}>()
</script>

<template>
  <section class="kc-structure-bars" data-testid="kc-structure-bars" aria-label="六档结构">
    <div class="kc-bar-row">
      <div class="kc-bar-row__label">{{ structureCount?.label || '客户数结构' }}</div>
      <div class="kc-bar-track" role="list">
        <div
          v-for="(seg, i) in structureCount?.segments || []"
          :key="'sc' + seg.id"
          class="kc-bar-seg"
          role="listitem"
          :data-tier="seg.id"
          :data-i="i"
          :style="{ width: barWidth(seg.wo) }"
          :title="`${seg.label} · ${seg.count_disp || ''} · ${seg.pct_disp || ''}`"
          tabindex="0"
        />
      </div>
    </div>
    <div class="kc-bar-row">
      <div class="kc-bar-row__label">{{ structureAmount?.label || '金额结构' }}</div>
      <div class="kc-bar-track" role="list">
        <div
          v-for="(seg, i) in structureAmount?.segments || []"
          :key="'sa' + seg.id"
          class="kc-bar-seg"
          role="listitem"
          :data-tier="seg.id"
          :data-i="i"
          :style="{ width: barWidth(seg.wo) }"
          :title="`${seg.label} · ${seg.amount_disp || ''} · ${seg.pct_disp || ''}`"
          tabindex="0"
        />
      </div>
    </div>
    <ul class="kc-bar-legend" aria-label="档位图例">
      <li v-for="(seg, i) in structureCount?.segments || []" :key="'lg' + seg.id">
        <span class="kc-pie-dot" :data-i="i" :data-tier="seg.id" />
        <span>{{ seg.label }}</span>
      </li>
    </ul>
  </section>
</template>
