<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  open: boolean
  title?: string
  tag?: string
}>()
const emit = defineEmits<{ close: [] }>()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) emit('close')
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="data-modal-mask"
      data-testid="data-modal"
      @click.self="emit('close')"
    >
      <div class="data-modal" role="dialog" aria-modal="true">
        <div class="data-modal__h">
          <b>{{ title }}</b>
          <span v-if="tag" class="tag" data-testid="data-modal-tag">{{ tag }}</span>
          <button type="button" class="ghost mini" @click="emit('close')">关闭</button>
        </div>
        <div class="data-modal__body">
          <slot />
        </div>
      </div>
    </div>
  </Teleport>
</template>
