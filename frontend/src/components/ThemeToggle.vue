<script setup lang="ts">
function toggle() {
  const root = document.documentElement
  const on = root.classList.toggle('theme-light')
  try {
    localStorage.setItem('cockpit-theme', on ? 'light' : 'dark')
  } catch (e) {}
}
</script>
<template>
  <button type="button" class="toggle" @click="toggle">亮/暗</button>
</template>
