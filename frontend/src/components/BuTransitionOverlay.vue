<script setup lang="ts">
/**
 * 2.6.5·C：切 BU 过场 —— logo 放大 + 「正在计算 XX BU 数据……」+ 扫描线
 * - 1s（store.transitionToBu wait 1000）
 * - 点击任意处 / Escape 可跳过
 * - prefers-reduced-motion：store 不置 viewTransitioning，本层不出现
 */
import '../styles/components/BuTransitionOverlay.css'
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import logoUrl from '../assets/logo.png'

const store = useCockpitStore()

const message = computed(() => {
  const name = (store.transitionLabel || '').trim() || '…'
  if (name === '整体') return '正在计算 整体 数据……'
  return `正在计算 ${name} BU 数据……`
})

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
    <div class="bu-xfade-scan" aria-hidden="true" />
    <div class="bu-xfade-inner">
      <img class="bu-xfade-logo" :src="logoUrl" alt="甲骨易" width="160" height="160" />
      <div class="bu-xfade-name" data-testid="bu-transition-label">{{ message }}</div>
      <div class="bu-xfade-hint">点击任意处跳过</div>
    </div>
  </div>
</template>
