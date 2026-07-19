/**
 * 54.14 R-21：响应式主题状态。
 * ThemeToggle / 管理端切换时写入；图表 option computed 读取 themeMode 以触发重算。
 */
import { ref, type Ref } from 'vue'

export type ThemeMode = 'dark' | 'light'

function readDomMode(): ThemeMode {
  if (typeof document === 'undefined') return 'dark'
  return document.documentElement.classList.contains('theme-light') ? 'light' : 'dark'
}

/** 全局主题 mode（看端+管理端共用逻辑） */
export const themeMode: Ref<ThemeMode> = ref(readDomMode())

/** 应用主题到 document + localStorage + 事件（ECharts 宿主监听 kanban-theme-change）。 */
export function applyTheme(mode: ThemeMode, opts?: { source?: string }): void {
  const light = mode === 'light'
  if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('theme-light', light)
  }
  try {
    localStorage.setItem('cockpit-theme', light ? 'light' : 'dark')
  } catch {
    /* ignore */
  }
  themeMode.value = light ? 'light' : 'dark'
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('kanban-theme-change', { detail: { light, source: opts?.source || 'applyTheme' } }),
    )
    window.dispatchEvent(
      new CustomEvent('admin-theme', { detail: { theme: light ? 'light' : 'dark' } }),
    )
  }
}

export function toggleTheme(opts?: { source?: string }): ThemeMode {
  const next: ThemeMode = themeMode.value === 'light' ? 'dark' : 'light'
  // 以 DOM 为准防漂移
  const fromDom = readDomMode()
  const target: ThemeMode = fromDom === 'light' ? 'dark' : 'light'
  applyTheme(target, opts)
  return next
}

export function syncThemeFromDom(): ThemeMode {
  const m = readDomMode()
  themeMode.value = m
  return m
}

/** 安装跨窗口/iframe 主题同步（postMessage + storage）。 */
export function installThemeListeners(): () => void {
  if (typeof window === 'undefined') return () => {}
  syncThemeFromDom()
  const onMsg = (ev: MessageEvent) => {
    const d = ev.data
    if (!d || typeof d !== 'object') return
    if (d.type === 'cockpit-theme' && (d.theme === 'light' || d.theme === 'dark')) {
      applyTheme(d.theme, { source: 'postMessage' })
    }
  }
  const onStorage = (ev: StorageEvent) => {
    if (ev.key !== 'cockpit-theme') return
    applyTheme(ev.newValue === 'light' ? 'light' : 'dark', { source: 'storage' })
  }
  window.addEventListener('message', onMsg)
  window.addEventListener('storage', onStorage)
  return () => {
    window.removeEventListener('message', onMsg)
    window.removeEventListener('storage', onStorage)
  }
}
