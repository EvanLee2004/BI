<script setup lang="ts">
/** 业务 BU 分页入口条（对齐 legacy chrome_prefix .bu-nav）；2.2.9 快照内 store 切换不跳路由 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'

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
const list = computed(() => {
  if (props.names && props.names.length) return props.names
  return store.buNames || []
})
const lab = computed(() => props.label || store.buNavLabel || '业务 BU 分页')
const cur = computed(() => props.current || store.buName || '')
const emptyHint = computed(() => {
  if (props.hint) return props.hint
  if (store.buNavHint) return store.buNavHint
  // 有配置计数但名单空、后端未给文案时的兜底（管理员/整体可见）
  if ((store.buConfigCount || 0) > 0 && !list.value.length) {
    return `已配置 ${store.buConfigCount} 个业务 BU，但入口名单为空。请管理员「更新数据」后刷新。`
  }
  return ''
})

function href(name: string) {
  return '/bu/' + encodeURIComponent(name)
}

async function onBuClick(name: string, e: Event) {
  e.preventDefault()
  if (name === store.buName) return
  /* 2.3.1：三主题转场 + KPI 重跳（count-up 随 period/vm 变） */
  await store.transitionToBu(name)
}
</script>
<template>
  <div
    v-if="list.length"
    class="bu-nav"
    role="navigation"
    :aria-label="lab"
    data-testid="bu-nav"
  >
    <span class="bu-nav-label">{{ lab }}</span>
    <span class="bu-nav-links">
      <a
        v-for="n in list"
        :key="n"
        class="bu-nav-a"
        :href="href(n)"
        :aria-current="n === cur ? 'page' : undefined"
        :style="n === cur ? 'border-color:var(--blue)' : undefined"
        @click="onBuClick(n, $event)"
      >{{ n }}</a>
    </span>
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

<style scoped>
.bu-nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 8px 16px;
  font-size: 13px;
}
.bu-nav-label {
  opacity: 0.75;
  white-space: nowrap;
}
.bu-nav-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.bu-nav-a {
  display: inline-flex;
  align-items: center;
  min-height: 36px;
  padding: 4px 12px;
  border: 1px solid var(--line, rgba(34, 211, 238, 0.35));
  border-radius: 8px;
  color: inherit;
  text-decoration: none;
}
.bu-nav-a:hover {
  border-color: var(--blue, #22d3ee);
}
.bu-nav--empty .bu-nav-hint {
  color: var(--warn, #fbbf24);
  font-size: 12px;
  line-height: 1.4;
  max-width: 52rem;
}
</style>
