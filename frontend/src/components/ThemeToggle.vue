<script setup lang="ts">
import { themeMode, toggleTheme } from '../utils/theme'

function onToggle() {
  toggleTheme({ source: 'ThemeToggle' })
}
</script>
<template>
  <button type="button" class="toggle dsdk-button" style="width: auto; padding: 6px 13px" @click="onToggle">
    {{ themeMode === 'light' ? '◐ 深色' : '◑ 浅色' }}
  </button>
</template>
