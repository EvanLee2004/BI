<script setup lang="ts">
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
const store = useCockpitStore()
const html = computed(() => (store.vm?.daily_html as string) || '')
</script>
<template>
  <div v-html="html"></div>
</template>
