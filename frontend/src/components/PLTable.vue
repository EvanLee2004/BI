<script setup lang="ts">
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
const store = useCockpitStore()
const html = computed(() => {
  const pl = store.vm?.pl as { body_by_period?: Record<string, string>; pl_tag?: string } | undefined
  return pl?.body_by_period?.[store.period] || ''
})
</script>
<template>
  <div class="card pl-card" v-html="html"></div>
</template>
