<script setup lang="ts">
/**
 * 任务书46·3B：ECharts 宿主。
 * 铁律2：option 的数据/标签串必须由后端 VM 预计算后传入，前端不做金额运算。
 */
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { kanbanTheme, currentThemeMode } from '../../echarts-theme'

const props = defineProps<{ option: Record<string, unknown> }>()
const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function render() {
  if (!el.value) return
  if (!chart) {
    echarts.registerTheme('kanban', kanbanTheme(currentThemeMode()))
    chart = echarts.init(el.value, 'kanban')
  }
  chart.setOption(props.option || {}, true)
}

onMounted(() => {
  render()
  window.addEventListener('resize', () => chart?.resize())
})
onBeforeUnmount(() => {
  chart?.dispose()
  chart = null
})
watch(() => props.option, render, { deep: true })
</script>
<template>
  <div ref="el" style="width:100%;min-height:280px"></div>
</template>
