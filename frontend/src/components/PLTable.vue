<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import SciFiPanel from './SciFiPanel.vue'
import type { PLDetail, PLDetailLine, PLTablePeriod } from '../types/vm'

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
/** 2.4.0：抽屉内「其他N项」展开集合（按行 name 记） */
const expandedOther = ref<Record<string, boolean>>({})
function toggleOther(name: string) {
  expandedOther.value = {
    ...expandedOther.value,
    [name]: !expandedOther.value[name],
  }
}
function isExpandable(ln: PLDetailLine): boolean {
  return !!ln.expandable
}
function childLines(ln: PLDetailLine): PLDetailLine[] {
  return ln.children || []
}

const exporting = ref(false)

/** 2.3.6：按当前筛选导出管理利润表 Excel（含构成明细）。 */
async function exportPlExcel() {
  if (exporting.value || store.snapshotMode) return
  if (typeof location !== 'undefined' && location.protocol === 'file:') {
    alert('导出需在看板服务页面使用')
    return
  }
  const blk = store.period || ''
  const url =
    store.scope === 'bu' && store.buName
      ? `/bu/${encodeURIComponent(store.buName)}/export/pl.xlsx?blk=${encodeURIComponent(blk)}`
      : `/api/export/pl.xlsx?blk=${encodeURIComponent(blk)}`
  exporting.value = true
  try {
    const r = await fetch(url, { credentials: 'same-origin' })
    if (!r.ok) {
      let msg = `HTTP ${r.status}`
      try {
        const t = await r.text()
        if (t) {
          try {
            const j = JSON.parse(t) as { detail?: string }
            msg = j.detail || t.slice(0, 200)
          } catch {
            msg = t.slice(0, 200)
          }
        }
      } catch {
        /* ignore */
      }
      throw new Error(msg)
    }
    const cd = r.headers.get('Content-Disposition') || ''
    let fn = '管理利润表.xlsx'
    const m = /filename\*=UTF-8''([^;]+)|filename="([^"]+)"/i.exec(cd)
    if (m) {
      try {
        fn = decodeURIComponent(m[1] || m[2] || fn)
      } catch {
        fn = m[1] || m[2] || fn
      }
    } else {
      const xf = r.headers.get('X-Filename')
      if (xf) {
        try {
          fn = decodeURIComponent(xf)
        } catch {
          fn = xf
        }
      }
    }
    const b = await r.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(b)
    a.download = fn
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(a.href)
  } catch (e) {
    alert('导出失败：' + (e instanceof Error ? e.message : String(e)))
  } finally {
    exporting.value = false
  }
}

function openDrawer(key: string | null | undefined) {
  if (!key) return
  openKey.value = key
  expandedOther.value = {}
}
function closeDrawer() {
  openKey.value = null
  expandedOther.value = {}
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') closeDrawer()
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>
<template>
  <SciFiPanel title="管理利润表" :tag="plTag" panel-class="pl-card">
    <template #header>
      <div class="pl-header-row">
        <div class="pl-header-left">
          <span>管理利润表</span>
          <span v-if="plTag" class="tag">{{ plTag }}</span>
        </div>
        <button
          v-if="!store.snapshotMode"
          type="button"
          class="ghost mini pl-export-btn"
          data-testid="pl-export-excel"
          :disabled="exporting"
          @click.stop="exportPlExcel"
        >
          ⬇ {{ exporting ? '生成中…' : '导出 Excel' }}
        </button>
      </div>
    </template>
    <div class="pl-table">
      <div
        v-for="(r, i) in table.rows"
        :key="i"
        class="pl-row"
        :class="{ total: r.total, grand: r.grand, 'pl-open': !!r.open_key, 'pl-pct': r.is_pct }"
        @click="r.open_key && openDrawer(r.open_key)"
      >
        <span class="pl-name">
          {{ r.name }}
          <span v-if="r.open_key" class="pl-open-hint">查看构成 ›</span>
          <span v-if="r.formula" class="pl-src">{{ r.formula }}</span>
        </span>
        <span class="pl-amt" :class="{ pos: r.grand || r.total || r.is_pct }">{{ r.amt_disp }}</span>
      </div>
    </div>
    <!-- 数据源徽标（装饰对齐基准；无金额） -->
    <div class="src-legend" aria-hidden="true">
      <span><i class="s-sys" />智云</span>
      <span><i class="s-led" />台账</span>
      <span><i class="s-man" />手填</span>
    </div>

    <!-- 右侧抽屉：body 直下 fixed 用 portal 类 -->
    <Teleport to="body">
      <div
        v-if="drawerOpen && detail"
        class="drawer open"
        aria-hidden="false"
      >
        <div class="drawer-mask" data-testid="drawer-mask" @click="closeDrawer"></div>
        <div class="drawer-panel" data-testid="drawer-panel">
          <div class="drawer-h">
            <b id="drawerTitle">{{ detail.title }}</b>
            <button type="button" class="ghost mini" data-close @click="closeDrawer">关闭</button>
          </div>
          <div class="drawer-body" id="drawerBody">
            <template v-for="(ln, j) in detail.lines" :key="j">
              <div
                class="pl-drow"
                :class="{ sub: ln.sub, 'pl-other-expandable': isExpandable(ln) }"
                @click.stop="isExpandable(ln) && toggleOther(ln.name)"
              >
                <span class="pl-name">
                  <template v-if="isExpandable(ln)">{{ expandedOther[ln.name] ? '▾ ' : '▸ ' }}</template>
                  {{ ln.name }}
                </span>
                <span class="pl-amt">{{ ln.amt_disp }}</span>
              </div>
              <template v-if="isExpandable(ln) && expandedOther[ln.name]">
                <div
                  v-for="(ch, k) in childLines(ln)"
                  :key="j + '-' + k"
                  class="pl-drow sub pl-other-child"
                >
                  <span class="pl-name">{{ ch.name }}</span>
                  <span class="pl-amt">{{ ch.amt_disp }}</span>
                </div>
              </template>
            </template>
          </div>
        </div>
      </div>
    </Teleport>
  </SciFiPanel>
</template>

<style scoped>
.pl-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  min-width: 0;
}
.pl-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.pl-export-btn {
  flex-shrink: 0;
  white-space: nowrap;
  /* 主题色由 theme.css button.ghost + .pl-export-btn 提供（2.4.1 暗色适配） */
}
</style>
