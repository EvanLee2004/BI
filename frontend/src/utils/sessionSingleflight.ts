/**
 * 3.7.14 AUDIT-017：同页 session 拉取单飞；登出/登录成功 invalidate。
 */

export type SessionFetcher<T> = () => Promise<T>

export function createSessionSingleflight<T>(fetchImpl: SessionFetcher<T>) {
  let inflight: Promise<T> | null = null

  return {
    get(): Promise<T> {
      if (inflight) return inflight
      inflight = Promise.resolve()
        .then(() => fetchImpl())
        .finally(() => {
          inflight = null
        })
      return inflight
    },
    invalidate(): void {
      inflight = null
    },
  }
}
