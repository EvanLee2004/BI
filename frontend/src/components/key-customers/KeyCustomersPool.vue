<script setup lang="ts">
import type { KeyCustomersItem, KeyCustomersVM } from '../../types/vm'
import type { FilterMode, PoolId } from '../../composables/useKeyCustomers'

defineProps<{
  pools: NonNullable<KeyCustomersVM['pools']>
  activePool: PoolId
  filterMode: FilterMode
  searchQ: string
  poolLoading: boolean
  poolError: string
  poolItemsRawLen: number
  /** 过滤后全量（空态判断） */
  filteredItems: KeyCustomersItem[]
  /** 当前页切片 */
  pagedItems: KeyCustomersItem[]
  listPageInfo: string
  listPageRange: string
  canPrevPage: boolean
  canNextPage: boolean
  rowDisplayIndex: (localIndex: number) => number
  silentTip: string
  nearTip: string
  salesColTip: string
  compareHint: string
  isSelected: (it: KeyCustomersItem) => boolean
  isCompared: (it: KeyCustomersItem) => boolean
  salesLine: (it: KeyCustomersItem) => { text: string; title: string }
  sparkBars: (it: KeyCustomersItem) => number[]
  customerRowKey: (it: KeyCustomersItem) => string
}>()

const emit = defineEmits<{
  'set-pool': [pid: PoolId]
  'set-filter': [m: FilterMode]
  'update:searchQ': [v: string]
  'prev-page': []
  'next-page': []
  'item-click': [it: KeyCustomersItem]
  'toggle-compare': [it: KeyCustomersItem]
}>()
</script>

<template>
  <section class="kc-pool" data-testid="kc-pool" aria-label="客户池">
    <div class="kc-pool__tabs" role="tablist">
      <button
        v-for="p in pools"
        :key="p.id"
        type="button"
        class="kc-chip"
        role="tab"
        :class="{ 'is-active': activePool === p.id }"
        :data-testid="'kc-pool-tab-' + p.id"
        :aria-selected="activePool === p.id ? 'true' : 'false'"
        @click="emit('set-pool', p.id as PoolId)"
      >
        {{ p.label }}
        <span class="kc-chip__hint">{{ p.hint }}</span>
        <span class="kc-chip__meta">{{ p.count_disp }}</span>
      </button>
    </div>
    <div class="kc-pool__filters">
      <button
        type="button"
        class="kc-chip kc-chip--sm"
        :class="{ 'is-active': filterMode === 'all' }"
        data-testid="kc-filter-all"
        @click="emit('set-filter', 'all')"
      >
        全部
      </button>
      <button
        type="button"
        class="kc-chip kc-chip--sm"
        :class="{ 'is-active': filterMode === 'silent' }"
        data-testid="kc-filter-silent"
        @click="emit('set-filter', 'silent')"
      >
        需跟进
      </button>
      <button
        type="button"
        class="kc-chip kc-chip--sm"
        :class="{ 'is-active': filterMode === 'near' }"
        data-testid="kc-filter-near"
        :title="nearTip"
        @click="emit('set-filter', 'near')"
      >
        临界晋级
      </button>
      <input
        :value="searchQ"
        type="search"
        class="kc-search"
        data-testid="kc-search"
        placeholder="搜索客户名"
        aria-label="搜索客户名"
        @input="emit('update:searchQ', ($event.target as HTMLInputElement).value)"
      />
      <!-- 3.6.1：搜索框右侧分页 -->
      <div
        v-if="filteredItems.length > 0"
        class="kc-pager"
        data-testid="kc-pager"
        role="navigation"
        :aria-label="listPageInfo"
      >
        <button
          type="button"
          class="kc-chip kc-chip--sm kc-pager__btn"
          data-testid="kc-page-prev"
          :disabled="!canPrevPage"
          aria-label="上一页"
          @click="emit('prev-page')"
        >
          上一页
        </button>
        <span class="kc-pager__info" data-testid="kc-page-info">{{ listPageRange }}</span>
        <button
          type="button"
          class="kc-chip kc-chip--sm kc-pager__btn"
          data-testid="kc-page-next"
          :disabled="!canNextPage"
          aria-label="下一页"
          @click="emit('next-page')"
        >
          下一页
        </button>
      </div>
    </div>
    <div class="kc-pool__list" data-testid="kc-pool-list">
      <div v-if="poolLoading" class="kc-tier__loading">加载中…</div>
      <div v-else-if="poolError" class="kc-tier__err">{{ poolError }}</div>
      <div v-else-if="!filteredItems.length" class="kc-tier__empty">
        {{ poolItemsRawLen ? '无匹配客户' : '该池暂无客户' }}
      </div>
      <template v-else>
        <div
          v-for="(it, idx) in pagedItems"
          :key="customerRowKey(it)"
          class="kc-row"
          :class="{
            'is-selected': isSelected(it),
            'is-compare': isCompared(it),
          }"
          data-testid="kc-customer-row"
        >
          <button
            type="button"
            class="kc-row__main"
            :aria-pressed="isSelected(it) ? 'true' : 'false'"
            @click="emit('item-click', it)"
          >
            <span class="kc-row__name" :title="it.name">
              <span
                class="kc-row__idx"
                data-testid="kc-row-idx"
                :aria-label="'第' + rowDisplayIndex(idx) + '名'"
              >{{ rowDisplayIndex(idx) }}</span>
              <span class="kc-row__tier" :data-tier="it.tier">{{ it.tier }}</span>
              {{ it.name }}
              <span
                v-if="it.status_disp"
                class="kc-row__status"
                :class="{
                  'is-silent': it.silent,
                  'is-near': it.near_upgrade && !it.silent,
                }"
                :title="it.silent ? silentTip : nearTip"
              >{{ it.status_disp }}</span>
            </span>
            <span class="kc-row__sales" :title="salesLine(it).title || salesColTip">{{
              salesLine(it).text
            }}</span>
            <span class="kc-row__ytd">{{ it.ytd_disp }}</span>
            <span v-if="sparkBars(it).length" class="kc-spark" aria-hidden="true">
              <i
                v-for="(w, si) in sparkBars(it)"
                :key="'sp' + si"
                class="kc-spark__bar"
                :style="{ height: `${Math.max(0, Math.min(100, Number(w) || 0))}%` }"
              />
            </span>
          </button>
          <button
            type="button"
            class="kc-row__cmp"
            data-testid="kc-compare-toggle"
            :aria-pressed="isCompared(it) ? 'true' : 'false'"
            :title="isCompared(it) ? '移出对比' : '加入对比'"
            @click.stop="emit('toggle-compare', it)"
          >
            {{ isCompared(it) ? '移出' : '对比' }}
          </button>
        </div>
      </template>
    </div>
    <p v-if="compareHint" class="kc-compare-hint" data-testid="kc-compare-hint">
      {{ compareHint }}
    </p>
  </section>
</template>
