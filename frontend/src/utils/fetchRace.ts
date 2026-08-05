/**
 * 3.7.14 AUDIT-010：请求世代号 — 乱序 resolve 时丢弃过期结果。
 * 纯函数，可供单测直驱。
 */

/** 当前世代与本次请求世代不一致 → 过期，勿写回 store */
export function isStaleGeneration(active: number, mine: number): boolean {
  return mine !== active
}

/** 推进世代；bump 由调用方持有的计数器闭包提供 */
export function bumpGeneration(next: () => number): number {
  return next()
}

/**
 * 创建一代请求控制器：abort 上一代 + 新 generation。
 * 用法：const g = gate.next(); fetch(..., { signal: g.signal }); if (gate.isStale(g.id)) return
 */
export function createGenerationGate() {
  let active = 0
  let controller: AbortController | null = null

  return {
    next(): { id: number; signal: AbortSignal } {
      try {
        controller?.abort()
      } catch {
        /* ignore */
      }
      controller = new AbortController()
      active += 1
      return { id: active, signal: controller.signal }
    },
    isStale(id: number): boolean {
      return isStaleGeneration(active, id)
    },
    get active() {
      return active
    },
    abort() {
      try {
        controller?.abort()
      } catch {
        /* ignore */
      }
    },
  }
}
