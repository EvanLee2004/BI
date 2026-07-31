/**
 * 重点客户交互状态：fetch/cache/filter/sort/select/compare（3.5.0）
 */
import { computed, reactive, ref, watch, type Ref } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import {
  buildKeyCustomersTrackOption,
  buildTrackTitle,
  type ChartMode,
  type KcMonthPoint,
} from '../charts/keyCustomersChart'
import {
  headerModeLabel,
  itemKey,
  removeCompareState,
  resolveSeriesKeys,
  rowStableKey,
  selectCustomerState,
  toggleCompareState,
} from './keyCustomersSelection'
import {
  KC_POOL_PAGE_SIZE,
  clampPage,
  pageCount,
  pageInfoDisp,
  pageRangeDisp,
  rowIndex1Based,
  slicePage,
} from './keyCustomersPager'
import { structureTierClickIntent } from './keyCustomersTierPool'
import type {
  KeyCustomersItem,
  KeyCustomersMonthPoint,
  KeyCustomersTier,
  KeyCustomersVM,
} from '../types/vm'
import { themeMode } from '../utils/theme'

export type FilterMode = 'all' | 'silent' | 'near'
export type PoolId = 'focus' | 'nurture' | 'longtail'

export function useKeyCustomers() {
  const store = useCockpitStore()

  const kc = computed((): KeyCustomersVM | null => {
    const v = store.vm as { key_customers?: KeyCustomersVM } | null
    return v?.key_customers || null
  })

  const visible = computed(() => {
    const d = kc.value
    if (!d) return false
    if (d.empty && !(d.tiers && d.tiers.length)) return false
    return !!(d.tiers && d.tiers.length)
  })

  const itemsCache = reactive<Record<string, KeyCustomersItem[]>>({})
  const loadErr = reactive<Record<string, string>>({})
  const loadingTier = reactive<Record<string, boolean>>({})
  const monthlyExtra = reactive<Record<string, KeyCustomersMonthPoint[]>>({})
  const selectedKey = ref('')
  const selectedItem = ref<KeyCustomersItem | null>(null)
  const compareKeys = ref<string[]>([])
  const compareHint = ref('')
  const activePool = ref<PoolId>('focus')
  const filterMode = ref<FilterMode>('all')
  const searchQ = ref('')
  /** 3.6.2：点饼高亮当前档（图例/扇区）；切池时保留直至下次点饼或 seed */
  const activeStructureTier = ref('')
  /** 3.6.1：池列表前端分页（pageSize=20）；池/滤/搜变化重置 */
  const listPage = ref(1)
  const chartMode = ref<ChartMode>('amount')
  const monthModal = ref(false)
  const monthTitle = ref('')
  const monthRows = ref<KeyCustomersMonthPoint[]>([])
  let seedGen = 0
  const inflightTier = new Set<string>()

  const COMPARE_MAX = computed(() => {
    const n = Number(kc.value?.compare_max)
    // 3.6.0：桌面默认最多 5 客对比
    return Number.isFinite(n) && n > 0 ? Math.min(5, Math.floor(n)) : 5
  })

  function clearLocalCaches() {
    for (const k of Object.keys(itemsCache)) delete itemsCache[k]
    for (const k of Object.keys(monthlyExtra)) delete monthlyExtra[k]
    for (const k of Object.keys(loadErr)) delete loadErr[k]
    for (const k of Object.keys(loadingTier)) delete loadingTier[k]
    inflightTier.clear()
    selectedKey.value = ''
    selectedItem.value = null
    compareKeys.value = []
    compareHint.value = ''
    filterMode.value = 'all'
    searchQ.value = ''
    listPage.value = 1
    activeStructureTier.value = ''
    chartMode.value = (kc.value?.chart?.default_mode as ChartMode) || 'amount'
    activePool.value = (kc.value?.default_pool as PoolId) || 'focus'
  }

  function monthRowsFor(it: KeyCustomersItem | null): KeyCustomersMonthPoint[] {
    if (!it?.mkey) return []
    return monthlyExtra[it.mkey] || kc.value?.monthly?.[it.mkey] || []
  }

  function findItemByKey(key: string): KeyCustomersItem | null {
    if (!key) return null
    for (const tid of Object.keys(itemsCache)) {
      for (const it of itemsCache[tid] || []) {
        if (itemKey(it) === key) return it
      }
    }
    for (const t of kc.value?.tiers || []) {
      for (const it of t.items || []) {
        if (itemKey(it) === key) return it
      }
    }
    return null
  }

  function selectCustomer(it: KeyCustomersItem | null) {
    compareHint.value = ''
    if (!it) {
      selectedKey.value = ''
      selectedItem.value = null
      return
    }
    const key = itemKey(it)
    const next = selectCustomerState(
      { selectedKey: selectedKey.value, compareKeys: compareKeys.value },
      key,
    )
    selectedKey.value = next.selectedKey
    compareKeys.value = next.compareKeys
    selectedItem.value = it
  }

  async function ensureTierForPool(pool: PoolId, gen?: number) {
    const myGen = gen ?? seedGen
    const poolMeta = (kc.value?.pools || []).find((p) => p.id === pool)
    const tids =
      poolMeta?.tiers ||
      (pool === 'focus' ? ['S', 'A', 'B'] : pool === 'nurture' ? ['C', 'D'] : ['E'])
    const tiers = kc.value?.tiers || []
    for (const tid of tids) {
      const t = tiers.find((x) => x.id === tid)
      if (t) await ensureTier(t, myGen)
    }
  }

  function seedFromVm(d: KeyCustomersVM | null) {
    const gen = ++seedGen
    clearLocalCaches()
    if (!d?.tiers) return
    activePool.value = (d.default_pool as PoolId) || 'focus'
    chartMode.value = (d.chart?.default_mode as ChartMode) || 'amount'
    for (const t of d.tiers) {
      if (!t.lazy) itemsCache[t.id] = t.items || []
    }
    void ensureTierForPool(activePool.value, gen)
  }

  watch(
    () =>
      [
        store.scope,
        store.buName,
        kc.value?.year ?? 0,
        kc.value?.totals?.count ?? 0,
        kc.value?.totals?.amount_disp ?? '',
        store.vm,
      ] as const,
    () => {
      seedFromVm(kc.value)
    },
    { immediate: true },
  )

  async function ensureTier(t: KeyCustomersTier, gen?: number) {
    const myGen = gen ?? seedGen
    if (!t.lazy) {
      if (myGen !== seedGen) return
      itemsCache[t.id] = t.items || []
      return
    }
    if (Object.prototype.hasOwnProperty.call(itemsCache, t.id)) return
    if (inflightTier.has(t.id)) return
    if (store.snapshotMode) {
      if (myGen !== seedGen) return
      itemsCache[t.id] = t.items || []
      if (!itemsCache[t.id].length) loadErr[t.id] = '快照中无该档名单'
      return
    }
    inflightTier.add(t.id)
    loadingTier[t.id] = true
    loadErr[t.id] = ''
    try {
      const buQ =
        store.scope === 'bu' && store.buName
          ? `&bu=${encodeURIComponent(store.buName)}`
          : ''
      const r = await fetch(
        `/api/v1/key-customers/tier?tier=${encodeURIComponent(t.id)}${buQ}`,
        { credentials: 'same-origin' },
      )
      if (myGen !== seedGen) return
      if (!r.ok) {
        loadErr[t.id] =
          r.status === 403
            ? '无权查看该档名单'
            : r.status === 401
              ? '请先登录'
              : '加载该档名单失败'
        return
      }
      const d = (await r.json()) as {
        items?: KeyCustomersItem[]
        monthly?: Record<string, KeyCustomersMonthPoint[]>
        amount_axis?: KeyCustomersVM['amount_axis']
      }
      if (myGen !== seedGen) return
      itemsCache[t.id] = d.items || []
      for (const [k, rows] of Object.entries(d.monthly || {})) {
        monthlyExtra[k] = rows
      }
    } catch {
      if (myGen !== seedGen) return
      loadErr[t.id] = '网络异常，请稍后重试'
    } finally {
      inflightTier.delete(t.id)
      if (myGen === seedGen) loadingTier[t.id] = false
    }
  }

  async function setPool(pid: PoolId) {
    activePool.value = pid
    filterMode.value = 'all'
    listPage.value = 1
    compareHint.value = ''
    await ensureTierForPool(pid)
  }

  /**
   * 3.6.2：点结构饼扇区 → 切对应经营池 + filter=all + ensure 该池 lazy 档。
   * 映射纯函数：structureTierClickIntent / poolForTier。
   */
  async function onStructureTierClick(tierId: string) {
    const intent = structureTierClickIntent(tierId)
    if (!intent) return
    activeStructureTier.value = intent.tier
    filterMode.value = intent.filterMode
    listPage.value = 1
    compareHint.value = ''
    activePool.value = intent.pool
    await ensureTierForPool(intent.pool)
  }

  function setFilter(m: FilterMode) {
    filterMode.value = m
    listPage.value = 1
  }

  function setChartMode(m: ChartMode) {
    chartMode.value = m
  }

  function setSearchQ(v: string) {
    searchQ.value = v
    listPage.value = 1
  }

  const poolTiers = computed((): KeyCustomersTier[] => {
    const poolMeta = (kc.value?.pools || []).find((p) => p.id === activePool.value)
    const tids = new Set(
      poolMeta?.tiers ||
        (activePool.value === 'focus'
          ? ['S', 'A', 'B']
          : activePool.value === 'nurture'
            ? ['C', 'D']
            : ['E']),
    )
    return (kc.value?.tiers || []).filter((t) => tids.has(t.id))
  })

  const poolLoading = computed(() => poolTiers.value.some((t) => loadingTier[t.id]))
  const poolError = computed(() => {
    for (const t of poolTiers.value) {
      if (loadErr[t.id]) return loadErr[t.id]
    }
    return ''
  })

  const poolItemsRaw = computed((): KeyCustomersItem[] => {
    const out: KeyCustomersItem[] = []
    for (const t of poolTiers.value) {
      const items = Object.prototype.hasOwnProperty.call(itemsCache, t.id)
        ? itemsCache[t.id]
        : t.items || []
      for (const it of items) {
        out.push(it.tier ? it : { ...it, tier: t.id })
      }
    }
    return out
  })

  function sortItems(list: KeyCustomersItem[], mode: FilterMode): KeyCustomersItem[] {
    const arr = list.slice()
    if (mode === 'near') {
      arr.sort((a, b) => {
        const ga = a.gap_fen != null ? a.gap_fen : Number.MAX_SAFE_INTEGER
        const gb = b.gap_fen != null ? b.gap_fen : Number.MAX_SAFE_INTEGER
        if (ga !== gb) return ga - gb
        const ya = Number(a.ytd_fen) || 0
        const yb = Number(b.ytd_fen) || 0
        if (yb !== ya) return yb - ya
        return String(a.name || '').localeCompare(String(b.name || ''), 'zh')
      })
      return arr
    }
    arr.sort((a, b) => {
      const ra = a.tier_rank != null ? a.tier_rank : 9
      const rb = b.tier_rank != null ? b.tier_rank : 9
      if (ra !== rb) return ra - rb
      const ya = Number(a.ytd_fen) || 0
      const yb = Number(b.ytd_fen) || 0
      if (yb !== ya) return yb - ya
      return String(a.name || '').localeCompare(String(b.name || ''), 'zh')
    })
    return arr
  }

  const filteredPoolItems = computed((): KeyCustomersItem[] => {
    let list = poolItemsRaw.value
    if (filterMode.value === 'silent') list = list.filter((it) => !!it.silent)
    else if (filterMode.value === 'near') list = list.filter((it) => !!it.near_upgrade)
    const q = searchQ.value.trim().toLowerCase()
    if (q) list = list.filter((it) => String(it.name || '').toLowerCase().includes(q))
    return sortItems(list, filterMode.value)
  })

  const listTotal = computed(() => filteredPoolItems.value.length)
  const listPages = computed(() => pageCount(listTotal.value, KC_POOL_PAGE_SIZE))
  const safeListPage = computed(() =>
    clampPage(listPage.value, listTotal.value, KC_POOL_PAGE_SIZE),
  )
  const pagedPoolItems = computed((): KeyCustomersItem[] =>
    slicePage(filteredPoolItems.value, safeListPage.value, KC_POOL_PAGE_SIZE),
  )
  const listPageInfo = computed(() =>
    pageInfoDisp(safeListPage.value, listTotal.value, KC_POOL_PAGE_SIZE),
  )
  const listPageRange = computed(() =>
    pageRangeDisp(safeListPage.value, listTotal.value, KC_POOL_PAGE_SIZE),
  )
  const canPrevListPage = computed(() => safeListPage.value > 1)
  const canNextListPage = computed(() => safeListPage.value < listPages.value)

  watch(listTotal, () => {
    const next = clampPage(listPage.value, listTotal.value, KC_POOL_PAGE_SIZE)
    if (next !== listPage.value) listPage.value = next
  })

  function prevListPage() {
    if (listPage.value > 1) listPage.value -= 1
  }

  function nextListPage() {
    if (listPage.value < listPages.value) listPage.value += 1
  }

  /** 当前页 localIndex → 跨页连续 1-based 序号 */
  function rowDisplayIndex(localIndex: number): number {
    return rowIndex1Based(safeListPage.value, localIndex, KC_POOL_PAGE_SIZE)
  }

  const cards = computed(() => kc.value?.summary_cards || {})
  const structureCount = computed(() => kc.value?.structure_bars?.count)
  const structureAmount = computed(() => kc.value?.structure_bars?.amount)
  const nearTip = computed(
    () =>
      kc.value?.near_tip ||
      '距上一级门槛不超过10%，仅作销售跟进提示，不改变客户等级',
  )
  const silentTip = computed(
    () =>
      kc.value?.silent_tip ||
      '近 2 个已过去完整自然月下单预估为 0（当前月不计入）；当月有单仍可能静默',
  )
  const salesColTip = computed(
    () => kc.value?.sales_col_tip || '本年各销售下单预估金额（降序）',
  )
  const guideText = computed(
    () => kc.value?.guide_text || '从左侧客户池选择客户，或点行动队列开始跟进',
  )
  const dailyOn = computed(() => !!store.dailyActive)
  const actionSilent = computed(() => kc.value?.action_queues?.silent || [])
  const actionNear = computed(() => kc.value?.action_queues?.near || [])
  const hasAction = computed(
    () => actionSilent.value.length > 0 || actionNear.value.length > 0,
  )
  const rhythmDisclaimer = computed(
    () =>
      kc.value?.chart?.rhythm_disclaimer ||
      '各客户自身峰值=100，仅比较节奏，不比较金额',
  )

  function onItemClick(it: KeyCustomersItem) {
    selectCustomer(it)
  }

  function onActionClick(row: {
    name?: string
    mkey?: string
    tier?: string
    ytd_disp?: string
    status_disp?: string
    silent?: boolean
    near_upgrade?: boolean
    gap_disp?: string
  }) {
    const key = itemKey(row)
    const found = findItemByKey(key) || findItemByKey(`name:${row.name || ''}`)
    if (found) {
      selectCustomer(found)
      return
    }
    selectCustomer({
      name: row.name || '',
      ytd_disp: row.ytd_disp || '',
      sales_disp: '',
      mkey: row.mkey,
      tier: row.tier,
      silent: row.silent,
      near_upgrade: row.near_upgrade,
      status_disp: row.status_disp,
      gap_disp: row.gap_disp,
    })
  }

  function isSelected(it: KeyCustomersItem): boolean {
    return selectedKey.value === itemKey(it)
  }

  function isCompared(it: KeyCustomersItem): boolean {
    return compareKeys.value.includes(itemKey(it))
  }

  function toggleCompare(it: KeyCustomersItem) {
    const key = itemKey(it)
    const { state, hint } = toggleCompareState(
      { selectedKey: selectedKey.value, compareKeys: compareKeys.value },
      key,
      COMPARE_MAX.value,
    )
    selectedKey.value = state.selectedKey
    compareKeys.value = state.compareKeys
    compareHint.value = hint
    if (!selectedItem.value && key) {
      const found = findItemByKey(key) || it
      selectedItem.value = found
      selectedKey.value = itemKey(found)
    } else if (selectedKey.value) {
      selectedItem.value = findItemByKey(selectedKey.value) || selectedItem.value
    }
  }

  function removeCompare(key: string) {
    const next = removeCompareState(
      { selectedKey: selectedKey.value, compareKeys: compareKeys.value },
      key,
    )
    compareKeys.value = next.compareKeys
    compareHint.value = ''
  }

  /** 清空多家公司对比（保留当前选中客户） */
  function clearCompare() {
    compareKeys.value = []
    compareHint.value = ''
  }

  function salesLine(it: KeyCustomersItem): { text: string; title: string } {
    const sales = it.sales || []
    if (sales.length) {
      const parts = sales.map((s) => `${s.name} ${s.amount_disp}`)
      const full = parts.join(' · ')
      if (parts.length <= 3) return { text: full, title: full }
      const head = parts.slice(0, 3).join(' · ')
      return { text: `${head} · 另有 ${parts.length - 3} 人`, title: full }
    }
    const fallback = it.sales_disp || '—'
    return { text: fallback, title: fallback }
  }

  function barWidth(wo: number | undefined): string {
    const n = Number(wo) || 0
    return `${Math.max(0, Math.min(100, n))}%`
  }

  function openMonthModal() {
    const it = selectedItem.value
    if (!it) return
    const y = kc.value?.year_label || (kc.value?.year ? `${kc.value.year}年` : '')
    monthTitle.value = `${it.name} · ${y}各月下单`
    monthRows.value = monthRowsFor(it)
    monthModal.value = true
  }

  const highlightMonth = computed((): number => {
    const p = String(store.period || '')
    const m = p.match(/年(\d{1,2})月$/)
    if (m) {
      const n = Number(m[1])
      if (n >= 1 && n <= 12) return n
    }
    return new Date().getMonth() + 1
  })

  const trackSeriesItems = computed((): KeyCustomersItem[] => {
    const keys = resolveSeriesKeys(selectedKey.value, compareKeys.value)
    return keys
      .map((k) => findItemByKey(k))
      .filter((x): x is KeyCustomersItem => !!x)
  })

  const trackOption = computed(() => {
    void themeMode.value
    return buildKeyCustomersTrackOption({
      seriesItems: trackSeriesItems.value,
      monthlyFor: (it) => monthRowsFor(it) as KcMonthPoint[],
      mode: chartMode.value,
      amountAxis: kc.value?.amount_axis,
      highlightMonth: highlightMonth.value,
      amountTitle: kc.value?.chart?.amount_title,
      rhythmTitle: kc.value?.chart?.rhythm_title,
      rhythmDisclaimer: rhythmDisclaimer.value,
      yAxisNameAmount: kc.value?.chart?.y_axis_name_amount,
    })
  })

  const trackTitle = computed(() =>
    buildTrackTitle({
      seriesItems: trackSeriesItems.value,
      yearLabel: kc.value?.year_label || (kc.value?.year ? `${kc.value.year}年` : ''),
      mode: chartMode.value,
      amountTitle: kc.value?.chart?.amount_title,
      rhythmTitle: kc.value?.chart?.rhythm_title,
      compareCount: compareKeys.value.length,
    }),
  )

  const insightHeadLabel = computed(() =>
    headerModeLabel(selectedKey.value, compareKeys.value, (k) => findItemByKey(k)?.name || k),
  )

  const panelTitle = computed(() => {
    const base = kc.value?.panel_title || '重点客户下单情况追踪'
    const y = kc.value?.year_label || ''
    return y ? `${base} · ${y}` : base
  })

  const helpLines = computed(() => {
    const lines = kc.value?.help_lines
    if (lines && lines.length) return lines
    const c = kc.value?.caption
    return c ? [c] : []
  })

  const selectedSales = computed(() => selectedItem.value?.sales || [])
  const selectedTrend = computed(() => selectedItem.value?.trend || null)

  function sparkBars(it: KeyCustomersItem): number[] {
    const s = it.spark_rhythm || it.spark_wo
    if (s && s.length) return s.slice(0, 12)
    return []
  }

  function customerRowKey(it: KeyCustomersItem): string {
    return rowStableKey(it, kc.value?.year)
  }

  return {
    kc,
    visible,
    selectedKey,
    selectedItem,
    compareKeys,
    compareHint,
    activePool,
    activeStructureTier,
    filterMode,
    searchQ,
    chartMode,
    monthModal,
    monthTitle,
    monthRows,
    COMPARE_MAX,
    cards,
    structureCount,
    structureAmount,
    nearTip,
    silentTip,
    salesColTip,
    guideText,
    dailyOn,
    actionSilent,
    actionNear,
    hasAction,
    rhythmDisclaimer,
    poolLoading,
    poolError,
    poolItemsRaw,
    filteredPoolItems,
    pagedPoolItems,
    listPage,
    listPages,
    listTotal,
    listPageInfo,
    listPageRange,
    canPrevListPage,
    canNextListPage,
    KC_POOL_PAGE_SIZE,
    prevListPage,
    nextListPage,
    rowDisplayIndex,
    trackSeriesItems,
    trackOption,
    trackTitle,
    insightHeadLabel,
    panelTitle,
    helpLines,
    selectedSales,
    selectedTrend,
    setPool,
    setFilter,
    setChartMode,
    setSearchQ,
    onStructureTierClick,
    onItemClick,
    onActionClick,
    isSelected,
    isCompared,
    toggleCompare,
    removeCompare,
    clearCompare,
    salesLine,
    barWidth,
    openMonthModal,
    sparkBars,
    customerRowKey,
    findItemByKey,
    itemKey,
    monthRowsFor,
  }
}

export type UseKeyCustomers = ReturnType<typeof useKeyCustomers>
