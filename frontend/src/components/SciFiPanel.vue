<script setup lang="ts">
/**
 * SciFi panel shell — kit visual language (dsdk-panel*).
 * Source: Dynamic-SciFi-Dashboard-Kit (MIT), vendored under vendor/scifi-kit/.
 * Data charts stay ECharts; this component is chrome only.
 */
withDefaults(
  defineProps<{
    title?: string
    tag?: string
    state?: 'normal' | 'warning' | 'critical' | 'stable'
    /** extra classes on root (e.g. kpi-card, pl-card) */
    panelClass?: string
    contentClass?: string
    showHeader?: boolean
  }>(),
  {
    title: '',
    tag: '',
    state: 'normal',
    panelClass: '',
    contentClass: '',
    showHeader: true,
  },
)
</script>
<template>
  <div
    class="dsdk-panel scifi-panel"
    :class="[
      `dsdk-panel-${state}`,
      panelClass,
    ]"
  >
    <div v-if="showHeader && (title || $slots.header)" class="dsdk-panel-header">
      <slot name="header">
        <span>{{ title }}</span>
        <span v-if="tag" class="tag">{{ tag }}</span>
      </slot>
    </div>
    <div class="dsdk-panel-content" :class="contentClass">
      <slot />
    </div>
  </div>
</template>
