<script setup lang="ts">
/**
 * 业务 BU 分页：整体 | 多语营销 | …（2.6.5·D 加「整体」；按权限显隐）
 */
import '../styles/components/BuNav.css'
import { computed, onMounted, ref } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import { fetchSession } from '../api/client'

const props = withDefaults(
  defineProps<{
    label?: string
    names?: string[]
    current?: string
    hint?: string
  }>(),
  { label: '业务 BU 分页', names: () => [], current: '', hint: '' },
)

const store = useCockpitStore()
/** 仅整体/管理员可见「整体」按钮 */
const canMain = ref(false)

const list = computed(() => {
  if (props.names && props.names.length) return props.names
  return store.buNames || []
})
const lab = computed(() => props.label || store.buNavLabel || '业务 BU 分页')
const cur = computed(() => {
  if (props.current) return props.current
  if (store.scope === 'main') return '整体'
  return store.buName || ''
})
const emptyHint = computed(() => {
  if (props.hint) return props.hint
  if (store.buNavHint) return store.buNavHint
  if ((store.buConfigCount || 0) > 0 && !list.value.length) {
    return `已配置 ${store.buConfigCount} 个业务 BU，但入口名单为空。请管理员「更新数据」后刷新。`
  }
  return ''
})
const showOverall = computed(() => {
  if (store.snapshotMode) return store.snapshotCanGoOverall()
  return canMain.value
})

/** 2.6.6·T1-8：整体含未归属、BU 页不含 → 必须标明差额，禁止两数字对不上却不说明 */
const unassignedNote = computed(() => {
  if (store.scope !== 'main') return ''
  const vm = store.vm as {
    unassigned?: { count?: number; by_period?: Record<string, string> }
    meta?: { unassigned?: { count?: number; by_period?: Record<string, string> } }
  } | null
  const u = vm?.unassigned || vm?.meta?.unassigned
  const n = Number(u?.count || 0)
  if (!n) return ''
  const pk = store.period || ''
  const amt = (u?.by_period && pk && u.by_period[pk]) || ''
  return amt
    ? `未归属 BU 销售 ${n} 人 · 本期未归属下单 ${amt}（只在整体、不进各 BU；整体合计大于各 BU 之和属正常）`
    : `未归属 BU 销售 ${n} 人（其下单/收入只在整体页，不进各 BU；整体合计大于各 BU 之和属正常）`
})

function href(name: string) {
  if (name === '整体') return '/'
  return '/bu/' + encodeURIComponent(name)
}

async function onBuClick(name: string, e: Event) {
  e.preventDefault()
  if (name === '整体') {
    if (store.scope === 'main' && !store.buName) return
    await store.transitionToMain()
    return
  }
  if (name === store.buName && store.scope === 'bu') return
  await store.transitionToBu(name)
}

onMounted(async () => {
  if (store.snapshotMode) {
    canMain.value = store.snapshotCanGoOverall()
    return
  }
  try {
    const sess = await fetchSession()
    canMain.value = !!(sess as { can_main?: boolean; is_admin?: boolean }).can_main
      || !!(sess as { is_admin?: boolean }).is_admin
  } catch {
    canMain.value = false
  }
})
</script>
<template>
  <div
    v-if="list.length || showOverall"
    class="bu-nav"
    role="navigation"
    :aria-label="lab"
    data-testid="bu-nav"
  >
    <span class="bu-nav-label">{{ lab }}</span>
    <span class="bu-nav-links">
      <a
        v-if="showOverall"
        class="bu-nav-a"
        data-testid="bu-nav-overall"
        href="/"
        :aria-current="cur === '整体' ? 'page' : undefined"
        :style="cur === '整体' ? 'border-color:var(--blue)' : undefined"
        @click="onBuClick('整体', $event)"
        >整体</a
      >
      <a
        v-for="n in list"
        :key="n"
        class="bu-nav-a"
        :href="href(n)"
        :aria-current="n === cur ? 'page' : undefined"
        :style="n === cur ? 'border-color:var(--blue)' : undefined"
        @click="onBuClick(n, $event)"
        >{{ n }}</a
      >
    </span>
    <div
      v-if="unassignedNote"
      class="bu-nav-unassigned"
      role="status"
      data-testid="bu-nav-unassigned-gap"
    >{{ unassignedNote }}</div>
  </div>
  <div
    v-else-if="emptyHint"
    class="bu-nav bu-nav--empty"
    role="status"
    data-testid="bu-nav-empty-hint"
  >
    <span class="bu-nav-label">{{ lab }}</span>
    <span class="bu-nav-hint">{{ emptyHint }}</span>
  </div>
</template>
