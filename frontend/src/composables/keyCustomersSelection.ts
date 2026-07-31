/**
 * 重点客户选择/对比 SSOT（纯函数 · 3.5.0）
 *
 * 规则（最简单可解释）：
 * - 比较集非空 → 图/标题用比较集
 * - 点击客户：若在比较集中则只更新头部选中；若在比较集外 → 清空比较，切单客
 * - 加入对比 / 移出对比 只动 compareKeys
 */

export type KcKeyable = { mkey?: string; name?: string }

export function itemKey(it: KcKeyable | null | undefined): string {
  if (!it) return ''
  return it.mkey || (it.name ? `name:${it.name}` : '')
}

export function rowStableKey(it: KcKeyable, year?: number): string {
  const k = itemKey(it)
  if (k) return k
  return `y${year || 0}:${it?.name || 'unknown'}`
}

/** 图/标题实际展示的客户 key 集合 */
export function resolveSeriesKeys(
  selectedKey: string,
  compareKeys: readonly string[],
): string[] {
  if (compareKeys.length) return [...compareKeys]
  return selectedKey ? [selectedKey] : []
}

export type SelectState = {
  selectedKey: string
  compareKeys: string[]
}

/**
 * 点击客户行：
 * - 无对比时再点当前选中 → 取消选中（3.7.2）
 * - 非比较成员则清比较回单客
 * - 比较成员仅切换头部选中（再点同头且仍在对比集 → 保持，不拆对比）
 */
export function selectCustomerState(
  state: SelectState,
  key: string,
): SelectState {
  if (!key) {
    return { selectedKey: '', compareKeys: [...state.compareKeys] }
  }
  if (
    key === state.selectedKey &&
    !state.compareKeys.length
  ) {
    return { selectedKey: '', compareKeys: [] }
  }
  if (state.compareKeys.length && !state.compareKeys.includes(key)) {
    return { selectedKey: key, compareKeys: [] }
  }
  return { selectedKey: key, compareKeys: [...state.compareKeys] }
}

export function toggleCompareState(
  state: SelectState,
  key: string,
  max: number,
): { state: SelectState; hint: string } {
  if (!key) return { state: { ...state, compareKeys: [...state.compareKeys] }, hint: '' }
  const idx = state.compareKeys.indexOf(key)
  if (idx >= 0) {
    return {
      state: {
        selectedKey: state.selectedKey,
        compareKeys: state.compareKeys.filter((k) => k !== key),
      },
      hint: '',
    }
  }
  if (state.compareKeys.length >= max) {
    return {
      state: { ...state, compareKeys: [...state.compareKeys] },
      hint: `最多同时比较 ${max} 个客户，请先移出一位再加入`,
    }
  }
  const next = [...state.compareKeys, key]
  return {
    state: {
      selectedKey: state.selectedKey || key,
      compareKeys: next,
    },
    hint: '',
  }
}

export function removeCompareState(state: SelectState, key: string): SelectState {
  return {
    selectedKey: state.selectedKey,
    compareKeys: state.compareKeys.filter((k) => k !== key),
  }
}

/** 头部模式文案：对比 N 客 / 单客 */
export function headerModeLabel(
  selectedKey: string,
  compareKeys: readonly string[],
  resolveName: (key: string) => string,
): string {
  if (compareKeys.length) {
    return `对比 ${compareKeys.length} 客`
  }
  if (selectedKey) {
    return resolveName(selectedKey) || selectedKey
  }
  return ''
}
