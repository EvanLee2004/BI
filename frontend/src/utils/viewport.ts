/**
 * 2.6.2：窄屏判定（仅布局/图表 option 分支；不改业务口径）。
 */
import { onMounted, onUnmounted, ref, type Ref } from 'vue'

export function isNarrowViewport(bp = 520): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(`(max-width: ${bp}px)`).matches
}

/** Vue 组件内响应式窄屏；resize 时更新。 */
export function useNarrowViewport(bp = 520): Ref<boolean> {
  const narrow = ref(isNarrowViewport(bp))
  let mql: MediaQueryList | null = null
  const onChange = () => {
    narrow.value = isNarrowViewport(bp)
  }
  onMounted(() => {
    onChange()
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      mql = window.matchMedia(`(max-width: ${bp}px)`)
      if (mql.addEventListener) mql.addEventListener('change', onChange)
      else mql.addListener(onChange)
    }
    window.addEventListener('resize', onChange)
  })
  onUnmounted(() => {
    if (mql) {
      if (mql.removeEventListener) mql.removeEventListener('change', onChange)
      else mql.removeListener(onChange)
    }
    if (typeof window !== 'undefined') window.removeEventListener('resize', onChange)
  })
  return narrow
}
