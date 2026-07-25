<script setup lang="ts">
/**
 * 2.6.4·D1：切 BU 过场 —— 甲骨易 logo + BU 名淡入淡出。
 * - 总时长由 store.transitionToBu 控制（≤800ms）
 * - 点击任意处 / Escape 可跳过
 * - prefers-reduced-motion 时 store 不置 viewTransitioning，本层不出现
 */
import { onMounted, onBeforeUnmount } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import logoUrl from '../assets/logo.png'

const store = useCockpitStore()

function skip() {
  store.skipViewTransition()
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' || e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    skip()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div
    v-if="store.viewTransitioning"
    class="bu-xfade"
    role="dialog"
    aria-label="切换业务线"
    data-testid="bu-transition-overlay"
    @click="skip"
  >
    <div class="bu-xfade-inner">
      <img class="bu-xfade-logo" :src="logoUrl" alt="甲骨易" width="120" height="120" />
      <div class="bu-xfade-name" data-testid="bu-transition-label">{{ store.transitionLabel || '…' }}</div>
      <div class="bu-xfade-hint">点击任意处跳过</div>
    </div>
  </div>
</template>

<style scoped>
.bu-xfade {
  position: fixed;
  inset: 0;
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--bg, #01030a) 82%, transparent);
  backdrop-filter: blur(4px);
  cursor: pointer;
  animation: bu-xfade-in 0.12s ease-out;
}
.bu-xfade-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  pointer-events: none;
}
.bu-xfade-logo {
  width: 120px;
  height: 120px;
  object-fit: contain;
  filter: drop-shadow(0 0 18px rgba(47, 243, 255, 0.4));
  animation: bu-xfade-logo 0.35s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.bu-xfade-name {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--ink, #eef4ff);
  animation: bu-xfade-title 0.28s ease 0.08s both;
}
.bu-xfade-hint {
  font-size: 12px;
  color: var(--mut, #94a3b8);
  opacity: 0.85;
}
@keyframes bu-xfade-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
@keyframes bu-xfade-logo {
  from {
    opacity: 0;
    transform: scale(0.88);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
@keyframes bu-xfade-title {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@media (prefers-reduced-motion: reduce) {
  .bu-xfade {
    display: none;
  }
}
@media (max-width: 520px) {
  .bu-xfade-logo {
    width: 88px;
    height: 88px;
  }
  .bu-xfade-name {
    font-size: 18px;
  }
}
</style>
