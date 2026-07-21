<script setup lang="ts">
/**
 * ECharts 宿主。
 * 铁律2：option 的数据/标签串必须由后端 VM 预计算后传入，前端不做金额运算。
 * 任务书54：主题从 kit CSS 变量派生；亮暗切换后重注册并 dispose 重绘。
 * 任务书54.1·V8：ResizeObserver 调 chart.resize()（修先大窗后缩窗横向溢出）。
 * 任务书54.4·A：默认 animation:false；IntersectionObserver 视口懒挂载；renderer 灰度 SVG。
 */
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { kanbanTheme, currentThemeMode } from '../../echarts-theme'

/**
 * A4：多实例/点数远 <1k 时官方推荐 SVG。
 * 若视觉退化可改回 'canvas'（记录待拍板）。
 * 当前默认 svg；用 sessionStorage 可覆盖：kanban_echarts_renderer=canvas|svg
 */
function resolveRenderer(): 'canvas' | 'svg' {
  try {
    const v = sessionStorage.getItem('kanban_echarts_renderer')
    if (v === 'canvas' || v === 'svg') return v
  } catch {
    /* ignore */
  }
  return 'svg'
}

const props = defineProps<{ option: Record<string, unknown> }>()
const emit = defineEmits<{ click: [params: { dataIndex?: number; seriesName?: string; name?: string }] }>()
const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let lastMode: 'dark' | 'light' | null = null
let ro: ResizeObserver | null = null
let io: IntersectionObserver | null = null
/** 是否曾进入视口（懒挂载） */
let inView = false
let pendingRender = false

function ensureChart() {
  if (!el.value || !inView) return
  const mode = currentThemeMode()
  if (chart && lastMode === mode) return
  if (chart) {
    chart.dispose()
    chart = null
  }
  echarts.registerTheme('kanban', kanbanTheme(mode))
  chart = echarts.init(el.value, 'kanban', { renderer: resolveRenderer() })
  lastMode = mode
  chart.on('click', (p) => {
    emit('click', {
      dataIndex: typeof p.dataIndex === 'number' ? p.dataIndex : undefined,
      seriesName: p.seriesName,
      name: typeof p.name === 'string' ? p.name : undefined,
    })
  })
}

function disposeChart() {
  if (ro && el.value) {
    try {
      ro.unobserve(el.value)
    } catch {
      /* ignore */
    }
  }
  chart?.dispose()
  chart = null
  lastMode = null
}

function render() {
  if (!inView) {
    pendingRender = true
    return
  }
  pendingRender = false
  ensureChart()
  if (!chart) return
  /* 强制零动画覆盖（A1）；option 内 animBlock 已关，双保险 */
  const opt = {
    ...(props.option || {}),
    animation: false,
    animationDuration: 0,
    animationDurationUpdate: 0,
  }
  chart.setOption(opt, true)
}

function onTheme() {
  lastMode = null
  if (inView) render()
}

function onWinResize() {
  chart?.resize()
}

/** rAF 合并 resize，降低 reflow 时 Chrome ResizeObserver loop 噪声 */
let roRaf = 0
function setupResizeObserver() {
  if (typeof ResizeObserver === 'undefined' || !el.value) return
  if (!ro) {
    ro = new ResizeObserver(() => {
      if (roRaf) cancelAnimationFrame(roRaf)
      roRaf = requestAnimationFrame(() => {
        roRaf = 0
        chart?.resize()
      })
    })
  }
  ro.observe(el.value)
}

onMounted(() => {
  window.addEventListener('resize', onWinResize)
  window.addEventListener('kanban-theme-change', onTheme)

  /* A5：视口懒挂载 — 进屏才 init，出屏 dispose 降同时存活实例 */
  if (typeof IntersectionObserver !== 'undefined' && el.value) {
    io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            inView = true
            render()
            setupResizeObserver()
          } else if (inView && chart) {
            /* 出屏 dispose，释放 canvas/svg 资源 */
            inView = false
            disposeChart()
          }
        }
      },
      { root: null, rootMargin: '80px 0px', threshold: 0.01 },
    )
    io.observe(el.value)
  } else {
    /* 无 IO 时直接挂载（SSR/旧环境回退） */
    inView = true
    render()
    setupResizeObserver()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onWinResize)
  window.removeEventListener('kanban-theme-change', onTheme)
  if (roRaf) {
    cancelAnimationFrame(roRaf)
    roRaf = 0
  }
  if (io) {
    io.disconnect()
    io = null
  }
  if (ro) {
    ro.disconnect()
    ro = null
  }
  chart?.dispose()
  chart = null
})

watch(
  () => props.option,
  () => {
    if (inView) render()
    else pendingRender = true
  },
  { deep: true },
)
</script>
<template>
  <div ref="el" style="width: 100%; min-height: 280px; height: 100%"></div>
</template>
