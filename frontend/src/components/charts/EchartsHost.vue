<script setup lang="ts">
/**
 * ECharts 宿主。
 * 铁律2：option 的数据/标签串必须由后端 VM 预计算后传入，前端不做金额运算。
 * 任务书54：主题从 kit CSS 变量派生；亮暗切换后重注册并 dispose 重绘。
 */
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { kanbanTheme, currentThemeMode } from '../../echarts-theme'

const props = defineProps<{ option: Record<string, unknown> }>()
const emit = defineEmits<{ click: [params: { dataIndex?: number; seriesName?: string; name?: string }] }>()
const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let lastMode: 'dark' | 'light' | null = null

function ensureChart() {
  if (!el.value) return
  const mode = currentThemeMode()
  if (chart && lastMode === mode) return
  if (chart) {
    chart.dispose()
    chart = null
  }
  echarts.registerTheme('kanban', kanbanTheme(mode))
  chart = echarts.init(el.value, 'kanban')
  lastMode = mode
  chart.on('click', (p) => {
    emit('click', {
      dataIndex: typeof p.dataIndex === 'number' ? p.dataIndex : undefined,
      seriesName: p.seriesName,
      name: typeof p.name === 'string' ? p.name : undefined,
    })
  })
}

function render() {
  ensureChart()
  if (!chart) return
  chart.setOption(props.option || {}, true)
}

function onTheme() {
  lastMode = null
  render()
}

onMounted(() => {
  render()
  window.addEventListener('resize', () => chart?.resize())
  window.addEventListener('kanban-theme-change', onTheme)
})
onBeforeUnmount(() => {
  window.removeEventListener('kanban-theme-change', onTheme)
  chart?.dispose()
  chart = null
})
watch(() => props.option, render, { deep: true })
</script>
<template>
  <div ref="el" style="width: 100%; min-height: 280px; height: 100%"></div>
</template>
