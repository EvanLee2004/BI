<script setup lang="ts">
import '../../styles/components/Toast.css'
import { onMounted, onUnmounted, ref } from 'vue'
import { onToast, type ToastKind } from '../../utils/toast'

const open = ref(false)
const message = ref('')
const kind = ref<ToastKind>('info')
let timer: ReturnType<typeof setTimeout> | null = null
let unsub: (() => void) | null = null

function clearTimer() {
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
}

function dismiss() {
  clearTimer()
  open.value = false
}

onMounted(() => {
  unsub = onToast((p) => {
    clearTimer()
    message.value = p.message
    kind.value = p.kind || 'info'
    open.value = true
    const ms = p.ms ?? 3200
    timer = setTimeout(() => {
      open.value = false
    }, ms)
  })
})

onUnmounted(() => {
  clearTimer()
  if (unsub) unsub()
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="kb-toast"
      :class="'kb-toast--' + kind"
      role="status"
      data-testid="kb-toast"
      @click="dismiss"
    >
      {{ message }}
    </div>
  </Teleport>
</template>
