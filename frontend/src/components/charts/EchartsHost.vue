<script setup lang="ts">
/**
 * ECharts 宿主。
 * 铁律2：option 的数据/标签串必须由后端 VM 预计算后传入，前端不做金额运算。
 */
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { kanbanTheme, currentThemeMode } from '../../echarts-theme'

const props = defineProps<{ option: Record<string, unknown> }>()
const emit = defineEmits<{ click: [params: { dataIndex?: number; seriesName?: string; name?: string }] }>()
const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function render() {
  if (!el.value) return
  if (!chart) {
    echarts.registerTheme('kanban', kanbanTheme(currentThemeMode()))
    chart = echarts.init(el.value, 'kanban')
    chart.on('click', (p) => {
      emit('click', {
        dataIndex: typeof p.dataIndex === 'number' ? p.dataIndex : undefined,
        seriesName: p.seriesName,
        name: typeof p.name === 'string' ? p.name : undefined,
      })
    })
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
  <div ref="el" style="width: 100%; min-height: 280px; height: 100%"></div>
</template>
