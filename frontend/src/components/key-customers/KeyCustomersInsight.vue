<script setup lang="ts">
import EchartsHost from '../charts/EchartsHost.vue'
import type { KeyCustomersItem, KeyCustomersVM } from '../../types/vm'
import type { ChartMode } from '../../charts/keyCustomersChart'

defineProps<{
  selectedItem: KeyCustomersItem | null
  guideText: string
  hasAction: boolean
  actionSilent: NonNullable<NonNullable<KeyCustomersVM['action_queues']>['silent']>
  actionNear: NonNullable<NonNullable<KeyCustomersVM['action_queues']>['near']>
  silentTip: string
  nearTip: string
  compareKeys: string[]
  compareHint: string
  insightHeadLabel: string
  selectedTrend: KeyCustomersItem['trend'] | null
  selectedSales: NonNullable<KeyCustomersItem['sales']>
  trackSeriesCount: number
  trackTitle: string
  trackOption: Record<string, unknown>
  chartMode: ChartMode
  rhythmDisclaimer: string
  isCompared: (it: KeyCustomersItem) => boolean
  findItemByKey: (k: string) => KeyCustomersItem | null
  barWidth: (wo: number | undefined) => string
}>()

const emit = defineEmits<{
  'action-click': [row: Record<string, unknown>]
  'toggle-compare': [it: KeyCustomersItem]
  'open-month': []
  'remove-compare': [key: string]
  'set-chart-mode': [m: ChartMode]
}>()
</script>

<template>
  <section class="kc-insight" data-testid="kc-insight" aria-label="客户洞察">
    <div v-if="!selectedItem" class="kc-insight__empty" data-testid="kc-insight-empty">
      <p class="kc-guide" data-testid="kc-guide">{{ guideText }}</p>
      <div v-if="hasAction" class="kc-action-queue" data-testid="kc-action-queue">
        <div v-if="actionSilent.length" class="kc-action-block">
          <div class="kc-section-label">需跟进（静默重点）</div>
          <button
            v-for="row in actionSilent"
            :key="'as' + (row.mkey || row.name)"
            type="button"
            class="kc-action-row"
            data-testid="kc-action-row"
            @click="emit('action-click', row)"
          >
            <span class="kc-row__tier" :data-tier="row.tier">{{ row.tier }}</span>
            <span class="kc-action-row__name" :title="row.name">{{ row.name }}</span>
            <span class="kc-action-row__meta">{{ row.ytd_disp }}</span>
            <span class="kc-row__status is-silent">{{ row.status_disp || '静默' }}</span>
          </button>
        </div>
        <div v-if="actionNear.length" class="kc-action-block">
          <div class="kc-section-label" :title="nearTip">临界晋级</div>
          <button
            v-for="row in actionNear"
            :key="'an' + (row.mkey || row.name)"
            type="button"
            class="kc-action-row"
            data-testid="kc-action-row"
            @click="emit('action-click', row)"
          >
            <span class="kc-row__tier" :data-tier="row.tier">{{ row.tier }}</span>
            <span class="kc-action-row__name" :title="row.name">{{ row.name }}</span>
            <span class="kc-action-row__meta">{{ row.ytd_disp }}</span>
            <span class="kc-row__status is-near">{{ row.status_disp || '临界' }}</span>
          </button>
        </div>
      </div>
      <div v-else class="kc-tier__empty" data-testid="kc-action-empty">
        当前无需跟进或临界晋级提醒
      </div>
    </div>

    <template v-else>
      <div class="kc-insight__head" data-testid="kc-insight-head">
        <div class="kc-insight__title">
          <span v-if="compareKeys.length" class="kc-insight__mode" data-testid="kc-compare-mode">{{
            insightHeadLabel
          }}</span>
          <template v-else>
            <span class="kc-row__tier" :data-tier="selectedItem.tier">{{ selectedItem.tier }}</span>
            <span class="kc-insight__name" :title="selectedItem.name">{{ selectedItem.name }}</span>
            <span class="kc-insight__ytd">{{ selectedItem.ytd_disp }}</span>
          </template>
        </div>
        <div v-if="!compareKeys.length" class="kc-insight__status">
          <span
            v-if="selectedItem.status_disp"
            class="kc-row__status"
            :class="{
              'is-silent': selectedItem.silent,
              'is-near': selectedItem.near_upgrade && !selectedItem.silent,
            }"
            :title="selectedItem.silent ? silentTip : nearTip"
          >{{ selectedItem.status_disp }}</span>
          <span
            v-if="selectedItem.gap_disp && selectedItem.next_tier"
            class="kc-insight__gap"
            :title="nearTip"
          >距{{ selectedItem.next_tier }} {{ selectedItem.gap_disp }}</span>
        </div>
        <div class="kc-insight__actions">
          <button
            type="button"
            class="kc-track__zoom"
            data-testid="kc-compare-toggle-main"
            @click="emit('toggle-compare', selectedItem)"
          >
            {{ isCompared(selectedItem) ? '移出对比' : '加入对比' }}
          </button>
          <button
            type="button"
            class="kc-track__zoom"
            data-testid="kc-track-zoom"
            title="放大查看"
            @click="emit('open-month')"
          >
            放大
          </button>
        </div>
      </div>

      <div v-if="compareKeys.length" class="kc-compare-tags" data-testid="kc-compare-tags">
        <span v-for="ck in compareKeys" :key="'ct' + ck" class="kc-compare-tag">
          {{ findItemByKey(ck)?.name || ck }}
          <button type="button" class="kc-compare-tag__x" @click="emit('remove-compare', ck)">
            ×
          </button>
        </span>
      </div>
      <p v-if="compareHint" class="kc-compare-hint">{{ compareHint }}</p>

      <div class="kc-mode-switch" data-testid="kc-chart-mode">
        <button
          type="button"
          class="kc-chip kc-chip--sm"
          :class="{ 'is-active': chartMode === 'amount' }"
          data-testid="kc-mode-amount"
          @click="emit('set-chart-mode', 'amount')"
        >
          金额对比
        </button>
        <button
          type="button"
          class="kc-chip kc-chip--sm"
          :class="{ 'is-active': chartMode === 'rhythm' }"
          data-testid="kc-mode-rhythm"
          @click="emit('set-chart-mode', 'rhythm')"
        >
          节奏指数
        </button>
      </div>
      <p
        v-if="chartMode === 'rhythm'"
        class="kc-rhythm-disclaimer"
        data-testid="kc-rhythm-disclaimer"
      >
        {{ rhythmDisclaimer }}
      </p>

      <div v-if="selectedTrend && !compareKeys.length" class="kc-trend-summary" data-testid="kc-trend-summary">
        <span>峰值 {{ selectedTrend.peak_disp || '—' }}</span>
        <span>月均 {{ selectedTrend.avg_disp || '—' }}</span>
        <span>{{ selectedTrend.recent_disp || '—' }}</span>
        <span>{{ selectedTrend.silent_complete_disp || '—' }}</span>
        <span v-if="selectedTrend.incomplete_hint" class="kc-trend-summary__hint">{{
          selectedTrend.incomplete_hint
        }}</span>
      </div>

      <div
        v-if="selectedSales.length && trackSeriesCount <= 1"
        class="kc-sales-bars"
        data-testid="kc-sales-bars"
        aria-label="各销售下单构成"
      >
        <div
          v-for="(s, si) in selectedSales"
          :key="'sb' + si + s.name"
          class="kc-sales-bars__row"
        >
          <span class="kc-sales-bars__name" :title="s.name">{{ s.name }}</span>
          <div class="kc-sales-bars__track">
            <div class="kc-sales-bars__fill" :style="{ width: barWidth(s.wo) }" />
          </div>
          <span class="kc-sales-bars__amt">{{ s.amount_disp }}</span>
        </div>
      </div>

      <div class="kc-track" data-testid="kc-track">
        <div class="kc-track__head">
          <div class="kc-section-label kc-track__title" data-testid="kc-track-title">
            {{ trackTitle }}
          </div>
        </div>
        <div class="kc-track-chart" data-testid="kc-track-chart">
          <EchartsHost :option="trackOption" />
        </div>
      </div>
    </template>
  </section>
</template>
