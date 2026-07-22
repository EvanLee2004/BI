<script setup lang="ts">
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
      <div class="intro-title">甲骨易 · 智能经营罗盘</div>
    </div>
  </div>
</template>

<style scoped>
.intro-splash {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg, #01030a);
  cursor: pointer;
  transition: opacity 0.28s ease;
}
.intro-splash.phase-out {
  opacity: 0;
  pointer-events: none;
}
.intro-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}
.intro-logo {
  width: 180px;
  height: 180px;
  object-fit: contain;
  transform: scale(0.85);
  opacity: 0;
  filter: drop-shadow(0 0 24px rgba(47, 243, 255, 0.45));
  animation: intro-logo-in 0.55s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}
.intro-title {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--ink, #eef4ff);
  opacity: 0;
  transform: translateY(12px);
  animation: intro-title-in 0.35s ease 0.45s forwards;
}
@keyframes intro-logo-in {
  to {
    opacity: 1;
    transform: scale(1);
  }
}
@keyframes intro-title-in {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@media (prefers-reduced-motion: reduce) {
  .intro-splash {
    display: none;
  }
}
</style>
