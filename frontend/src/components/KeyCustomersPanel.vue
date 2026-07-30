<script setup lang="ts">
/**
 * 3.4.0 重点客户分析 · Layer3
 * 四区最底：六档手风琴 + 双饼；点客户 1～12 月下单。
 * 前端零金额/分级运算；日查不换本块；切月不重算等级。
 */
import '../styles/components/KeyCustomersPanel.css'
import { computed, reactive, ref, watch } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import SciFiPanel from './SciFiPanel.vue'
import DataModal from './base/DataModal.vue'
import RankBar from './base/RankBar.vue'
import EchartsHost from './charts/EchartsHost.vue'
import {
  animBlock,
  chartMutedColor,
  chartTextColor,
  pieEmphasis,
  pieGlowItemStyle,
  SERIES_PALETTE,
} from '../chart-fx'
import { cssColor } from '../utils/cssColor'
import { themeMode } from '../utils/theme'

export type KcItem = {
  name: string
  ytd_disp: string
  sales_disp: string
  silent?: boolean
  mkey?: string
  wo?: number
}

export type KcTier = {
  id: string
  label: string
  range_disp: string
  count: number
  amount_disp: string
  pct_count_disp: string
  pct_amount_disp: string
  default_open: boolean
  lazy: boolean
  items: KcItem[]
}

export type KcPie = {
  labels: string[]
  values: number[]
  values_disp: string[]
  pct_disp: string[]
}

export type KeyCustomersVM = {
  year?: number
  year_label?: string
  caption?: string
  metric_label?: string
  tiers?: KcTier[]
  pie_count?: KcPie
  pie_amount?: KcPie
  monthly?: Record<string, { i?: number; name: string; order_disp: string; wo?: number }[]>
  empty?: boolean
  totals?: { count?: number; amount_disp?: string }
}

const store = useCockpitStore()

const kc = computed((): KeyCustomersVM | null => {
  const v = store.vm as { key_customers?: KeyCustomersVM } | null
  return v?.key_customers || null
})

const visible = computed(() => {
  const d = kc.value
  if (!d) return false
  if (d.empty && !(d.tiers && d.tiers.length)) return false
  return !!(d.tiers && d.tiers.length)
})

const openMap = reactive<Record<string, boolean>>({})
const itemsCache = reactive<Record<string, KcItem[]>>({})
const loadErr = reactive<Record<string, string>>({})
const loadingTier = reactive<Record<string, boolean>>({})
const monthlyExtra = reactive<Record<string, { i?: number; name: string; order_disp: string; wo?: number }[]>>({})

watch(
  () => kc.value,
  (d) => {
    if (!d?.tiers) return
    for (const t of d.tiers) {
      if (openMap[t.id] === undefined) {
        openMap[t.id] = !!t.default_open
      }
      if (!t.lazy && t.items?.length) {
        itemsCache[t.id] = t.items
      }
    }
  },
  { immediate: true },
)

function tierItems(t: KcTier): KcItem[] {
  if (itemsCache[t.id]?.length) return itemsCache[t.id]
  return t.items || []
}

async function ensureTier(t: KcTier) {
  if (!t.lazy) {
    if (t.items?.length) itemsCache[t.id] = t.items
    return
  }
  if (itemsCache[t.id]?.length) return
  if (store.snapshotMode) {
    // 导出 embed 应已有 items；若无则人话空态
    itemsCache[t.id] = t.items || []
    if (!itemsCache[t.id].length) {
      loadErr[t.id] = '快照中无该档名单'
    }
    return
  }
  loadingTier[t.id] = true
  loadErr[t.id] = ''
  try {
    const buQ =
      store.scope === 'bu' && store.buName
        ? `&bu=${encodeURIComponent(store.buName)}`
        : ''
    const r = await fetch(
      `/api/v1/key-customers/tier?tier=${encodeURIComponent(t.id)}${buQ}`,
      { credentials: 'same-origin' },
    )
    if (!r.ok) {
      loadErr[t.id] =
        r.status === 403
          ? '无权查看该档名单'
          : r.status === 401
            ? '请先登录'
            : '加载该档名单失败'
      return
    }
    const d = (await r.json()) as {
      items?: KcItem[]
      monthly?: Record<string, { i?: number; name: string; order_disp: string; wo?: number }[]>
    }
    itemsCache[t.id] = d.items || []
    for (const [k, rows] of Object.entries(d.monthly || {})) {
      monthlyExtra[k] = rows
    }
  } catch {
    loadErr[t.id] = '网络异常，请稍后重试'
  } finally {
    loadingTier[t.id] = false
  }
}

async function toggleTier(t: KcTier) {
  const next = !openMap[t.id]
  openMap[t.id] = next
  if (next) await ensureTier(t)
}

const monthModal = ref(false)
const monthTitle = ref('')
const monthRows = ref<{ i?: number; name: string; order_disp: string; wo?: number }[]>([])

function onItemClick(it: KcItem) {
  if (!it.mkey) {
    monthTitle.value = (it.name || '') + ' · 各月下单'
    monthRows.value = []
    monthModal.value = true
    return
  }
  const base = kc.value?.monthly || {}
  const rows = monthlyExtra[it.mkey] || base[it.mkey] || []
  const y = kc.value?.year_label || (kc.value?.year ? `${kc.value.year}年` : '')
  monthTitle.value = `${it.name} · ${y}各月下单`
  monthRows.value = rows
  monthModal.value = true
}

function pieOption(pie: KcPie | undefined, centerTitle: string) {
  void themeMode.value
  const labels = pie?.labels || []
  const values = pie?.values || []
  const valuesDisp = pie?.values_disp || []
  const pctDisp = pie?.pct_disp || []
  const data = labels.map((name, i) => ({
    name,
    value: Number(values[i] || 0),
    itemStyle: { color: SERIES_PALETTE[i % SERIES_PALETTE.length] },
  }))
  const ink = chartTextColor()
  const mut = chartMutedColor()
  return {
    ...animBlock(),
    tooltip: {
      trigger: 'item',
      confine: true,
      formatter: (p: { dataIndex: number; name: string }) => {
        const i = p.dataIndex
        return `${p.name}<br/>${valuesDisp[i] || '—'}（${pctDisp[i] || '—'}）`
      },
    },
    color: SERIES_PALETTE,
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        data,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: {
          borderColor: cssColor('--chart-label-stroke-dark') || cssColor('--panel-bg'),
          borderWidth: 2,
          ...pieGlowItemStyle(cssColor('--blue')),
        },
        emphasis: pieEmphasis(),
      },
    ],
    graphic: [
      {
        type: 'group',
        left: 'center',
        top: 'middle',
        children: [
          {
            type: 'text',
            style: {
              text: centerTitle,
              fill: mut,
              fontSize: 11,
              textAlign: 'center',
            },
            top: -8,
          },
          {
            type: 'text',
            style: {
              text: pie?.values_disp
                ? String(
                    labels
                      .map((_, i) => Number(values[i] || 0))
                      .reduce((a, b) => a + b, 0),
                  )
                : '',
              fill: ink,
              fontSize: 0, // 不用前端加总做展示主数字；中心只标题
              textAlign: 'center',
            },
          },
        ],
      },
    ],
  }
}

// 中心文案用后端 totals，避免前端对金额求和
const pieCountOption = computed(() => {
  const t = kc.value?.totals?.count
  return pieOption(kc.value?.pie_count, t != null ? `共${t}户` : '数量')
})
const pieAmountOption = computed(() => {
  const a = kc.value?.totals?.amount_disp || ''
  return pieOption(kc.value?.pie_amount, a ? a : '金额')
})

const dailyOn = computed(() => !!store.dailyActive)
</script>

<template>
  <div
    v-if="visible"
    id="keyCustomers"
    class="kc-host"
    data-testid="key-customers-panel"
    data-source="key_customers"
  >
    <SciFiPanel panel-class="kc-panel">
      <template #header>
        <span>重点客户分析 · {{ kc?.year_label || '' }}</span>
      </template>
      <p class="kc-caption" data-testid="kc-caption">{{ kc?.caption }}</p>
      <p v-if="dailyOn" class="kc-daily-hint" data-testid="kc-daily-hint">
        日查仅作用于上方排名；本块仍按自然年分级，不随日区间重算。
      </p>
      <div class="kc-grid">
        <div class="kc-list" data-testid="kc-list">
          <div
            v-for="t in kc?.tiers || []"
            :key="t.id"
            class="kc-tier"
            :data-tier="t.id"
            :data-open="openMap[t.id] ? '1' : '0'"
          >
            <button
              type="button"
              class="kc-tier__head"
              :data-testid="'kc-tier-head-' + t.id"
              :aria-expanded="openMap[t.id] ? 'true' : 'false'"
              @click="toggleTier(t)"
            >
              <span class="kc-tier__id">{{ t.label }}</span>
              <span class="kc-tier__range">{{ t.range_disp }}</span>
              <span class="kc-tier__meta">
                <span>{{ t.count }}户</span>
                <span>{{ t.amount_disp }}</span>
                <span>{{ t.pct_amount_disp }}</span>
              </span>
              <span class="kc-tier__chev">{{ openMap[t.id] ? '▾' : '▸' }}</span>
            </button>
            <div v-if="openMap[t.id]" class="kc-tier__body" :data-testid="'kc-tier-body-' + t.id">
              <div v-if="loadingTier[t.id]" class="kc-tier__loading">加载中…</div>
              <div v-else-if="loadErr[t.id]" class="kc-tier__err">{{ loadErr[t.id] }}</div>
              <div v-else-if="!tierItems(t).length" class="kc-tier__empty">
                {{ t.count ? '暂无名单' : '该档暂无客户' }}
              </div>
              <button
                v-for="(it, idx) in tierItems(t)"
                :key="t.id + '-' + idx + '-' + it.name"
                type="button"
                class="kc-row"
                data-testid="kc-customer-row"
                @click="onItemClick(it)"
              >
                <span class="kc-row__name">
                  {{ it.name }}
                  <span v-if="it.silent" class="kc-row__silent" title="连续两月无下单">静默</span>
                </span>
                <span class="kc-row__sales">{{ it.sales_disp }}</span>
                <span class="kc-row__ytd">{{ it.ytd_disp }}</span>
              </button>
            </div>
          </div>
        </div>
        <div class="kc-pies" data-testid="kc-pies">
          <div class="kc-pie-block">
            <div class="kc-pie-title">级分布 · 数量</div>
            <div class="kc-pie-chart">
              <EchartsHost :option="pieCountOption" />
            </div>
            <ul class="kc-pie-legend">
              <li v-for="(lab, i) in kc?.pie_count?.labels || []" :key="'pc' + lab">
                <span class="kc-pie-dot" :data-i="i" />
                <span>{{ lab }}</span>
                <span>{{ kc?.pie_count?.values_disp?.[i] }}户</span>
                <span>{{ kc?.pie_count?.pct_disp?.[i] }}</span>
              </li>
            </ul>
          </div>
          <div class="kc-pie-block">
            <div class="kc-pie-title">级分布 · 金额</div>
            <div class="kc-pie-chart">
              <EchartsHost :option="pieAmountOption" />
            </div>
            <ul class="kc-pie-legend">
              <li v-for="(lab, i) in kc?.pie_amount?.labels || []" :key="'pa' + lab">
                <span class="kc-pie-dot" :data-i="i" />
                <span>{{ lab }}</span>
                <span>{{ kc?.pie_amount?.values_disp?.[i] }}</span>
                <span>{{ kc?.pie_amount?.pct_disp?.[i] }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </SciFiPanel>

    <DataModal :open="monthModal" :title="monthTitle" @close="monthModal = false">
      <div v-if="!monthRows.length" class="rank-list__empty">暂无月度下单数据</div>
      <div v-else class="kc-month-list" data-testid="kc-month-modal">
        <RankBar
          v-for="(it, idx) in monthRows"
          :key="'kcm' + idx + it.name"
          :rank="it.i ?? idx + 1"
          :name="String(it.name || '')"
          :primary-width="Number(it.wo) || 0"
          :primary-value="it.order_disp"
        />
      </div>
    </DataModal>
  </div>
</template>
