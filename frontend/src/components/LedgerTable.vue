<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useCockpitStore } from '../stores/cockpit'

const store = useCockpitStore()
const info = ref('')
const tbl = ref<HTMLTableElement | null>(null)

onMounted(async () => {
  try {
    const u = '/api/detail?table=' + encodeURIComponent('费用明细') + '&page=1&page_size=50'
    const r = await fetch(u, { credentials: 'same-origin' })
    if (!r.ok) {
      info.value = '无权限或加载失败'
      return
    }
    const d = await r.json()
    info.value = '共 ' + (d.total || 0) + ' 行'
    const cols: string[] = d.columns || []
    let h = '<tr>' + cols.map((c) => '<th>' + c + '</th>').join('') + '</tr>'
    for (const row of d.rows || []) {
      h +=
        '<tr>' +
        cols
          .map((c) => {
            const cls = /金额|含税/.test(c) ? 'num' : /事项/.test(c) ? 'col-flex' : ''
            return '<td class="' + cls + '">' + String(row[c] ?? '') + '</td>'
          })
          .join('') +
        '</tr>'
    }
    if (tbl.value) tbl.value.innerHTML = h
  } catch (e) {
    info.value = String(e)
  }
})
</script>
<template>
  <div class="card">
    <div class="card-h">费用明细 <span class="tag">{{ info }}</span></div>
    <div class="ledger-scroll">
      <table class="bu-ledger cock-ledger" ref="tbl"></table>
    </div>
  </div>
</template>
