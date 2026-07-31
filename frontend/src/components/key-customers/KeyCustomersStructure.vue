<script setup lang="ts">
/**
 * 3.6.2 双饼六档结构（客户数 + 金额）；点扇区 emit tier 供池联动。
 * 标签/单位均来自 VM *_disp，禁止前端金额运算。
 */
import { computed } from 'vue'
import type { KeyCustomersSeg } from '../../types/vm'
import EchartsHost from '../charts/EchartsHost.vue'
import {
  buildKeyCustomersStructurePieOption,
  structureHasData,
  tierColorAt,
} from '../../charts/keyCustomersStructurePies'
import { themeMode } from '../../utils/theme'

const props = defineProps<{
  structureCount?: { label?: string; segments?: KeyCustomersSeg[] } | null
  structureAmount?: { label?: string; segments?: KeyCustomersSeg[] } | null
  activeTier?: string | null
}>()

const emit = defineEmits<{
  'tier-click': [tierId: string]
}>()

const countSegs = computed(() => props.structureCount?.segments || [])
const amountSegs = computed(() => props.structureAmount?.segments || [])
const hasData = computed(
  () => structureHasData(countSegs.value) || structureHasData(amountSegs.value),
)

const countOption = computed(() => {
  void themeMode.value
  return buildKeyCustomersStructurePieOption({
    kind: 'count',
    label: props.structureCount?.label || '客户数结构',
    segments: countSegs.value,
    activeTier: props.activeTier,
  })
})

const amountOption = computed(() => {
  void themeMode.value
  return buildKeyCustomersStructurePieOption({
    kind: 'amount',
    label: props.structureAmount?.label || '金额结构',
    segments: amountSegs.value,
    activeTier: props.activeTier,
  })
})

function onPieClick(p: { name?: string; dataIndex?: number }) {
  const name = (p.name || '').trim()
  if (name) {
    emit('tier-click', name)
    return
  }
  const i = p.dataIndex
  if (i != null && countSegs.value[i]) {
    emit('tier-click', String(countSegs.value[i].id || countSegs.value[i].label || ''))
  }
}

const legendSegs = computed(() => countSegs.value.length ? countSegs.value : amountSegs.value)
</script>

<template>
  <section
    class="kc-structure-pies"
    data-testid="kc-structure-pies"
    aria-label="六档结构双饼"
  >
    <div v-if="!hasData" class="kc-structure-empty" data-testid="kc-structure-empty">
      暂无分级结构数据
    </div>
    <div v-else class="kc-structure-pies__grid">
      <div class="kc-pie-wrap" data-testid="kc-pie-count">
        <EchartsHost class="kc-pie-chart" :option="countOption as any" @click="onPieClick" />
      </div>
      <div class="kc-pie-wrap" data-testid="kc-pie-amount">
        <EchartsHost class="kc-pie-chart" :option="amountOption as any" @click="onPieClick" />
      </div>
    </div>
    <ul v-if="hasData" class="kc-bar-legend" aria-label="档位图例">
      <li
        v-for="(seg, i) in legendSegs"
        :key="'lg' + seg.id"
        class="kc-legend-item"
        :class="{ 'is-active': activeTier && String(seg.id).toUpperCase() === String(activeTier).toUpperCase() }"
        :data-tier="seg.id"
        role="button"
        tabindex="0"
        @click="emit('tier-click', String(seg.id || ''))"
        @keydown.enter.prevent="emit('tier-click', String(seg.id || ''))"
      >
        <span
          class="kc-pie-dot"
          :data-i="i"
          :data-tier="seg.id"
          :style="{ background: tierColorAt(i) }"
        />
        <span>{{ seg.label }}</span>
      </li>
    </ul>
  </section>
</template>
