import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchBuVm, fetchCockpitVm } from '../api/client'

export const useCockpitStore = defineStore('cockpit', () => {
  const period = ref('')
  const vm = ref<Record<string, unknown> | null>(null)
  const loading = ref(false)
  const error = ref('')
  const scope = ref<'main' | 'bu'>('main')
  const buName = ref('')

  async function loadMain() {
    loading.value = true
    error.value = ''
    try {
      vm.value = await fetchCockpitVm()
      scope.value = 'main'
      const keys = (vm.value.period_keys as string[]) || []
      period.value = (vm.value.year_key as string) || keys[0] || ''
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
      vm.value = await fetchBuVm(name)
      scope.value = 'bu'
      const keys = (vm.value.period_keys as string[]) || []
      period.value = (vm.value.year_key as string) || keys[0] || ''
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  function setPeriod(key: string) {
    period.value = key
  }

  return { period, vm, loading, error, scope, buName, loadMain, loadBu, setPeriod }
})
