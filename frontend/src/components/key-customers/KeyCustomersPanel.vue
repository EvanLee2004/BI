<script setup lang="ts">
/**
 * 3.5.0 重点客户编排容器 · Layer3
 * fetch/筛选/对比 → useKeyCustomers；图 → keyCustomersChart；子块 props/emits。
 */
import '../../styles/components/KeyCustomersPanel.css'
import SciFiPanel from '../SciFiPanel.vue'
import DataModal from '../base/DataModal.vue'
import RankBar from '../base/RankBar.vue'
import { useKeyCustomers } from '../../composables/useKeyCustomers'
import KeyCustomersSummary from './KeyCustomersSummary.vue'
import KeyCustomersStructure from './KeyCustomersStructure.vue'
import KeyCustomersPool from './KeyCustomersPool.vue'
import KeyCustomersInsight from './KeyCustomersInsight.vue'

const kcApi = useKeyCustomers()
const {
  kc,
  visible,
  selectedItem,
  compareKeys,
  compareHint,
  activePool,
  filterMode,
  searchQ,
  chartMode,
  monthModal,
  monthTitle,
  monthRows,
  cards,
  structureCount,
  structureAmount,
  nearTip,
  silentTip,
  salesColTip,
  guideText,
  dailyOn,
  actionSilent,
  actionNear,
  hasAction,
  rhythmDisclaimer,
  poolLoading,
  poolError,
  poolItemsRaw,
  filteredPoolItems,
  pagedPoolItems,
  listPageInfo,
  listPageRange,
  canPrevListPage,
  canNextListPage,
  prevListPage,
  nextListPage,
  rowDisplayIndex,
  trackSeriesItems,
  trackOption,
  trackTitle,
  insightHeadLabel,
  panelTitle,
  helpLines,
  selectedSales,
  selectedTrend,
  setPool,
  setFilter,
  setChartMode,
  setSearchQ,
  onItemClick,
  onActionClick,
  isSelected,
  isCompared,
  toggleCompare,
  removeCompare,
  clearCompare,
  salesLine,
  barWidth,
  openMonthModal,
  sparkBars,
  customerRowKey,
  findItemByKey,
} = kcApi
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
        <span data-testid="kc-panel-title">{{ panelTitle }}</span>
      </template>

      <div class="kc-help" data-testid="kc-help">
        <p
          v-for="(line, hi) in helpLines"
          :key="'hl' + hi"
          class="kc-help__line"
          :data-testid="hi === 0 ? 'kc-caption' : undefined"
        >
          {{ line }}
        </p>
        <p v-if="dailyOn" class="kc-daily-hint" data-testid="kc-daily-hint">
          日查仅作用于上方排名；本块仍按自然年分级，不随日区间重算。
        </p>
      </div>

      <div class="kc-layout" data-testid="kc-layout">
        <KeyCustomersSummary :cards="cards" :silent-tip="silentTip" :near-tip="nearTip" />
        <KeyCustomersStructure
          :structure-count="structureCount"
          :structure-amount="structureAmount"
          :bar-width="barWidth"
        />

        <div class="kc-workbench" data-testid="kc-workbench">
          <KeyCustomersPool
            :pools="kc?.pools || []"
            :active-pool="activePool"
            :filter-mode="filterMode"
            :search-q="searchQ"
            :pool-loading="poolLoading"
            :pool-error="poolError"
            :pool-items-raw-len="poolItemsRaw.length"
            :filtered-items="filteredPoolItems"
            :paged-items="pagedPoolItems"
            :list-page-info="listPageInfo"
            :list-page-range="listPageRange"
            :can-prev-page="canPrevListPage"
            :can-next-page="canNextListPage"
            :row-display-index="rowDisplayIndex"
            :silent-tip="silentTip"
            :near-tip="nearTip"
            :sales-col-tip="salesColTip"
            :compare-hint="compareHint"
            :is-selected="isSelected"
            :is-compared="isCompared"
            :sales-line="salesLine"
            :spark-bars="sparkBars"
            :customer-row-key="customerRowKey"
            @set-pool="setPool"
            @set-filter="setFilter"
            @update:search-q="setSearchQ"
            @prev-page="prevListPage"
            @next-page="nextListPage"
            @item-click="onItemClick"
            @toggle-compare="toggleCompare"
          />
          <KeyCustomersInsight
            :selected-item="selectedItem"
            :guide-text="guideText"
            :has-action="hasAction"
            :action-silent="actionSilent"
            :action-near="actionNear"
            :silent-tip="silentTip"
            :near-tip="nearTip"
            :compare-keys="compareKeys"
            :compare-hint="compareHint"
            :insight-head-label="insightHeadLabel"
            :selected-trend="selectedTrend"
            :selected-sales="selectedSales"
            :track-series-count="trackSeriesItems.length"
            :track-title="trackTitle"
            :track-option="trackOption as any"
            :chart-mode="chartMode"
            :rhythm-disclaimer="rhythmDisclaimer"
            :is-compared="isCompared"
            :find-item-by-key="findItemByKey"
            :bar-width="barWidth"
            @action-click="onActionClick"
            @toggle-compare="toggleCompare"
            @open-month="openMonthModal"
            @remove-compare="removeCompare"
            @clear-compare="clearCompare"
            @set-chart-mode="setChartMode"
          />
        </div>
      </div>
    </SciFiPanel>

    <DataModal :open="monthModal" :title="monthTitle" @close="monthModal = false">
      <div v-if="!monthRows.length" class="rank-list__empty">暂无月度下单数据</div>
      <div v-else class="kc-month-list" data-testid="kc-month-modal">
        <RankBar
          v-for="it in monthRows"
          :key="'kcm' + (it.i ?? '') + (it.name || '')"
          :rank="it.i ?? 0"
          :name="String(it.name || '')"
          :primary-width="Number(it.rhythm_index ?? it.wo) || 0"
          :primary-value="it.value_disp || it.order_disp"
        />
      </div>
    </DataModal>
  </div>
</template>
