<script setup lang="ts">
import { computed } from 'vue'
import { themeMode, toggleTheme, themeToggleLabel } from '../utils/theme'

function onToggle() {
  toggleTheme({ source: 'ThemeToggle' })
}

const label = computed(() => themeToggleLabel(themeMode.value))
</script>
<template>
  <button type="button" class="toggle dsdk-button" style="width: auto; padding: 6px 13px" @click="onToggle">
    {{ label }}
  </button>
</template>
