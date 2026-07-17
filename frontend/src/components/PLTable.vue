<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import SciFiPanel from './SciFiPanel.vue'
import type { PLDetail, PLTablePeriod } from '../types/vm'

const store = useCockpitStore()

const table = computed((): PLTablePeriod => {
  return store.vm?.pl?.table_by_period?.[store.period] || { rows: [], details: {} }
})
const plTag = computed(() => store.vm?.pl?.pl_tag || '')

const openKey = ref<string | null>(null)
const drawerOpen = computed(() => !!openKey.value)
const detail = computed((): PLDetail | null => {
  if (!openKey.value) return null
  return (table.value.details || {})[openKey.value] || null
})

function openDrawer(key: string | null | undefined) {
  if (!key) return
  openKey.value = key
}
function closeDrawer() {
  openKey.value = null
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') closeDrawer()
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>
<template>
  <SciFiPanel title="管理利润表" :tag="plTag" panel-class="pl-card">
    <div class="pl-table">
      <div
        v-for="(r, i) in table.rows"
        :key="i"
        class="pl-row"
        :class="{ total: r.total, grand: r.grand, 'pl-open': !!r.open_key }"
        @click="r.open_key && openDrawer(r.open_key)"
      >
        <span class="pl-name">
          {{ r.name }}
          <span v-if="r.open_key" class="pl-open-hint">查看构成 ›</span>
          <span v-if="r.formula" class="pl-src">{{ r.formula }}</span>
        </span>
        <span class="pl-amt" :class="{ pos: r.grand || r.total }">{{ r.amt_disp }}</span>
      </div>
    </div>

    <!-- 右侧抽屉：body 直下 fixed 用 portal 类 -->
    <Teleport to="body">
      <div
        v-if="drawerOpen && detail"
        class="drawer open"
        aria-hidden="false"
        @click.self="closeDrawer"
      >
        <div class="drawer-panel">
          <div class="drawer-h">
            <b id="drawerTitle">{{ detail.title }}</b>
            <button type="button" class="ghost mini" data-close @click="closeDrawer">关闭</button>
          </div>
          <div class="drawer-body" id="drawerBody">
            <div
              v-for="(ln, j) in detail.lines"
              :key="j"
              class="pl-drow"
              :class="{ sub: ln.sub }"
            >
              <span>{{ ln.name }}</span>
              <span class="pl-amt">{{ ln.amt_disp }}</span>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </SciFiPanel>
</template>
