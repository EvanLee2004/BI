<script setup lang="ts">
/**
 * 2.3.0 S4.A 登录入场：甲骨易 logo 放大 + 产品名。
 * 触发：sessionStorage kanban_intro_pending=1（登录页提交时写入）。
 * 不阻塞数据加载；可跳过；reduced-motion 全跳过。
 */
import { onMounted, onBeforeUnmount, ref } from 'vue'
import logoUrl from '../assets/logo.png'
import { prefersReducedMotion } from '../chart-fx'

const visible = ref(false)
const phase = ref<'in' | 'hold' | 'out' | 'done'>('in')
let timers: number[] = []
let done = false

const emit = defineEmits<{ done: [] }>()

function finish() {
  if (done) return
  done = true
  phase.value = 'done'
  visible.value = false
  timers.forEach((t) => clearTimeout(t))
  timers = []
  emit('done')
}

function skip() {
  finish()
}

function onKey(e: KeyboardEvent) {
  if (e.key) skip()
}

onMounted(() => {
  let pending = false
  try {
    pending = sessionStorage.getItem('kanban_intro_pending') === '1'
    if (pending) sessionStorage.removeItem('kanban_intro_pending')
  } catch {
    pending = false
  }

  /* 管理端 / 快照 / 无 pending / reduced-motion → 不播 */
  const path = typeof location !== 'undefined' ? location.pathname : ''
  if (path.startsWith('/admin') || !pending || prefersReducedMotion()) {
    finish()
    return
  }

  visible.value = true
  phase.value = 'in'
  /* logo 600ms → 产品名 400ms → 停留 400ms → 淡出 400ms；总 ≤2s */
  timers.push(
    window.setTimeout(() => {
      phase.value = 'hold'
    }, 1000),
  )
  timers.push(
    window.setTimeout(() => {
      phase.value = 'out'
    }, 1400),
  )
  timers.push(
    window.setTimeout(() => {
      finish()
    }, 1800),
  )

  window.addEventListener('keydown', onKey)
})

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
  transition: opacity 0.4s ease;
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
  animation: intro-logo-in 0.6s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}
.intro-title {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--ink, #eef4ff);
  opacity: 0;
  transform: translateY(12px);
  animation: intro-title-in 0.4s ease 0.55s forwards;
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
