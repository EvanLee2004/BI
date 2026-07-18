<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { jget } from '../api'

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

async function load() {
  try {
    list.value = await jget('/api/history')
    if (!list.value.length) {
      info.value = '还没有历史快照（每次更新后自动生成，明天起就有了）'
      frameSrc.value = 'about:blank'
      years.value = []
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
  day.value = days.value[0]?.day || ''
  if (day.value) show(day.value)
}

function show(d: string) {
  day.value = d
  frameSrc.value = '/api/history/' + d
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <span>看哪天</span>
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
      <span class="muted">{{ info }}</span>
    </div>
    <div class="admin-note">每天更新完自动存一份当天页面（同天多次=留最后一次）；月末那天随月末快照永久保留。</div>
    <iframe class="admin-iframe" :src="frameSrc" title="历史快照" />
  </div>
</template>

<style scoped>
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
.muted { color: var(--admin-mut, #94a3b8); font-size: 13px; }
</style>
