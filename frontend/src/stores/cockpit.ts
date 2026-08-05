import { friendlyError, friendlyFromStatus } from '../utils/friendlyError'
import {
  buPathFromSession,
  isOverallForbiddenError,
  navigateToBuPath,
  type SessionLike,
} from '../utils/buEntryRedirect'
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ApiError, fetchBuVm, fetchCockpitVm, fetchSession } from '../api/client'
import { createGenerationGate } from '../utils/fetchRace'
import type { PageVM, RankViewBlk } from '../types/vm'

/** 3.7.14 AUDIT-010：主数据拉取世代闸 — 周期/BU 切换 abort 上一代并丢弃过期写回 */
const vmLoadGate = createGenerationGate()

function isAuthRequired(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401
}

function isAbortError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false
  const name = (err as { name?: string }).name
  if (name === 'AbortError') return true
  // DOMException / fetch abort
  const msg = String((err as { message?: string }).message || '')
  return /abort/i.test(msg)
}

/** 2.2.9 导出快照包（与后端 assemble_export_pack 对齐） */
export type KanbanSnapshotPack = {
  kind?: string
  schema?: number
  exported_at?: string
  built_at?: string
  version?: string
  default_period?: string
  scope?: string
  bu_export_name?: string
  cockpit?: PageVM | Record<string, unknown>
  bu?: Record<string, PageVM | Record<string, unknown>>
}

function archiveDayFromUrl(): string {
  try {
    const q = new URLSearchParams(location.search)
    const d = (q.get('archive') || '').trim()
    if (/^\d{8}$/.test(d)) return d
  } catch {
    /* ignore */
  }
  return ''
}

function readEmbeddedSnapshot(): KanbanSnapshotPack | null {
  try {
    const w = window as unknown as { __KANBAN_SNAPSHOT__?: KanbanSnapshotPack }
    const pack = w.__KANBAN_SNAPSHOT__
    if (pack && typeof pack === 'object' && (pack.kind === 'kanban_snapshot' || pack.cockpit || pack.bu)) {
      return pack
    }
  } catch {
    /* ignore */
  }
  try {
    const el = document.getElementById('kanban-snapshot-data')
    if (el && el.textContent) {
      const pack = JSON.parse(el.textContent) as KanbanSnapshotPack
      if (pack && typeof pack === 'object') return pack
    }
  } catch {
    /* ignore */
  }
  return null
}

export const useCockpitStore = defineStore('cockpit', () => {
  const period = ref('')
  const vm = ref<PageVM | null>(null)
  const loading = ref(false)
  const error = ref('')
  /** 2.6.10 V-5：HTTP 401 → 登录页（按状态码，不靠中文 detail） */
  const authRequired = ref(false)
  /** 最近错误 HTTP 状态（0=未知/网络），供错误块选出口 */
  const errorStatus = ref(0)
  const scope = ref<'main' | 'bu'>('main')
  const buName = ref('')
  /**
   * 按时间段查询（B-01）：查询激活时排名双卡「原位」切换为区间结果，
   * 回款情况总图不消失不挪窝、版面不跳动；返回默认（年）一键恢复。
   * 对齐 legacy 老前端实录行为——只有排名卡换，其余各卡各安其位。
   */
  const dailyActive = ref(false)
  const dailyRange = ref<{ start: string; end: string }>({ start: '', end: '' })
  const dailyDual = ref<{ sales?: RankViewBlk; customer?: RankViewBlk } | null>(null)
  /** 业务 BU 分页名单（整体页=全部已发布 BU；BU 页=本账号可见） */
  const buNames = ref<string[]>([])
  const buNavLabel = ref('业务 BU 分页')
  const buNavHint = ref('')
  const buConfigCount = ref(0)
  /** 2.2.7：历史存档只读模式（/?archive=YYYYMMDD） */
  const archiveMode = ref(false)
  const archiveDay = ref('')
  const archiveBuiltAt = ref('')
  const archiveVersion = ref('')
  /** 2.2.9：导出静态快照只读（内嵌 pack，零 API） */
  const snapshotMode = ref(false)
  const snapshotPack = ref<KanbanSnapshotPack | null>(null)
  const snapshotExportedAt = ref('')
  const snapshotBuiltAt = ref('')
  const snapshotVersion = ref('')
  const snapshotScopeLabel = ref('')
  /** 2.3.1 S6：切 BU 视觉转场标志（不改数据装配） */
  const viewTransitioning = ref(false)
  /** 2.6.4·D1：过场展示的目标 BU 名 */
  const transitionLabel = ref('')
  /** 2.6.4·D1：用户点跳过 */
  const transitionSkipped = ref(false)

  function applyNavFromVm(data: PageVM) {
    const names = data.bu_names
    buNames.value = Array.isArray(names) ? names : []
    buNavLabel.value = String(data.bu_nav_label || '业务 BU 分页')
    buNavHint.value = String(data.bu_nav_hint || '')
    const n = (data as { bu_config_count?: number }).bu_config_count
    buConfigCount.value = typeof n === 'number' ? n : 0
  }

  function applyPeriodFromVm(data: PageVM, preferred?: string) {
    const keys = data.period_keys || []
    if (preferred && keys.includes(preferred)) {
      period.value = preferred
    } else {
      period.value = data.year_key || keys[0] || preferred || ''
    }
  }

  function loadSnapshot(pack: KanbanSnapshotPack) {
    loading.value = true
    error.value = ''
    snapshotMode.value = true
    archiveMode.value = false
    archiveDay.value = ''
    snapshotPack.value = pack
    snapshotExportedAt.value = String(pack.exported_at || '')
    snapshotBuiltAt.value = String(pack.built_at || pack.exported_at || '')
    snapshotVersion.value = String(pack.version || '')
    /* 2.3.0：快照初始主题 = pack.theme；保留切换钮（localStorage 可再改） */
    try {
      const raw = (pack as { theme?: string }).theme
      const t = raw === 'neon' || raw === 'dark' || raw === 'light' ? raw : 'neon'
      document.documentElement.dataset.theme = t
      document.documentElement.classList.toggle('theme-light', t === 'light')
      localStorage.setItem('cockpit-theme', t)
      localStorage.setItem('cockpit-theme-v2', '1')
      window.dispatchEvent(
        new CustomEvent('kanban-theme-change', { detail: { theme: t, light: t === 'light', source: 'snapshot' } }),
      )
    } catch {
      /* ignore */
    }
    const scopeRaw = String(pack.scope || '整体')
    const buExport = String(pack.bu_export_name || '')
    snapshotScopeLabel.value = scopeRaw === 'BU' && buExport ? `BU·${buExport}` : scopeRaw || '整体'
    try {
      const buMap = (pack.bu || {}) as Record<string, PageVM>
      const buKeys = Object.keys(buMap)
      const defaultPeriod = String(pack.default_period || '')
      if (scopeRaw === 'BU' && buExport && buMap[buExport]) {
        const data = buMap[buExport] as PageVM
        vm.value = data
        scope.value = 'bu'
        buName.value = buExport
        applyNavFromVm({
          ...data,
          bu_names: buKeys.length ? buKeys : data.bu_names || [buExport],
        } as PageVM)
        if (!buNames.value.length) buNames.value = [buExport]
        applyPeriodFromVm(data, defaultPeriod)
      } else {
        const data = (pack.cockpit || {}) as PageVM
        if (!data || (!data.period_keys && !Object.keys(data).length)) {
          // 允许仅有 bu 的包？整体包应有 cockpit
          if (!buKeys.length) {
            throw new Error('快照包无 cockpit / bu 数据')
          }
        }
        vm.value = data as PageVM
        scope.value = 'main'
        buName.value = ''
        // 整体包：BuNav 名单 = pack.bu 全部键（优先）
        const navNames = buKeys.length
          ? buKeys
          : Array.isArray(data.bu_names)
            ? data.bu_names
            : []
        applyNavFromVm({ ...data, bu_names: navNames } as PageVM)
        buNames.value = navNames
        applyPeriodFromVm(data as PageVM, defaultPeriod)
      }
      clearDaily()
    } catch (e) {
      error.value = friendlyError(e)
    } finally {
      loading.value = false
    }
  }

  function noteError(e: unknown) {
    if (isAuthRequired(e)) {
      authRequired.value = true
      errorStatus.value = 401
      error.value = friendlyFromStatus(401)
      return
    }
    authRequired.value = false
    if (e instanceof ApiError) {
      errorStatus.value = e.status
      error.value = friendlyError(e)
      return
    }
    errorStatus.value = 0
    error.value = friendlyError(e)
  }

  async function loadArchive(day: string) {
    loading.value = true
    error.value = ''
    authRequired.value = false
    errorStatus.value = 0
    archiveMode.value = true
    archiveDay.value = day
    snapshotMode.value = false
    snapshotPack.value = null
    try {
      const r = await fetch(`/api/v1/history/${day}/vm`, { credentials: 'same-origin' })
      if (r.status === 401) {
        authRequired.value = true
        errorStatus.value = 401
        error.value = friendlyFromStatus(401)
        return
      }
      if (!r.ok) {
        const d = await r.json().catch(() => ({}))
        const detail = (d as { detail?: string }).detail || ''
        if (detail) console.warn('[history]', r.status, detail)
        throw new ApiError(r.status, friendlyFromStatus(r.status))
      }
      const pack = (await r.json()) as {
        cockpit?: PageVM
        bu?: Record<string, PageVM>
        built_at?: string
        version?: string
        day?: string
      }
      const data = (pack.cockpit || {}) as PageVM
      if (!data || !(data as { period_keys?: string[] }).period_keys) {
        if (!Object.keys(data).length) {
          throw new Error('该日存档无 cockpit 数据')
        }
      }
      vm.value = data
      scope.value = 'main'
      buName.value = ''
      applyNavFromVm(data)
      const keys = data.period_keys || []
      period.value = data.year_key || keys[0] || ''
      archiveBuiltAt.value = String(pack.built_at || '')
      archiveVersion.value = String(pack.version || '')
      clearDaily()
    } catch (e) {
      noteError(e)
    } finally {
      loading.value = false
    }
  }

  /** 2.2.9：快照是否允许切到整体（BU 专用包 scope=BU 或 cockpit 空 → 否） */
  function snapshotCanGoOverall(): boolean {
    if (!snapshotMode.value || !snapshotPack.value) return true
    const pack = snapshotPack.value
    if (String(pack.scope || '') === 'BU') return false
    const c = (pack.cockpit || {}) as PageVM
    if (!c || typeof c !== 'object') return false
    if (Object.keys(c).length === 0) return false
    const keys = c.period_keys || []
    // 有 period_keys / year_key 才算可用整体页，避免空壳 KPI
    if (keys.length || c.year_key) return true
    return false
  }

  async function loadMain() {
    // 2.2.9：内嵌快照优先（零 API）
    if (snapshotMode.value && snapshotPack.value) {
      const pack = snapshotPack.value
      // BU 专用包 / 空 cockpit：禁止跳到空整体壳
      if (!snapshotCanGoOverall()) {
        return
      }
      const data = (pack.cockpit || {}) as PageVM
      vm.value = data
      scope.value = 'main'
      buName.value = ''
      const buMap = (pack.bu || {}) as Record<string, PageVM>
      const navNames = Object.keys(buMap)
      applyNavFromVm({ ...data, bu_names: navNames.length ? navNames : data.bu_names } as PageVM)
      if (navNames.length) buNames.value = navNames
      applyPeriodFromVm(data, period.value || String(pack.default_period || ''))
      clearDaily()
      return
    }
    const embedded = readEmbeddedSnapshot()
    if (embedded && !archiveDayFromUrl()) {
      loadSnapshot(embedded)
      return
    }
    const day = archiveDayFromUrl()
    if (day) {
      await loadArchive(day)
      return
    }
    archiveMode.value = false
    archiveDay.value = ''
    snapshotMode.value = false
    const gen = vmLoadGate.next()
    loading.value = true
    error.value = ''
    authRequired.value = false
    errorStatus.value = 0
    try {
      const data = await fetchCockpitVm({ signal: gen.signal })
      if (vmLoadGate.isStale(gen.id)) return
      vm.value = data
      scope.value = 'main'
      buName.value = ''
      applyNavFromVm(data)
      const keys = data.period_keys || []
      period.value = data.year_key || keys[0] || ''
    } catch (e) {
      if (vmLoadGate.isStale(gen.id)) return
      if (isAbortError(e)) return
      if (isAuthRequired(e)) {
        noteError(e)
        return
      }
      // 2.4.3：整体 cockpit 403「无整体…」→ 回流本账号业务线，禁止永久空壳
      if (isOverallForbiddenError(e) || (e instanceof ApiError && e.status === 403)) {
        try {
          const sess = (await fetchSession()) as SessionLike
          if (vmLoadGate.isStale(gen.id)) return
          const dest = buPathFromSession(sess)
          if (dest) {
            navigateToBuPath(dest)
            return
          }
        } catch (se) {
          if (vmLoadGate.isStale(gen.id)) return
          if (isAuthRequired(se)) {
            noteError(se)
            return
          }
          /* fall through to friendly error */
        }
      }
      noteError(e)
    } finally {
      if (!vmLoadGate.isStale(gen.id)) loading.value = false
    }
  }

  async function loadBu(name: string) {
    // 2.2.9 快照：从 pack.bu[name] 取，禁止 API
    if (snapshotMode.value && snapshotPack.value) {
      const buMap = (snapshotPack.value.bu || {}) as Record<string, PageVM>
      const data = buMap[name]
      if (!data) {
        vm.value = null
        errorStatus.value = 404
        error.value = '没有找到这个页面'
        loading.value = false
        return
      }
      loading.value = true
      error.value = ''
      try {
        vm.value = data as PageVM
        scope.value = 'bu'
        buName.value = name
        applyNavFromVm({
          ...(data as PageVM),
          bu_names: Object.keys(buMap),
        } as PageVM)
        buNames.value = Object.keys(buMap)
        applyPeriodFromVm(data as PageVM, period.value || String(snapshotPack.value.default_period || ''))
        clearDaily()
      } finally {
        loading.value = false
      }
      return
    }
    // 历史存档模式不进 BU 实时接口（防写回当前库语义混乱）
    if (archiveDayFromUrl() || archiveMode.value) {
      await loadArchive(archiveDay.value || archiveDayFromUrl())
      return
    }
    const gen = vmLoadGate.next()
    loading.value = true
    error.value = ''
    authRequired.value = false
    errorStatus.value = 0
    // 记住目标名；失败时勿保留旧 VM，否则 ErrorState 被成功页挡住
    buName.value = name
    scope.value = 'bu'
    try {
      const data = await fetchBuVm(name, { signal: gen.signal })
      if (vmLoadGate.isStale(gen.id)) return
      vm.value = data
      applyNavFromVm(data)
      const keys = data.period_keys || []
      period.value = data.year_key || keys[0] || ''
    } catch (e) {
      if (vmLoadGate.isStale(gen.id) || isAbortError(e)) return
      vm.value = null
      noteError(e)
    } finally {
      if (!vmLoadGate.isStale(gen.id)) loading.value = false
    }
  }

  /** 错误块「重试」：按当前路由再拉一次 */
  async function retryLoad() {
    error.value = ''
    authRequired.value = false
    errorStatus.value = 0
    if (scope.value === 'bu' && buName.value) {
      await loadBu(buName.value)
    } else {
      await loadMain()
    }
  }

  /**
   * 2.6.5·C：切 BU 过场（明昊指定）。
   * - 1 秒、每次都播；文案「正在计算 XX BU 数据……」
   * - 可跳过；prefers-reduced-motion 零动画
   * - 过场期间 KPI count-up 被抑制（CountUpNumber 读 viewTransitioning），结束后不连播
   */
  async function transitionToBu(name: string) {
    if (!name || name === buName.value) return
    let reduced = false
    try {
      reduced =
        typeof window !== 'undefined' &&
        !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    } catch {
      reduced = false
    }
    transitionSkipped.value = false
    transitionLabel.value = name
    if (!reduced) viewTransitioning.value = true
    const wait = (ms: number) =>
      new Promise<void>((resolve) => {
        const t0 = Date.now()
        const tick = () => {
          if (transitionSkipped.value || Date.now() - t0 >= ms) {
            resolve()
            return
          }
          setTimeout(tick, 16)
        }
        setTimeout(tick, Math.min(16, ms))
      })
    try {
      // 先开过场再拉数：仪式感 1s（跳过则立即结束等待）
      const loadP = loadBu(name)
      if (!reduced && !transitionSkipped.value) await wait(1000)
      await loadP
      if (typeof history !== 'undefined' && !snapshotMode.value) {
        try {
          history.pushState({}, '', '/bu/' + encodeURIComponent(name))
        } catch {
          /* ignore */
        }
      }
    } finally {
      viewTransitioning.value = false
      transitionLabel.value = ''
      transitionSkipped.value = false
    }
  }

  /** 2.6.5·D：回整体（与切 BU 同套过场，label=整体） */
  async function transitionToMain() {
    if (scope.value === 'main' && !buName.value) return
    let reduced = false
    try {
      reduced =
        typeof window !== 'undefined' &&
        !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    } catch {
      reduced = false
    }
    transitionSkipped.value = false
    transitionLabel.value = '整体'
    if (!reduced) viewTransitioning.value = true
    const wait = (ms: number) =>
      new Promise<void>((resolve) => {
        const t0 = Date.now()
        const tick = () => {
          if (transitionSkipped.value || Date.now() - t0 >= ms) {
            resolve()
            return
          }
          setTimeout(tick, 16)
        }
        setTimeout(tick, Math.min(16, ms))
      })
    try {
      const loadP = loadMain()
      if (!reduced && !transitionSkipped.value) await wait(1000)
      await loadP
      if (typeof history !== 'undefined' && !snapshotMode.value) {
        try {
          history.pushState({}, '', '/')
        } catch {
          /* ignore */
        }
      }
    } finally {
      viewTransitioning.value = false
      transitionLabel.value = ''
      transitionSkipped.value = false
    }
  }

  function skipViewTransition() {
    transitionSkipped.value = true
    viewTransitioning.value = false
  }

  function setPeriod(key: string) {
    period.value = key
    // 切顶部周期即回默认排名态（区间查询是临时叠加，周期一变就撤销），与 legacy 一致
    clearDaily()
  }

  function setDaily(start: string, end: string, dual: { sales?: RankViewBlk; customer?: RankViewBlk } | null) {
    if (archiveMode.value || snapshotMode.value) return
    dailyRange.value = { start, end }
    dailyDual.value = dual
    dailyActive.value = !!dual
  }

  function clearDaily() {
    dailyActive.value = false
    dailyDual.value = null
  }

  /** 启动探测：若页内嵌了快照包则进入 snapshotMode */
  function tryBootSnapshot(): boolean {
    const pack = readEmbeddedSnapshot()
    if (!pack) return false
    loadSnapshot(pack)
    return true
  }

  return {
    period,
    vm,
    loading,
    error,
    authRequired,
    errorStatus,
    scope,
    buName,
    buNames,
    buNavLabel,
    buNavHint,
    buConfigCount,
    archiveMode,
    archiveDay,
    archiveBuiltAt,
    archiveVersion,
    snapshotMode,
    snapshotPack,
    snapshotExportedAt,
    snapshotBuiltAt,
    snapshotVersion,
    snapshotScopeLabel,
    dailyActive,
    dailyRange,
    dailyDual,
    viewTransitioning,
    transitionLabel,
    skipViewTransition,
    loadMain,
    loadBu,
    retryLoad,
    transitionToBu,
    transitionToMain,
    loadArchive,
    loadSnapshot,
    tryBootSnapshot,
    snapshotCanGoOverall,
    setPeriod,
    setDaily,
    clearDaily,
  }
})
