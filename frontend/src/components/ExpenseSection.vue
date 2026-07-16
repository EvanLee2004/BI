<script setup lang="ts">
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
const store = useCockpitStore()
const html = computed(() => {
  const e = store.vm?.expense as { body_by_period?: Record<string, string> } | undefined
  return e?.body_by_period?.[store.period] || ''
})
</script>
<template>
  <div style="margin-top:16px" v-html="html"></div>
</template>
