<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { jget } from '../api'
import { useClientPager } from '../composables/useClientPager'

type His = { day: string; saved_at?: string }

const list = ref<His[]>([])
const year = ref('')
const month = ref('')
const day = ref('')
const years = ref<string[]>([])
const months = ref<string[]>([])
const days = ref<His[]>([])
const info = ref('')
const frameSrc = ref('about:blank')
const { page, pages, pageRows, pageInfo, resetPage, prevPage, nextPage } = useClientPager(days)

async function load() {
  try {
    list.value = await jget('/api/history')
    if (!list.value.length) {
      info.value = '还没有历史快照（每次更新后自动生成，明天起就有了）'
      frameSrc.value = 'about:blank'
      years.value = []
      days.value = []
      return
    }
    info.value = '共 ' + list.value.length + ' 天'
    years.value = [...new Set(list.value.map((x) => x.day.slice(0, 4)))]
    year.value = years.value[0] || ''
    fillM()
  } catch (e) {
    info.value = '加载失败:' + String(e)
  }
}

function fillM() {
  months.value = [
    ...new Set(list.value.filter((x) => x.day.slice(0, 4) === year.value).map((x) => x.day.slice(4, 6))),
  ]
  month.value = months.value[0] || ''
  fillD()
}

function fillD() {
  days.value = list.value.filter((x) => x.day.slice(0, 4) === year.value && x.day.slice(4, 6) === month.value)
  resetPage()
  day.value = days.value[0]?.day || ''
  if (day.value) show(day.value)
}

function show(d: string) {
  day.value = d
  frameSrc.value = '/api/history/' + d
}

watch([year, month], () => {
  /* year/month changed via select handlers */
})

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <span>展示哪天</span>
      <el-select v-model="year" style="width: 100px" @change="fillM">
        <el-option v-for="y in years" :key="y" :label="y + '年'" :value="y" />
      </el-select>
      <el-select v-model="month" style="width: 90px" @change="fillD">
        <el-option v-for="m in months" :key="m" :label="Number(m) + '月'" :value="m" />
      </el-select>
      <el-select v-model="day" style="width: 240px" @change="show(day)">
        <el-option
          v-for="x in days"
          :key="x.day"
          :label="Number(x.day.slice(6)) + '日（存于 ' + (x.saved_at || '') + '）'"
          :value="x.day"
        />
      </el-select>
      <span class="muted">{{ info }} · 本月 {{ pageInfo }}</span>
      <el-button size="small" :disabled="page <= 1" @click="prevPage">上一页</el-button>
      <el-button size="small" :disabled="page >= pages" @click="nextPage">下一页</el-button>
    </div>
    <div class="admin-note">每天更新完自动存一份当天页面（同天多次=留最后一次）；月末那天随月末快照永久保留。</div>
    <el-table
      :data="pageRows"
      border
      stripe
      size="small"
      style="margin-bottom: 10px; max-width: 520px"
      highlight-current-row
      @row-click="(row: His) => show(row.day)"
    >
      <el-table-column label="日期" width="120">
        <template #default="{ row }">{{ row.day }}</template>
      </el-table-column>
      <el-table-column label="存于" min-width="180">
        <template #default="{ row }">{{ row.saved_at || '—' }}</template>
      </el-table-column>
      <el-table-column label="" width="80">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click.stop="show(row.day)">打开</el-button>
        </template>
      </el-table-column>
    </el-table>
    <iframe class="admin-iframe" :src="frameSrc" title="历史快照" />
  </div>
</template>

<style scoped>
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
.muted { color: var(--admin-mut, #94a3b8); font-size: 13px; }
</style>
