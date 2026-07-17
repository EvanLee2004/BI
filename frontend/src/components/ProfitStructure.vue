<script setup lang="ts">
/** 板块三：收入与毛利结构 — 真组件 + 其余弹窗 */
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useCockpitStore } from '../stores/cockpit'

const store = useCockpitStore()

type Item = { i: number; name: string; revenue_disp: string; margin_disp?: string; bar_w?: number }
type Side = {
  title?: string
  dim?: string
  conc_disp?: string
  items?: Item[]
  others?: { names?: number | string; amt_disp?: string; margin_disp?: string }
  empty?: boolean
  full_items?: Item[]
  show_meta?: boolean
}
type Pack = { start?: string; end?: string; customer?: Side; sales?: Side }

const pack = computed((): Pack | null => {
  const r = store.vm?.rankings as { profit_rank_by_period?: Record<string, Pack> } | undefined
  return r?.profit_rank_by_period?.[store.period] || null
})

const modal = ref(false)
const modalTitle = ref('')
const modalItems = ref<Item[]>([])
const showMeta = ref(true)

function openOthers(side: Side) {
  modalTitle.value = (side.title || '') + ' · 完整排名'
  modalItems.value = side.full_items || []
  showMeta.value = !!side.show_meta
  modal.value = true
}
function close() {
  modal.value = false
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>
<template>
  <div>
    <div v-if="pack" id="profitRankViews" class="pr-grid grid-2e" :data-start="pack.start" :data-end="pack.end">
      <div v-for="side in [pack.customer, pack.sales]" :key="side?.dim" class="card" :data-dim="side?.dim">
        <div class="card-h">
          {{ side?.title }}
          <span v-if="side?.conc_disp" class="conc">{{ side.conc_disp }}</span>
          <span class="tag">确认口径</span>
        </div>
        <div v-if="!side || side.empty" class="ev-empty">本期无数据</div>
        <div v-else class="ev-list rk-list">
          <div v-for="it in side.items" :key="it.i + it.name" class="ev-row rk-row">
            <span class="rk-no">{{ it.i }}</span>
            <span class="ev-name" :title="it.name">{{ it.name }}</span>
            <span class="ev-track"><i :style="{ width: (it.bar_w || 0) + '%' }"></i></span>
            <span class="ev-amt">{{ it.revenue_disp }}</span>
            <span v-if="side.show_meta !== false && it.margin_disp" class="rk-meta">{{ it.margin_disp }}</span>
          </div>
          <div
            v-if="side.others"
            class="ev-row rk-row rk-others pr-more"
            @click="openOthers(side)"
          >
            <span class="rk-no">…</span>
            <span class="ev-name"
              >其余 {{ side.others.names }} 个 <span class="rk-open">点开看明细 ›</span></span
            >
            <span class="ev-track"></span>
            <span class="ev-amt">{{ side.others.amt_disp }}</span>
          </div>
        </div>
      </div>
    </div>
    <div class="pr-formula">
      <span class="pr-f-h">计算逻辑</span>
      <span class="pr-f-item"><b>交付金额</b> = 智云含税原数</span>
      <span class="pr-f-item"><b>交付收入</b> = 交付金额 ÷ 1.06</span>
      <span class="pr-f-item"><b>系统成本率</b> = 项目成本 ÷ 交付收入</span>
      <span class="pr-f-item"><b>集中度</b> = 前5大交付收入 ÷ 期内总交付收入</span>
    </div>
    <Teleport to="body">
      <div v-if="modal" class="rkm-mask" style="display: flex" @click.self="close">
        <div class="rkm">
          <div class="rkm-h">
            <b>{{ modalTitle }}</b>
            <button type="button" class="ghost mini" @click="close">关闭</button>
          </div>
          <div class="rkm-list">
            <div class="ev-list">
              <div v-for="it in modalItems" :key="'p' + it.i + it.name" class="ev-row rk-row">
                <span class="rk-no">{{ it.i }}</span>
                <span class="ev-name">{{ it.name }}</span>
                <span class="ev-track"></span>
                <span class="ev-amt">{{ it.revenue_disp }}</span>
                <span v-if="showMeta && it.margin_disp" class="rk-meta">{{ it.margin_disp }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
