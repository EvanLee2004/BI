/**
 * 管理端长列表统一客户端翻页（2.2.5）：每页 50，上一页/下一页 + 共 N 条 · 第 X 页。
 * 数据源变化时自动回到第 1 页。
 */
import { computed, ref, unref, watch, type MaybeRef, type Ref } from 'vue'

export const ADMIN_PAGE_SIZE = 50

export function useClientPager<T>(source: MaybeRef<T[]>, pageSize = ADMIN_PAGE_SIZE) {
  const page = ref(1)
  const total = computed(() => unref(source).length)
  const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize) || 1))
  const pageRows = computed(() => {
    const all = unref(source)
    const p = Math.min(Math.max(1, page.value), pages.value)
    if (p !== page.value) page.value = p
    const start = (p - 1) * pageSize
    return all.slice(start, start + pageSize)
  })
  const pageInfo = computed(
    () => `共 ${total.value} 条 · 第 ${page.value}/${pages.value} 页`,
  )

  function resetPage() {
    page.value = 1
  }
  function prevPage() {
    if (page.value > 1) page.value -= 1
  }
  function nextPage() {
    if (page.value < pages.value) page.value += 1
  }

  watch(
    () => unref(source).length,
    () => {
      if (page.value > pages.value) page.value = pages.value
    },
  )

  return {
    page: page as Ref<number>,
    pageSize,
    total,
    pages,
    pageRows,
    pageInfo,
    resetPage,
    prevPage,
    nextPage,
  }
}
