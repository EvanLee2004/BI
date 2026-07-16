<script setup lang="ts">
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
const store = useCockpitStore()
const keys = computed(() => (store.vm?.period_keys as string[]) || [])
</script>
<template>
  <select
    class="toggle"
    :value="store.period"
    @change="store.setPeriod(($event.target as HTMLSelectElement).value)"
  >
    <option v-for="k in keys" :key="k" :value="k">{{ k }}</option>
  </select>
</template>
