/** 2.6.10 V-4：站内轻提示总线（替代原生 alert）。 */

export type ToastKind = 'info' | 'warn' | 'error'

export type ToastPayload = {
  message: string
  kind?: ToastKind
  ms?: number
}

type Listener = (p: ToastPayload) => void

const listeners = new Set<Listener>()

export function showToast(message: string, kind: ToastKind = 'info', ms = 3200): void {
  const payload: ToastPayload = { message, kind, ms }
  listeners.forEach((fn) => {
    try {
      fn(payload)
    } catch {
      /* ignore */
    }
  })
}

export function onToast(fn: Listener): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}
