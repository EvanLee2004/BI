import { friendlyError } from '../utils/friendlyError'
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchBuVm, fetchCockpitVm } from '../api/client'
import type { PageVM, RankViewBlk } from '../types/vm'

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
  /** 54.11 R-01：有配置但名单空时的可见提示（勿静默） */
  const buNavHint = ref('')
  const buConfigCount = ref(0)
  /** 2.2.7：历史存档只读模式（/?archive=YYYYMMDD） */
  const archiveMode = ref(false)
  const archiveDay = ref('')
  const archiveBuiltAt = ref('')
  const archiveVersion = ref('')

  function applyNavFromVm(data: PageVM) {
    const names = data.bu_names
    buNames.value = Array.isArray(names) ? names : []
    buNavLabel.value = String(data.bu_nav_label || '业务 BU 分页')
    buNavHint.value = String(data.bu_nav_hint || '')
    const n = (data as { bu_config_count?: number }).bu_config_count
    buConfigCount.value = typeof n === 'number' ? n : 0
  }

  async function loadArchive(day: string) {
    loading.value = true
    error.value = ''
    archiveMode.value = true
    archiveDay.value = day
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
        // 允许空结构但至少是对象
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

  async function loadMain() {
    const day = archiveDayFromUrl()
    if (day) {
      await loadArchive(day)
      return
    }
    archiveMode.value = false
    archiveDay.value = ''
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
    if (archiveMode.value) return
    dailyRange.value = { start, end }
    dailyDual.value = dual
    dailyActive.value = !!dual
  }

  function clearDaily() {
    dailyActive.value = false
    dailyDual.value = null
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
    dailyActive,
    dailyRange,
    dailyDual,
    loadMain,
    loadBu,
    loadArchive,
    setPeriod,
    setDaily,
    clearDaily,
  }
})
