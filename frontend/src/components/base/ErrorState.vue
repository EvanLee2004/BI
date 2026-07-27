<script setup lang="ts">
/**
 * 2.6.10 V-5：看端统一错误块 — 人话 + 至少一个出口，禁止裸红字撞墙。
 */
import '../../styles/components/ErrorState.css'

defineProps<{
  title?: string
  message: string
  primaryLabel?: string
  secondaryLabel?: string
}>()

const emit = defineEmits<{
  primary: []
  secondary: []
}>()
</script>

<template>
  <div class="error-state wrap" data-testid="error-state" role="alert">
    <div class="error-state__card">
      <h2 v-if="title" class="error-state__title">{{ title }}</h2>
      <p class="error-state__msg">{{ message }}</p>
      <div class="error-state__actions">
        <button
          v-if="primaryLabel"
          type="button"
          class="error-state__btn error-state__btn--primary"
          data-testid="error-state-primary"
          @click="emit('primary')"
        >
          {{ primaryLabel }}
        </button>
        <button
          v-if="secondaryLabel"
          type="button"
          class="error-state__btn"
          data-testid="error-state-secondary"
          @click="emit('secondary')"
        >
          {{ secondaryLabel }}
        </button>
      </div>
    </div>
  </div>
</template>
