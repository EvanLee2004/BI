import { friendlyError } from '../utils/friendlyError'
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchBuVm, fetchCockpitVm } from '../api/client'
import type { PageVM, RankViewBlk } from '../types/vm'

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

  async function loadArchive(day: string) {
    loading.value = true
    error.value = ''
    archiveMode.value = true
    archiveDay.value = day
    snapshotMode.value = false
    snapshotPack.value = null
    try {
      const r = await fetch(`/api/history/${day}/vm`, { credentials: 'same-origin' })
      if (r.status === 401) {
        error.value = '未登录'
        return
      }
      if (!r.ok) {
        const d = await r.json().catch(() => ({}))
        throw new Error((d as { detail?: string }).detail || `HTTP ${r.status}`)
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
      error.value = friendlyError(e)
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
    loading.value = true
    error.value = ''
    try {
      const data = await fetchCockpitVm()
      vm.value = data
      scope.value = 'main'
      buName.value = ''
      applyNavFromVm(data)
      const keys = data.period_keys || []
      period.value = data.year_key || keys[0] || ''
    } catch (e) {
      error.value = friendlyError(e)
    } finally {
      loading.value = false
    }
  }

  async function loadBu(name: string) {
    // 2.2.9 快照：从 pack.bu[name] 取，禁止 API
    if (snapshotMode.value && snapshotPack.value) {
      const buMap = (snapshotPack.value.bu || {}) as Record<string, PageVM>
      const data = buMap[name]
      if (!data) {
        error.value = `快照中无业务线「${name}」`
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
    loading.value = true
    error.value = ''
    buName.value = name
    try {
      const data = await fetchBuVm(name)
      vm.value = data
      scope.value = 'bu'
      applyNavFromVm(data)
      const keys = data.period_keys || []
      period.value = data.year_key || keys[0] || ''
    } catch (e) {
      error.value = friendlyError(e)
    } finally {
      loading.value = false
    }
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
    loadMain,
    loadBu,
    loadArchive,
    loadSnapshot,
    tryBootSnapshot,
    snapshotCanGoOverall,
    setPeriod,
    setDaily,
    clearDaily,
  }
})
