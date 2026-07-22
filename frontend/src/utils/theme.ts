/**
 * 2.3.0：三主题枚举 neon | dark | light。
 * ThemeToggle / 管理端切换时写入；图表 option computed 读取 themeMode 以触发重算。
 * light 仍挂 theme-light class（兼容层，既有测试锚点）。
 */
import { ref, type Ref } from 'vue'

export type ThemeMode = 'neon' | 'dark' | 'light'

const THEME_KEY = 'cockpit-theme'
const THEME_V2_KEY = 'cockpit-theme-v2'
const CYCLE: ThemeMode[] = ['neon', 'dark', 'light']

/** 非法/未知值一律回落 neon（2.3.0 新默认）。 */
export function normalizeTheme(v: unknown): ThemeMode {
  if (v === 'neon' || v === 'dark' || v === 'light') return v
  return 'neon'
}

function readDomMode(): ThemeMode {
  if (typeof document === 'undefined') return 'neon'
  const ds = document.documentElement.dataset.theme
  if (ds === 'neon' || ds === 'dark' || ds === 'light') return ds
  return document.documentElement.classList.contains('theme-light') ? 'light' : 'dark'
}

/** 首次 2.3.0 升级强制霓虹；已有 v2 标记则尊重用户选择。 */
export function migrateThemeIfNeeded(): ThemeMode {
  if (typeof localStorage === 'undefined') return readDomMode()
  try {
    const hasV2 = localStorage.getItem(THEME_V2_KEY)
    if (!hasV2) {
      applyTheme('neon', { source: 'migrate-v2' })
      localStorage.setItem(THEME_V2_KEY, '1')
      return 'neon'
    }
    const stored = normalizeTheme(localStorage.getItem(THEME_KEY))
    applyTheme(stored, { source: 'migrate-respect' })
    return stored
  } catch {
    applyTheme('neon', { source: 'migrate-fallback' })
    return 'neon'
  }
}

/** 全局主题 mode（看端+管理端共用逻辑） */
export const themeMode: Ref<ThemeMode> = ref(readDomMode())

/** 应用主题到 document + localStorage + 事件（ECharts 宿主监听 kanban-theme-change）。 */
export function applyTheme(mode: ThemeMode, opts?: { source?: string }): void {
  const m = normalizeTheme(mode)
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = m
    /* 兼容层：仅 light 加 theme-light，neon/dark 移除 */
    document.documentElement.classList.toggle('theme-light', m === 'light')
  }
  try {
    localStorage.setItem(THEME_KEY, m)
  } catch {
    /* ignore */
  }
  themeMode.value = m
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('kanban-theme-change', {
        detail: { theme: m, light: m === 'light', source: opts?.source || 'applyTheme' },
      }),
    )
    window.dispatchEvent(
      new CustomEvent('admin-theme', { detail: { theme: m } }),
    )
  }
}

/** 循环：neon → dark → light → neon */
export function toggleTheme(opts?: { source?: string }): ThemeMode {
  const fromDom = readDomMode()
  const idx = CYCLE.indexOf(fromDom)
  const target: ThemeMode = CYCLE[(idx < 0 ? 0 : idx + 1) % CYCLE.length]
  applyTheme(target, opts)
  return target
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
    if (d.type === 'cockpit-theme') {
      applyTheme(normalizeTheme(d.theme), { source: 'postMessage' })
    }
  }
  const onStorage = (ev: StorageEvent) => {
    if (ev.key !== THEME_KEY) return
    applyTheme(normalizeTheme(ev.newValue), { source: 'storage' })
  }
  window.addEventListener('message', onMsg)
  window.addEventListener('storage', onStorage)
  return () => {
    window.removeEventListener('message', onMsg)
    window.removeEventListener('storage', onStorage)
  }
}

/** 主题钮下一态文案（保留「深色」「浅色」字样供 live 测试定位）。 */
export function themeToggleLabel(mode: ThemeMode = themeMode.value): string {
  const m = normalizeTheme(mode)
  if (m === 'neon') return '◐ 深色'
  if (m === 'dark') return '◑ 浅色'
  return '◈ 霓虹'
}
