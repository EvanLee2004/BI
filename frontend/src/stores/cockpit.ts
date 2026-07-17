import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchBuVm, fetchCockpitVm } from '../api/client'
import type { PageVM, RankViewBlk } from '../types/vm'

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

  function applyNavFromVm(data: PageVM) {
    const names = data.bu_names
    buNames.value = Array.isArray(names) ? names : []
    buNavLabel.value = String(data.bu_nav_label || '业务 BU 分页')
  }

  async function loadMain() {
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
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function loadBu(name: string) {
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
      error.value = e instanceof Error ? e.message : String(e)
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
    dailyActive,
    dailyRange,
    dailyDual,
    loadMain,
    loadBu,
    setPeriod,
    setDaily,
    clearDaily,
  }
})
