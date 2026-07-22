<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const frame = ref<HTMLIFrameElement | null>(null)

function reload() {
  try {
    frame.value?.contentWindow?.location.reload()
  } catch {
    if (frame.value) frame.value.src = '/'
  }
}

function onTheme(e: Event) {
  const detail = (e as CustomEvent).detail as { theme?: string }
  const t = detail?.theme
  const theme = t === 'neon' || t === 'dark' || t === 'light' ? t : 'neon'
  try {
    const f = frame.value
    if (f?.contentWindow) {
      f.contentWindow.postMessage({ type: 'cockpit-theme', theme }, location.origin)
    }
  } catch {
    /* ignore */
  }
}

onMounted(() => {
  window.addEventListener('admin-reload-dash', reload)
  window.addEventListener('admin-theme', onTheme)
})
onUnmounted(() => {
  window.removeEventListener('admin-reload-dash', reload)
  window.removeEventListener('admin-theme', onTheme)
})
</script>

<template>
  <div>
    <iframe ref="frame" class="admin-iframe" src="/" title="经营驾驶舱" />
  </div>
</template>
