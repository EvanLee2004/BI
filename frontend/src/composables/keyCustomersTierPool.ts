/**
 * 重点客户六档 → 经营池映射 + 点饼联动意图（3.6.2 纯函数）
 * S/A/B→focus · C/D→nurture · E→longtail；未知→longtail（与 domain.pool_for_tier 一致）
 */

export type KcPoolId = 'focus' | 'nurture' | 'longtail'

export type KcFilterMode = 'all' | 'silent' | 'near'

/** 点结构饼后的名单联动意图（组件只执行，不算账） */
export type StructureTierClickIntent = {
  tier: string
  pool: KcPoolId
  /** 始终切回全部，避免静默/临界筛掉目标档 */
  filterMode: 'all'
  ensureTiers: string[]
}

const FOCUS = new Set(['S', 'A', 'B'])
const NURTURE = new Set(['C', 'D'])
const LONGTAIL = new Set(['E'])

export function poolForTier(tierId: string): KcPoolId {
  const tid = String(tierId || '')
    .trim()
    .toUpperCase()
  if (FOCUS.has(tid)) return 'focus'
  if (NURTURE.has(tid)) return 'nurture'
  if (LONGTAIL.has(tid)) return 'longtail'
  return 'longtail'
}

/** 与 pools.tiers 对齐；未知档只 ensure 自身大写 */
export function tiersForPool(pool: KcPoolId): string[] {
  if (pool === 'focus') return ['S', 'A', 'B']
  if (pool === 'nurture') return ['C', 'D']
  return ['E']
}

/**
 * 点饼扇区 → 切池 + filter=all + 需 ensure 的档位列表。
 * tier 空串 → null（忽略点击）。
 */
export function structureTierClickIntent(
  tierId: string | null | undefined,
): StructureTierClickIntent | null {
  const raw = String(tierId || '').trim()
  if (!raw) return null
  const tier = raw.toUpperCase()
  const pool = poolForTier(tier)
  const poolTiers = tiersForPool(pool)
  const ensureTiers = poolTiers.includes(tier) ? poolTiers : [tier, ...poolTiers]
  return {
    tier,
    pool,
    filterMode: 'all',
    ensureTiers: [...new Set(ensureTiers)],
  }
}

/** 3.7.2：结构档点击结果（set 或 clear 再点同档） */
export type StructureTierApply = {
  kind: 'set' | 'clear'
  /** clear 时为空串 */
  tier: string
  pool: KcPoolId
  filterMode: 'all'
  ensureTiers: string[]
}

/** 清除结构筛选：回 default_pool（通常 focus）+ filter=all，无高亮 */
export function clearStructureFilterState(
  defaultPool: KcPoolId = 'focus',
): StructureTierApply {
  const pool = defaultPool || 'focus'
  return {
    kind: 'clear',
    tier: '',
    pool,
    filterMode: 'all',
    ensureTiers: tiersForPool(pool),
  }
}

/**
 * 3.7.2：点饼/图例档 — 同档再点=取消；异档=切换。
 * tier 空 → null；defaultPool 用于取消后回默认池。
 */
export function applyStructureTierToggle(
  tierId: string | null | undefined,
  activeStructureTier: string | null | undefined,
  defaultPool: KcPoolId = 'focus',
): StructureTierApply | null {
  const raw = String(tierId || '').trim()
  if (!raw) return null
  const tier = raw.toUpperCase()
  const active = String(activeStructureTier || '')
    .trim()
    .toUpperCase()
  if (active && tier === active) {
    return clearStructureFilterState(defaultPool)
  }
  const intent = structureTierClickIntent(tier)
  if (!intent) return null
  return {
    kind: 'set',
    tier: intent.tier,
    pool: intent.pool,
    filterMode: intent.filterMode,
    ensureTiers: intent.ensureTiers,
  }
}
