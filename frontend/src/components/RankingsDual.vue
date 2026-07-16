<script setup lang="ts">
/**
 * 板块四：下单/回款双血条。
 * 数据源 = VM.rankings.rankings_view[period]（与 legacy assembleRankings 同源）。
 * 铁律2：只拼 DOM；width% 用后端 wo/wr；金额串用 order_disp/receipt_disp。
 * 禁止绑板块三的利润结构字段。
 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'

const store = useCockpitStore()

type DualItem = {
  i: number
  name: string
  wo?: number
  wr?: number
  order_disp?: string
  receipt_disp?: string
  mkey?: string
}
type DualBlk = {
  title?: string
  dim?: string
  items?: DualItem[]
  others?: { names?: number | string; amt?: string; count?: number | string }
  empty?: boolean
  embed_full?: boolean
  full_items?: DualItem[]
}
type RankView = {
  visible?: boolean
  start?: string
  end?: string
  sales?: DualBlk
  customer?: DualBlk
  monthly_data?: Record<string, DualItem[]>
}

function esc(s: unknown): string {
  return String(s ?? '').replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string,
  )
}

/** wo/wr 已是后端百分比，只做 toFixed 拼 CSS（与 rankings.js 一致，非金额运算） */
function pct(v: unknown): string {
  const n = v == null ? 0 : Number(v)
  return (Number.isFinite(n) ? n : 0).toFixed(1)
}

function dualBarRow(it: DualItem, extraClass = '', titleAttr = '', mkey = ''): string {
  const wo = pct(it.wo)
  const wr = pct(it.wr)
  const cls = 'ev-row dual-row' + (extraClass ? ' ' + extraClass : '')
  const t = titleAttr ? ` title="${esc(titleAttr)}"` : ''
  const dm = mkey ? ` data-mkey="${esc(mkey)}"` : ''
  return (
    `<div class="${cls}"${t}${dm}><span class="rk-no">${it.i}</span>` +
    `<span class="ev-name" title="${esc(it.name)}">${esc(it.name)}</span>` +
    `<div class="dual-bars">` +
    `<span class="dual-bar dual-o" title="下单"><i style="width:${wo}%"></i><em>${esc(it.order_disp)}</em></span>` +
    `<span class="dual-bar dual-r" title="回款"><i style="width:${wr}%"></i><em>${esc(it.receipt_disp)}</em></span>` +
    `</div></div>`
  )
}

function dualRows(items: DualItem[] | undefined, asEntity: boolean): string {
  if (!items || !items.length) return '<div class="ev-empty">本期无数据</div>'
  return items
    .map((it) =>
      asEntity
        ? dualBarRow(it, 'rk-entity', '点开看 1~12 月下单/回款', it.mkey || '')
        : dualBarRow(it),
    )
    .join('')
}

function card(blk: DualBlk | undefined): string {
  if (!blk) return ''
  let body: string
  if (blk.empty) body = '<div class="ev-empty">本期无数据</div>'
  else {
    let more = ''
    if (blk.others) {
      more =
        `<div class="ev-row rk-row rk-others rk-more" title="点开看 10 名以后的完整明细">` +
        `<span class="rk-no">…</span><span class="ev-name">其余 ${esc(blk.others.names)}` +
        ` 个 <span class="rk-open">点开看明细 ›</span></span><span class="ev-track"></span>` +
        `<span class="ev-amt">${esc(blk.others.amt)}</span>` +
        `<span class="rk-meta">${esc(blk.others.count)}笔</span></div>`
    }
    let full = ''
    if (blk.embed_full && blk.full_items && blk.full_items.length) {
      full =
        `<div class="rk-full" hidden><div class="ev-list">${dualRows(blk.full_items, true)}</div></div>`
    }
    body = `<div class="ev-list rk-list">${dualRows(blk.items, true)}${more}</div>${full}`
  }
  const leg =
    `<span class="dual-legend" title="双血条读法">` +
    `<span class="dual-leg dual-o">上·紫=下单</span>` +
    `<span class="dual-leg dual-r">下·青=回款</span></span>`
  return (
    `<div class="card" data-dim="${esc(blk.dim)}"><div class="card-h">${esc(blk.title)}${leg}</div>${body}</div>`
  )
}

const view = computed((): RankView | null => {
  const rk = store.vm?.rankings as
    | { rankings_view?: Record<string, RankView> }
    | undefined
  const map = rk?.rankings_view || {}
  return map[store.period] || null
})

const html = computed(() => {
  const v = view.value
  if (!v || v.visible === false) return ''
  return (
    `<div class="grid-2e dual-grid" data-start="${esc(v.start)}" data-end="${esc(v.end)}">\n` +
    card(v.sales) +
    '\n\n' +
    card(v.customer) +
    '\n\n</div>\n'
  )
})
</script>
<template>
  <div id="rankViews" class="rank-host dual-rankings" data-source="rankings_view" v-html="html"></div>
</template>
