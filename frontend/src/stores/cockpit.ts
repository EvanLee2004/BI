import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchBuVm, fetchCockpitVm } from '../api/client'
import type { PageVM } from '../types/vm'

export const useCockpitStore = defineStore('cockpit', () => {
  const period = ref('')
  const vm = ref<PageVM | null>(null)
  const loading = ref(false)
  const error = ref('')
  const scope = ref<'main' | 'bu'>('main')
  const buName = ref('')
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
    loadMain,
    loadBu,
    setPeriod,
  }
})
