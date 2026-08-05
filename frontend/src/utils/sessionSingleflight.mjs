/** ESM mirror of sessionSingleflight.ts for node tests. */
export function createSessionSingleflight(fetchImpl) {
  let inflight = null
  return {
    get() {
      if (inflight) return inflight
      inflight = Promise.resolve()
        .then(() => fetchImpl())
        .finally(() => {
          inflight = null
        })
      return inflight
    },
    invalidate() {
      inflight = null
    },
  }
}
