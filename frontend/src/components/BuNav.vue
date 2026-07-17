<script setup lang="ts">
/** 业务 BU 分页入口条（对齐 legacy chrome_prefix .bu-nav） */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'

const props = withDefaults(
  defineProps<{
    label?: string
    names?: string[]
    current?: string
  }>(),
  { label: '业务 BU 分页', names: () => [], current: '' },
)

const store = useCockpitStore()
const list = computed(() => {
  if (props.names && props.names.length) return props.names
  return store.buNames || []
})
const lab = computed(() => props.label || store.buNavLabel || '业务 BU 分页')
const cur = computed(() => props.current || store.buName || '')

function href(name: string) {
  return '/bu/' + encodeURIComponent(name)
}
</script>
<template>
  <div
    v-if="list.length"
    class="bu-nav"
    role="navigation"
    :aria-label="lab"
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
      >{{ n }}</a>
    </span>
  </div>
</template>
