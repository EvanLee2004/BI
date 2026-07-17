<script setup lang="ts">
function toggle() {
  const root = document.documentElement
  const on = root.classList.toggle('theme-light')
  try {
    localStorage.setItem('cockpit-theme', on ? 'light' : 'dark')
  } catch (e) {}
  // 通知 ECharts 宿主按 kit CSS 变量重注册主题
  window.dispatchEvent(new CustomEvent('kanban-theme-change', { detail: { light: on } }))
}
</script>
<template>
  <button type="button" class="toggle dsdk-button" style="width: auto; padding: 6px 13px" @click="toggle">
    亮/暗
  </button>
</template>
