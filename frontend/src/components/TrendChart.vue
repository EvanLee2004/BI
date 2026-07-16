<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
const store = useCockpitStore()
const host = ref<HTMLElement | null>(null)
const svgHtml = computed(() => {
  const t = store.vm?.trend as { svg_html?: string } | undefined
  return t?.svg_html || ''
})
// 默认挂后端 SVG；3B 可切 ECharts（数据仍来自 VM）
const useEcharts = ref(false)
</script>
<template>
  <div class="card">
    <div class="card-h">收入 · 毛利趋势</div>
    <div class="rc-body" ref="host" v-html="svgHtml"></div>
  </div>
</template>
