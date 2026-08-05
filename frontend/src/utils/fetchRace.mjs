/** ESM mirror of fetchRace.ts for node tests without strip-types. */
export function isStaleGeneration(active, mine) {
  return mine !== active
}

export function bumpGeneration(next) {
  return next()
}

export function createGenerationGate() {
  let active = 0
  let controller = null
  return {
    next() {
      try {
        controller?.abort()
      } catch {
        /* ignore */
      }
      controller = new AbortController()
      active += 1
      return { id: active, signal: controller.signal }
    },
    isStale(id) {
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
