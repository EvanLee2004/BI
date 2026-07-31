<script setup lang="ts">
/**
 * 3.5.0 重点客户编排容器 · Layer3
 * 3.6.2：说明收纳标题旁 ?；结构双饼点扇区联动名单。
 * fetch/筛选/对比 → useKeyCustomers；图 → keyCustomersChart；子块 props/emits。
 */
import { ref } from 'vue'
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
  activeStructureTier,
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
  onStructureTierClick,
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

/** 标题旁 ?：hover 或 click 展开；默认首屏无大段 help */
const helpOpen = ref(false)

function toggleHelp() {
  helpOpen.value = !helpOpen.value
}

function openHelp() {
  helpOpen.value = true
}

function closeHelp() {
  helpOpen.value = false
}
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
        <span class="kc-panel-title-row">
          <span data-testid="kc-panel-title">{{ panelTitle }}</span>
          <span
            class="kc-help-wrap"
            @mouseenter="openHelp"
            @mouseleave="closeHelp"
          >
            <button
              type="button"
              class="kc-help-btn"
              data-testid="kc-help-btn"
              aria-label="分级与口径说明"
              :aria-expanded="helpOpen ? 'true' : 'false'"
              aria-controls="kc-help-popover"
              @click.stop="toggleHelp"
              @focus="openHelp"
            >
              ?
            </button>
            <div
              v-if="helpOpen"
              id="kc-help-popover"
              class="kc-help-popover"
              data-testid="kc-help-popover"
              role="tooltip"
            >
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
          </span>
        </span>
      </template>

      <div class="kc-layout" data-testid="kc-layout">
        <KeyCustomersSummary :cards="cards" :silent-tip="silentTip" :near-tip="nearTip" />
        <KeyCustomersStructure
          :structure-count="structureCount"
          :structure-amount="structureAmount"
          :active-tier="activeStructureTier"
          @tier-click="onStructureTierClick"
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
