<script setup lang="ts">
import '../styles/components/IntroSplash.css'
/**
 * 2.3.1 S1：logo 入场改为「填充加载等待」。
 * - 看端每次刷新都播（不依赖 kanban_intro_pending）
 * - /admin* 与 snapshotMode 不播；reduced-motion 全跳过
 * - 与数据加载并行；min_show=900ms、上限 1600ms；可跳过
 */
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import logoUrl from '../assets/logo.png'
import { prefersReducedMotion } from '../chart-fx'

const props = defineProps<{
  /** 数据是否已加载完成（与 store.loading 反相） */
  dataReady?: boolean
}>()

const visible = ref(false)
const phase = ref<'in' | 'hold' | 'out' | 'done'>('in')
let timers: number[] = []
let done = false
let minShowElapsed = false
let dataReadySeen = false
const startedAt = ref(0)

const emit = defineEmits<{ done: [] }>()

const MIN_SHOW_MS = 900
const MAX_SHOW_MS = 1600

function finish(immediate = false) {
  if (done) return
  done = true
  timers.forEach((t) => clearTimeout(t))
  timers = []
  if (immediate || !visible.value) {
    phase.value = 'done'
    visible.value = false
    emit('done')
    return
  }
  phase.value = 'out'
  /* 淡出后卸掉 */
  timers.push(
    window.setTimeout(() => {
      phase.value = 'done'
      visible.value = false
      emit('done')
    }, 280),
  )
}

function tryFinish() {
  if (done) return
  if (minShowElapsed && dataReadySeen) finish()
}

function skip() {
  finish()
}

function onKey(e: KeyboardEvent) {
  if (e.key) skip()
}

onMounted(() => {
  const path = typeof location !== 'undefined' ? location.pathname : ''
  if (path.startsWith('/admin') || prefersReducedMotion()) {
    finish(true)
    return
  }

  /* 兼容：若登录页仍写 pending，读后清掉（不再作为唯一触发） */
  try {
    sessionStorage.removeItem('kanban_intro_pending')
  } catch {
    /* ignore */
  }

  startedAt.value = performance.now()
  visible.value = true
  phase.value = 'in'
  dataReadySeen = !!props.dataReady

  timers.push(
    window.setTimeout(() => {
      minShowElapsed = true
      tryFinish()
    }, MIN_SHOW_MS),
  )
  timers.push(
    window.setTimeout(() => {
      finish()
    }, MAX_SHOW_MS),
  )

  window.addEventListener('keydown', onKey)
})

watch(
  () => props.dataReady,
  (v) => {
    if (v) {
      dataReadySeen = true
      tryFinish()
    }
  },
)

onBeforeUnmount(() => {
  timers.forEach((t) => clearTimeout(t))
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div
    v-if="visible"
    class="intro-splash"
    :class="['phase-' + phase]"
    role="dialog"
    aria-label="入场动画"
    @click="skip"
  >
    <div class="intro-inner">
      <img class="intro-logo" :src="logoUrl" alt="甲骨易" width="180" height="180" />
      <div class="intro-title">甲骨易 · 经营看板</div>
    </div>
  </div>
</template>

