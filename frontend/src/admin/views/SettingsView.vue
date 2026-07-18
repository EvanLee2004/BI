<script setup lang="ts">
import { inject, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { jget, jpost, downloadBlob } from '../api'
import { SRC_MAP, salesArr } from '../utils'

const reloadDash = inject<() => void>('reloadDash', () => {})
const health = inject<{ value: Record<string, unknown> | null }>('adminHealth', ref(null) as never)

// —— 版本 ——
const verNum = ref('v…')
const verStage = ref('')
const verNext = ref('')
const verLog = ref<{ title?: string; date?: string; items?: string[] }[]>([])
const verDrawer = ref(false)
const vuMsg = ref('')
const vuAvail = ref('')
const canUpdate = ref(false)
const updatePayload = ref<Record<string, unknown> | null>(null)

// —— 设置表单 ——
const scheduleTimes = ref<string[]>(['09:30'])
const sKeep = ref(30)
const sFeishuHook = ref('')
const sLogKeep = ref(365)
const sDiskMin = ref(10)
const sArchYear = ref(new Date().getFullYear())
const sArchMsg = ref('')
const sBakInfo = ref('')
const sZyUser = ref('')
const sZyPwd = ref('')
const sLedgerPath = ref('')
const sOverallSalary = ref(false)
const sZyUrl = ref('')
const sTblOrders = ref('')
const sTblReceipts = ref('')
const sTblProject = ref('')
const sTblInhouse = ref('')
const srcRows = ref<{ name: string; src: string; rows: string }[]>([])

const dirty = reactive(new Set<string>())
const setMsgs = reactive<Record<string, string>>({
  sched: '',
  backup: '',
  alert: '',
  zy: '',
  acct: '',
  bu: '',
})
const saving = ref(false)

function mark(k: string) {
  dirty.add(k)
}

// —— 账号 ——
type Acct = {
  账号: string
  显示名?: string
  权限?: string
  密码?: string
  初始密码?: boolean
  最后登录?: string
  可见BU?: string[]
}
const acctList = ref<Acct[]>([])
const acctPwShow = ref<Record<number, boolean>>({})
const masterAccount = ref('lushasha')

// —— BU ——
type BuItem = { name: string; 负责人: string[] | string; 销售: string[]; 分摊比例: number | null }
const buList = ref<BuItem[]>([])
const salesPool = ref<{ name: string; ref_disp?: string }[]>([])
const buPicked = ref<Set<string>>(new Set())
const buUnassigned = ref<{ unassigned_count?: number; unassigned_orders_disp?: string }>({})
const buAllocLegacy = ref(false)
const dragName = ref('')

async function loadVersion() {
  try {
    const v = await jget<{ version?: string; stage?: string; changelog?: { title?: string; date?: string; items?: string[] }[] }>(
      '/api/version',
    )
    verNum.value = 'v' + String(v.version || '?').split('-')[0]
    verStage.value = v.stage || ''
    verNext.value =
      verStage.value === '试运行'
        ? '· 正式上线后升 v1.0'
        : verStage.value === '公测 Beta'
          ? '· 公测通过后去掉 Beta 升 v1.0 正式版'
          : ''
    verLog.value = v.changelog || []
  } catch {
    verNum.value = '版本?'
  }
}

async function checkUpdate() {
  vuMsg.value = '检查中…（联网比对远端）'
  vuAvail.value = ''
  updatePayload.value = null
  try {
    const d = await jget<{
      supported?: boolean
      available?: boolean
      reason?: string
      local?: string
      remote_rev?: string
      behind?: number
      remote?: string
      log?: string[]
      can_update?: boolean
    }>('/api/update/check')
    if (!d.supported) {
      vuMsg.value = d.reason || '一键更新不可用'
      return
    }
    if (!d.available) {
      vuMsg.value = '✓ ' + (d.reason || '已是最新版本') + (d.local ? '（当前 ' + d.local + '）' : '')
      return
    }
    vuMsg.value = ''
    updatePayload.value = d as Record<string, unknown>
    canUpdate.value = !!d.can_update
    vuAvail.value = `发现新版本 · 落后 ${d.behind || 0} 个提交（${d.local || ''} → ${d.remote_rev || ''}）`
  } catch (e) {
    vuMsg.value = '检查失败：' + String(e)
  }
}

async function applyUpdate() {
  try {
    await ElMessageBox.confirm('确认一键更新？将拉取新代码并重启服务（约 10 秒内不可用）。', '一键更新')
  } catch {
    return
  }
  vuAvail.value = '更新中…拉取新代码…'
  try {
    const d = await jpost<{ ok?: boolean; from?: string; to?: string; reason?: string }>('/api/update/apply', {})
    if (d.ok) {
      vuAvail.value = `✓ 已拉取 ${d.from || ''} → ${d.to || ''}，服务重启中…`
      setTimeout(() => location.reload(), 12000)
    } else {
      vuAvail.value = '未更新：' + (d.reason || '')
    }
  } catch {
    vuAvail.value = '更新请求已发出，服务可能正在重启…'
    setTimeout(() => location.reload(), 12000)
  }
}

async function loadSettings() {
  try {
    const s = await jget<{
      schedule_times?: string[]
      schedule_time?: string
      backup_keep_days?: number
      zhiyun_username?: string
      zhiyun_password?: string
      ledger_share_path?: string
      overall_see_salary?: boolean
      feishu_webhook_url?: string
      run_log_keep_days?: number
      disk_free_min_ratio?: number
      zhiyun_conn?: { base_url?: string; tables?: Record<string, string> }
      backup_stats?: { count?: number; mb?: number }
    }>('/api/settings')
    scheduleTimes.value =
      s.schedule_times && s.schedule_times.length ? s.schedule_times.slice() : [s.schedule_time || '09:30']
    sKeep.value = s.backup_keep_days || 30
    sZyUser.value = s.zhiyun_username || ''
    sZyPwd.value = s.zhiyun_password || ''
    sLedgerPath.value = s.ledger_share_path || ''
    sOverallSalary.value = !!s.overall_see_salary
    sFeishuHook.value = s.feishu_webhook_url || ''
    sLogKeep.value = s.run_log_keep_days != null ? s.run_log_keep_days : 365
    sDiskMin.value =
      s.disk_free_min_ratio != null ? Math.round(Number(s.disk_free_min_ratio) * 100) : 10
    const zc = s.zhiyun_conn || {}
    const zt = zc.tables || {}
    sZyUrl.value = zc.base_url || ''
    sTblOrders.value = zt.orders || ''
    sTblReceipts.value = zt.receipts || ''
    sTblProject.value = zt.project_detail || ''
    sTblInhouse.value = zt.inhouse || ''
    const b = s.backup_stats || {}
    sBakInfo.value = '当前备份：' + (b.count || 0) + ' 份，共 ' + (b.mb || 0) + ' MB'
    const rows: Record<string, number> = {}
    ;(((health as { value?: { sources?: { name: string; rows: number }[] } })?.value?.sources) || []).forEach(
      (x) => {
        rows[x.name] = x.rows
      },
    )
    srcRows.value = SRC_MAP.map(([n, src]) => ({
      name: n,
      src,
      rows: rows[n] != null ? String(rows[n]) : '—',
    }))
  } catch (e) {
    ElMessage.error('读取设置失败:' + String(e))
  }
}

function schedAdd() {
  if (scheduleTimes.value.length >= 6) {
    setMsgs.sched = '最多 6 个时间点'
    return
  }
  scheduleTimes.value.push('12:00')
  mark('sched')
}
function schedDel(i: number) {
  if (scheduleTimes.value.length <= 1) return
  scheduleTimes.value.splice(i, 1)
  mark('sched')
}

async function exportArchive() {
  sArchMsg.value = '导出中…'
  try {
    await downloadBlob(
      '/api/archive_export?year=' + encodeURIComponent(String(sArchYear.value)),
      '审计归档_' + sArchYear.value + '.xlsx',
    )
    sArchMsg.value = '✓ 已下载 ' + sArchYear.value + ' 年归档（库内未删）'
  } catch (e) {
    sArchMsg.value = '失败：' + String(e)
  }
}

// —— 账号 ——
function permType(a: Acct) {
  const p = a.权限 || ''
  if (p === '管理员') return '管理员'
  if (p === '整体') return '整体'
  return 'BU'
}
function isMaster(a: Acct) {
  return String(a.账号 || '').trim() === masterAccount.value
}
function adminCount() {
  return acctList.value.filter((a) => (a.权限 || '') === '管理员').length
}
function acctAdd() {
  acctList.value.push({ 账号: '', 显示名: '', 权限: '整体', 密码: '8888', 初始密码: true, 最后登录: '' })
  mark('acct')
}
function acctDel(i: number) {
  const a = acctList.value[i]
  if (isMaster(a)) {
    ElMessage.warning('总账号「' + masterAccount.value + '」永久不可删除')
    return
  }
  if ((a.权限 || '') === '管理员' && adminCount() <= 1) {
    ElMessage.warning('至少保留一个管理员')
    return
  }
  ElMessageBox.confirm('删除该账号？立即失效', '确认').then(() => {
    acctList.value.splice(i, 1)
    mark('acct')
  }).catch(() => {})
}
async function loadAccts() {
  try {
    const d = await jget<{ accounts?: Acct[]; master_account?: string }>('/api/accounts')
    acctList.value = d.accounts || []
    if (d.master_account) masterAccount.value = d.master_account
    acctPwShow.value = {}
  } catch (e) {
    setMsgs.acct = '读取失败:' + String(e)
  }
}

// —— BU ——
function claimedSales() {
  const s = new Set<string>()
  buList.value.forEach((b) => salesArr(b.销售).forEach((x) => s.add(x)))
  return s
}
const poolNames = () => {
  const claimed = claimedSales()
  return salesPool.value.map((p) => p.name).filter((n) => !claimed.has(n))
}
function buAdd() {
  buList.value.push({ name: '', 负责人: [], 销售: [], 分摊比例: null })
  mark('bu')
}
function buDel(i: number) {
  ElMessageBox.confirm('删除该 BU？销售回未归属池', '确认').then(() => {
    buList.value.splice(i, 1)
    mark('bu')
  }).catch(() => {})
}
function moveToPool(name: string) {
  if (!name) return
  buList.value.forEach((b) => {
    b.销售 = salesArr(b.销售).filter((s) => s !== name)
  })
  mark('bu')
}
function moveToBu(i: number, name: string) {
  if (!name || i < 0 || i >= buList.value.length) return
  buList.value.forEach((b) => {
    b.销售 = salesArr(b.销售).filter((s) => s !== name)
  })
  const cur = salesArr(buList.value[i].销售)
  if (cur.indexOf(name) < 0) cur.push(name)
  buList.value[i].销售 = cur
  mark('bu')
}
function onDragStart(name: string, e: DragEvent) {
  dragName.value = name
  e.dataTransfer?.setData('text/plain', name)
  e.dataTransfer!.effectAllowed = 'move'
}
function onDropPool(e: DragEvent) {
  e.preventDefault()
  const name = (e.dataTransfer?.getData('text/plain') || dragName.value || '').trim()
  if (name) moveToPool(name)
  dragName.value = ''
}
function onDropBu(i: number, e: DragEvent) {
  e.preventDefault()
  const name = (e.dataTransfer?.getData('text/plain') || dragName.value || '').trim()
  if (name) moveToBu(i, name)
  dragName.value = ''
}
function togglePick(name: string, on: boolean) {
  const s = new Set(buPicked.value)
  if (on) s.add(name)
  else s.delete(name)
  buPicked.value = s
}
const pickTo = ref('__pool__')
function applyBatch() {
  const names = Array.from(buPicked.value)
  if (!names.length) return
  names.forEach((n) => {
    buList.value.forEach((b) => {
      b.销售 = salesArr(b.销售).filter((s) => s !== n)
    })
    if (pickTo.value !== '__pool__') {
      const i = +pickTo.value
      if (i >= 0 && i < buList.value.length) {
        const cur = salesArr(buList.value[i].销售)
        if (cur.indexOf(n) < 0) cur.push(n)
        buList.value[i].销售 = cur
      }
    }
  })
  buPicked.value = new Set()
  mark('bu')
  setMsgs.bu = `已批量指定 ${names.length} 人——点底部保存生效`
}
function buAllocEnabled() {
  return buList.value.some((b) => b.分摊比例 != null && b.分摊比例 !== ('' as unknown) && !isNaN(Number(b.分摊比例)))
}
async function loadBuCfg() {
  try {
    type PoolRes = {
      sales?: { name: string; ref_disp?: string }[]
      unassigned_count?: number
      unassigned_orders_disp?: string
    }
    const [d, pool] = await Promise.all([
      jget<{ bus?: BuItem[]; 公共费用分摊启用?: boolean }>('/api/bu_config'),
      jget<PoolRes>('/api/sales_pool').catch((): PoolRes => ({ sales: [] })),
    ])
    buList.value = (d.bus || []).map((b) => ({
      name: b.name,
      负责人: b.负责人 || [],
      销售: salesArr(b.销售),
      分摊比例: b.分摊比例 == null || !d.公共费用分摊启用 ? null : Number(b.分摊比例),
    }))
    salesPool.value = pool.sales || []
    buPicked.value = new Set()
    buUnassigned.value = {
      unassigned_count: pool.unassigned_count || 0,
      unassigned_orders_disp: pool.unassigned_orders_disp || '',
    }
    buAllocLegacy.value = buAllocEnabled()
  } catch (e) {
    setMsgs.bu = '读取失败:' + String(e)
  }
}

async function saveSchedule() {
  setMsgs.sched = '保存中…'
  const times = scheduleTimes.value.map((t) => String(t || '').trim()).filter(Boolean)
  if (!times.length) {
    setMsgs.sched = '至少保留一个时间点'
    return false
  }
  try {
    const d = await jpost<{ schedule_times?: string[]; note?: string }>('/api/settings', { schedule_times: times })
    if (d.schedule_times?.length) scheduleTimes.value = d.schedule_times.slice()
    setMsgs.sched = d.note || '已保存'
    return true
  } catch (e) {
    setMsgs.sched = '失败：' + String(e)
    return false
  }
}
async function saveBackup() {
  setMsgs.backup = '保存中…'
  try {
    const d = await jpost<{ note?: string }>('/api/settings', { backup_keep_days: sKeep.value })
    setMsgs.backup = d.note || '已保存'
    return true
  } catch (e) {
    setMsgs.backup = '失败：' + String(e)
    return false
  }
}
async function saveAlert() {
  setMsgs.alert = '保存中…'
  const pct = sDiskMin.value || 10
  try {
    const d = await jpost<{ note?: string }>('/api/settings', {
      feishu_webhook_url: sFeishuHook.value,
      run_log_keep_days: sLogKeep.value,
      disk_free_min_ratio: pct * 1e-2,
    })
    setMsgs.alert = d.note || '已保存'
    return true
  } catch (e) {
    setMsgs.alert = '失败：' + String(e)
    return false
  }
}
async function saveZhiyun() {
  setMsgs.zy = '保存中…'
  const p: Record<string, unknown> = { ledger_share_path: sLedgerPath.value, overall_see_salary: !!sOverallSalary.value }
  if (sZyUser.value || sZyPwd.value) {
    p.zhiyun_username = sZyUser.value
    p.zhiyun_password = sZyPwd.value
  }
  if (sZyUrl.value) {
    p.zhiyun_base_url = sZyUrl.value
    p.zhiyun_tables = {
      orders: sTblOrders.value,
      receipts: sTblReceipts.value,
      project_detail: sTblProject.value,
      inhouse: sTblInhouse.value,
    }
  }
  try {
    const d = await jpost<{ note?: string }>('/api/settings', p)
    setMsgs.zy = d.note || '已保存'
    return true
  } catch (e) {
    setMsgs.zy = '失败：' + String(e)
    return false
  }
}
async function saveAccts() {
  setMsgs.acct = '保存中…'
  if (!adminCount()) {
    setMsgs.acct = '保存失败：至少保留一个管理员'
    return false
  }
  if (!acctList.value.some((a) => String(a.账号 || '').trim() === masterAccount.value)) {
    setMsgs.acct = '保存失败：总账号不可删除'
    return false
  }
  try {
    const d = await jpost<{ accounts?: Acct[]; master_account?: string; note?: string; count?: number }>('/api/accounts', {
      accounts: acctList.value,
    })
    acctList.value = d.accounts || []
    if (d.master_account) masterAccount.value = d.master_account
    setMsgs.acct = (d.note || '已保存') + '（共 ' + d.count + ' 个）'
    return true
  } catch (e) {
    setMsgs.acct = '保存失败：' + String(e)
    return false
  }
}
async function saveBu() {
  setMsgs.bu = '保存并重算中…'
  try {
    const payload = buList.value.map((b) => ({
      name: b.name,
      负责人: b.负责人,
      销售: salesArr(b.销售),
      分摊比例: b.分摊比例,
    }))
    const d = await jpost<{ bus?: BuItem[]; 公共费用分摊启用?: boolean; note?: string; count?: number }>('/api/bu_config', {
      bus: payload,
      公共费用分摊启用: buAllocEnabled(),
    })
    buList.value = (d.bus || []).map((b) => ({
      name: b.name,
      负责人: b.负责人 || [],
      销售: salesArr(b.销售),
      分摊比例: b.分摊比例 == null || !d.公共费用分摊启用 ? null : Number(b.分摊比例),
    }))
    setMsgs.bu = (d.note || '已保存') + '（共 ' + d.count + ' 个 BU）'
    reloadDash()
    return true
  } catch (e) {
    setMsgs.bu = '保存失败：' + String(e)
    return false
  }
}

async function saveAll() {
  saving.value = true
  const jobs: [string, () => Promise<boolean>][] = [
    ['sched', saveSchedule],
    ['backup', saveBackup],
    ['alert', saveAlert],
    ['zy', saveZhiyun],
    ['acct', saveAccts],
    ['bu', saveBu],
  ]
  let fail = 0
  for (const [k, fn] of jobs) {
    if (!dirty.has(k)) continue
    let ok = false
    try {
      ok = await fn()
    } catch {
      ok = false
    }
    if (ok) dirty.delete(k)
    else fail++
  }
  saving.value = false
  if (fail) ElMessage.error('有 ' + fail + ' 处设置保存失败')
  else ElMessage.success('✓ 设置已保存')
}

function discard() {
  dirty.clear()
  loadSettings()
  loadAccts()
  loadBuCfg()
  ElMessage.info('已放弃未保存的设置更改')
}

function ownerStr(b: BuItem) {
  return Array.isArray(b.负责人) ? b.负责人.join('、') : String(b.负责人 || '')
}
function setOwner(b: BuItem, v: string) {
  b.负责人 = v
  mark('bu')
}
function onPermType(row: Acct, v: string) {
  row.权限 = v
  if (v !== 'BU') row.可见BU = []
  mark('acct')
}
function onBuVisible(row: Acct, bn: string, on: boolean) {
  const s = new Set(row.可见BU || [])
  if (on) s.add(bn)
  else s.delete(bn)
  row.可见BU = Array.from(s)
  row.权限 = 'BU'
  mark('acct')
}

onMounted(async () => {
  await Promise.all([loadVersion(), loadSettings(), loadAccts(), loadBuCfg()])
})
</script>

<template>
  <div class="settings">
    <el-row :gutter="16">
      <!-- 版本 -->
      <el-col :span="24">
        <el-card shadow="never" class="scard">
          <template #header>
            <div class="scard-h"><span class="ico">🧭</span><div><div class="ttl">版本与更新</div><div class="sub">检查更新 / 一键更新 / 更新日志</div></div></div>
          </template>
          <div class="ver-now">
            <span class="num">{{ verNum }}</span>
            <el-tag size="small" style="margin-left: 8px">{{ verStage }}</el-tag>
            <span class="muted" style="margin-left: 8px">{{ verNext }}</span>
          </div>
          <div style="margin-top: 10px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap">
            <el-button size="small" @click="checkUpdate">检查更新</el-button>
            <el-button size="small" text @click="verDrawer = true">更新日志 ›</el-button>
            <span class="muted">{{ vuMsg }}</span>
          </div>
          <div v-if="vuAvail" class="vu-box">
            <div>{{ vuAvail }}</div>
            <ul v-if="updatePayload?.log">
              <li v-for="(s, i) in (updatePayload.log as string[])" :key="i">{{ s }}</li>
            </ul>
            <el-button v-if="canUpdate" type="primary" size="small" style="margin-top: 8px" @click="applyUpdate">一键更新并重启</el-button>
            <div v-else-if="updatePayload" class="muted" style="color: #fbbf24; margin-top: 6px">
              ⚠ {{ (updatePayload.reason as string) || '当前不满足自动更新条件' }}
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 自动更新 -->
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="scard" @input="mark('sched')" @change="mark('sched')">
          <template #header>
            <div class="scard-h"><span class="ico">⏰</span><div><div class="ttl">自动更新</div><div class="sub">每天多个时间点完整更新</div></div></div>
          </template>
          <div v-for="(t, i) in scheduleTimes" :key="i" class="sched-row">
            <el-time-select v-model="scheduleTimes[i]" start="00:00" step="00:30" end="23:30" placeholder="时间" style="width: 120px" @change="mark('sched')" />
            <el-button v-if="scheduleTimes.length > 1" text size="small" @click="schedDel(i)">✕</el-button>
          </div>
          <el-button size="small" text style="margin-top: 8px" @click="schedAdd">＋ 添加时间点</el-button>
          <div class="muted foot">{{ setMsgs.sched }}</div>
        </el-card>
      </el-col>

      <!-- 备份 -->
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="scard">
          <template #header>
            <div class="scard-h"><span class="ico">🗄</span><div><div class="ttl">备份清理 · 审计归档</div><div class="sub">备份保留天数 + 按年导出</div></div></div>
          </template>
          <div class="field-row">
            <span>备份保留</span>
            <el-input-number v-model="sKeep" :min="1" :max="365" @change="mark('backup')" />
            <span class="muted">天</span>
          </div>
          <div class="muted">{{ sBakInfo }}</div>
          <div class="field-row" style="margin-top: 12px">
            <span>导出归档年份</span>
            <el-input-number v-model="sArchYear" :min="2020" :max="2099" controls-position="right" />
            <el-button size="small" @click="exportArchive">导出归档 Excel</el-button>
          </div>
          <div class="muted">{{ sArchMsg || setMsgs.backup }}</div>
        </el-card>
      </el-col>

      <!-- 飞书告警 -->
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="scard">
          <template #header>
            <div class="scard-h"><span class="ico">📣</span><div><div class="ttl">飞书告警</div><div class="sub">体检红 / 回滚 / 连崩推送</div></div></div>
          </template>
          <el-form label-position="top">
            <el-form-item label="自定义机器人 Webhook">
              <el-input v-model="sFeishuHook" type="password" show-password placeholder="https://open.feishu.cn/..." @input="mark('alert')" />
            </el-form-item>
            <el-form-item label="运行日志保留（天）">
              <el-input-number v-model="sLogKeep" :min="30" :max="3650" @change="mark('alert')" />
            </el-form-item>
            <el-form-item label="磁盘告警阈值（% 剩余以下体检红）">
              <el-input-number v-model="sDiskMin" :min="1" :max="50" @change="mark('alert')" />
            </el-form-item>
          </el-form>
          <div class="muted">{{ setMsgs.alert }}</div>
        </el-card>
      </el-col>

      <!-- 智云 -->
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="scard">
          <template #header>
            <div class="scard-h"><span class="ico">🔑</span><div><div class="ttl">智云账号 · 台账路径</div><div class="sub">只存本机，不进代码库</div></div></div>
          </template>
          <el-form label-position="top">
            <el-form-item label="智云账号">
              <el-input v-model="sZyUser" type="password" show-password @input="mark('zy')" />
            </el-form-item>
            <el-form-item label="智云密码">
              <el-input v-model="sZyPwd" type="password" show-password @input="mark('zy')" />
            </el-form-item>
            <el-form-item label="收单台账共享盘路径">
              <el-input v-model="sLedgerPath" placeholder="共享盘路径" @input="mark('zy')" />
            </el-form-item>
            <el-checkbox v-model="sOverallSalary" @change="mark('zy')">整体账号可见工资明细</el-checkbox>
            <el-collapse style="margin-top: 10px">
              <el-collapse-item title="智云服务器与抓取表（一般不用改）" name="1">
                <el-form-item label="智云服务器地址"><el-input v-model="sZyUrl" @input="mark('zy')" /></el-form-item>
                <el-form-item label="下单 表ID"><el-input v-model="sTblOrders" @input="mark('zy')" /></el-form-item>
                <el-form-item label="回款记录 表ID"><el-input v-model="sTblReceipts" @input="mark('zy')" /></el-form-item>
                <el-form-item label="项目明细 表ID"><el-input v-model="sTblProject" @input="mark('zy')" /></el-form-item>
                <el-form-item label="内部译员 表ID"><el-input v-model="sTblInhouse" @input="mark('zy')" /></el-form-item>
              </el-collapse-item>
            </el-collapse>
          </el-form>
          <div class="muted">{{ setMsgs.zy }}</div>
        </el-card>
      </el-col>

      <!-- 账号与权限 -->
      <el-col :span="24">
        <el-card shadow="never" class="scard">
          <template #header>
            <div class="scard-h"><span class="ico">👥</span><div><div class="ttl">账号与权限</div><div class="sub">管理员 / 整体 / 按 BU；总账号不可删</div></div></div>
          </template>
          <el-table :data="acctList" border size="small" max-height="360">
            <el-table-column label="账号" width="140">
              <template #default="{ row, $index }">
                <el-input v-model="row.账号" size="small" :readonly="isMaster(row)" @input="mark('acct')" />
              </template>
            </el-table-column>
            <el-table-column label="显示名" width="120">
              <template #default="{ row }">
                <el-input v-model="row.显示名" size="small" @input="mark('acct')" />
              </template>
            </el-table-column>
            <el-table-column label="权限" min-width="220">
              <template #default="{ row }">
                <template v-if="isMaster(row)">
                  <el-tag>管理员</el-tag>
                </template>
                <template v-else>
                  <el-select
                    :model-value="permType(row)"
                    size="small"
                    style="width: 140px"
                    @change="(v: string | number | boolean) => onPermType(row, String(v))"
                  >
                    <el-option label="管理员" value="管理员" />
                    <el-option label="整体（看全部）" value="整体" />
                    <el-option label="按 BU（可多选）" value="BU" />
                  </el-select>
                  <div v-if="permType(row) === 'BU'" class="bu-checks">
                    <el-checkbox
                      v-for="bn in buList.map((b) => b.name).filter(Boolean)"
                      :key="bn"
                      :model-value="(row.可见BU || []).includes(bn)"
                      @change="(on: string | number | boolean) => onBuVisible(row, bn, !!on)"
                    >{{ bn }}</el-checkbox>
                  </div>
                </template>
              </template>
            </el-table-column>
            <el-table-column label="密码" width="160">
              <template #default="{ row, $index }">
                <el-input
                  v-model="row.密码"
                  size="small"
                  :type="acctPwShow[$index] ? 'text' : 'password'"
                  @input="() => { row.初始密码 = false; mark('acct') }"
                />
                <el-button text size="small" @click="acctPwShow[$index] = !acctPwShow[$index]">{{ acctPwShow[$index] ? '🙈' : '👁' }}</el-button>
                <el-tag v-if="row.初始密码" type="warning" size="small">初始</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="最后登录" label="最后登录" width="140" />
            <el-table-column label="" width="80">
              <template #default="{ row, $index }">
                <span v-if="isMaster(row)" class="muted">总账号</span>
                <el-button v-else text size="small" @click="acctDel($index)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button size="small" text style="margin-top: 8px" @click="acctAdd">＋ 加账号</el-button>
          <span class="muted" style="margin-left: 8px">{{ setMsgs.acct }}</span>
        </el-card>
      </el-col>

      <!-- BU 归属 -->
      <el-col :span="24">
        <el-card shadow="never" class="scard">
          <template #header>
            <div class="scard-h"><span class="ico">🏢</span><div><div class="ttl">BU 数据归属（销售归属）</div><div class="sub">一人一 BU；拖动或批量指定；保存后重算</div></div></div>
          </template>
          <el-alert
            v-if="buUnassigned.unassigned_count"
            type="warning"
            :closable="false"
            style="margin-bottom: 12px"
            :title="`未归属销售 ${buUnassigned.unassigned_count} 人，当年下单合计 ${buUnassigned.unassigned_orders_disp || ''}`"
          />
          <div v-if="buPicked.size" class="bu-batch">
            已勾选 <b>{{ buPicked.size }}</b> 人 →
            <el-select v-model="pickTo" size="small" style="width: 160px">
              <el-option label="保持未归属" value="__pool__" />
              <el-option v-for="(b, i) in buList" :key="i" :label="b.name || 'BU' + (i + 1)" :value="String(i)" />
            </el-select>
            <el-button size="small" @click="applyBatch">批量指定</el-button>
            <el-button size="small" text @click="buPicked = new Set()">清除勾选</el-button>
          </div>

          <div class="bu-pool" @dragover.prevent @drop="onDropPool">
            <div class="bu-pool-h"><b>未归属销售</b><span class="muted"> · 共 {{ salesPool.length }} · 未归属 {{ poolNames().length }}</span></div>
            <div class="admin-bu-zone">
              <span
                v-for="n in poolNames()"
                :key="n"
                class="admin-bu-chip"
                draggable="true"
                @dragstart="onDragStart(n, $event)"
              >
                <el-checkbox :model-value="buPicked.has(n)" @change="(on: string | number | boolean) => togglePick(n, !!on)" @click.stop />
                <span>{{ n }}</span>
                <span v-if="salesPool.find((p) => p.name === n)?.ref_disp" class="muted">{{ salesPool.find((p) => p.name === n)?.ref_disp }}</span>
              </span>
              <div v-if="!poolNames().length" class="muted">暂无未归属销售</div>
            </div>
          </div>

          <div class="bu-cols">
            <div v-for="(b, i) in buList" :key="i" class="bu-col">
              <el-input v-model="b.name" size="small" placeholder="BU 名" style="margin-bottom: 6px" @input="mark('bu')" />
              <el-input :model-value="ownerStr(b)" size="small" placeholder="负责人备注" style="margin-bottom: 6px" @update:model-value="(v: string) => setOwner(b, v)" />
              <div class="muted" style="display: flex; justify-content: space-between">
                <span>销售 {{ salesArr(b.销售).length }} 人</span>
                <el-button text size="small" @click="buDel(i)">删 BU</el-button>
              </div>
              <div class="admin-bu-zone" @dragover.prevent @drop="onDropBu(i, $event)">
                <span
                  v-for="n in salesArr(b.销售)"
                  :key="n"
                  class="admin-bu-chip"
                  draggable="true"
                  @dragstart="onDragStart(n, $event)"
                >
                  <el-checkbox :model-value="buPicked.has(n)" @change="(on: string | number | boolean) => togglePick(n, !!on)" @click.stop />
                  <span>{{ n }}</span>
                  <el-button text size="small" @click.stop="moveToPool(n)">×</el-button>
                </span>
                <div v-if="!salesArr(b.销售).length" class="muted">拖销售到这里</div>
              </div>
            </div>
          </div>
          <el-button size="small" text style="margin-top: 10px" @click="buAdd">＋ 加一个 BU</el-button>
          <div class="muted" style="margin-top: 8px">
            公共费用分摊比例已改为按月填写——去「数据调整 → 人工填写」。
            <span v-if="buAllocLegacy" style="color: #fbbf24">⚠ 检测到旧全年分摊比例，已停用，请按月重填。</span>
          </div>
          <div class="muted">{{ setMsgs.bu }}</div>
        </el-card>
      </el-col>

      <!-- 数据来源 -->
      <el-col :span="24">
        <el-card shadow="never" class="scard">
          <template #header>
            <div class="scard-h"><span class="ico">🔌</span><div><div class="ttl">数据从哪来</div><div class="sub">智云四表 + 共享盘台账</div></div></div>
          </template>
          <el-table :data="srcRows" border size="small">
            <el-table-column prop="name" label="数据" width="200" />
            <el-table-column prop="src" label="从哪来" />
            <el-table-column prop="rows" label="当前行数" width="100" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <div v-if="dirty.size" class="admin-dirty-bar">
      <span>有 <b>{{ dirty.size }}</b> 处设置未保存</span>
      <el-button @click="discard">放弃更改</el-button>
      <el-button type="primary" :loading="saving" @click="saveAll">保存全部设置</el-button>
    </div>

    <el-drawer v-model="verDrawer" title="更新日志" size="400px">
      <p class="muted">按时间倒序（最新在最上面）</p>
      <div v-for="(e, i) in verLog" :key="i" class="vl">
        <div class="vl-h"><b>{{ e.title }}</b><span class="muted">{{ e.date }}</span></div>
        <ul>
          <li v-for="(it, j) in (e.items || [])" :key="j">{{ it }}</li>
        </ul>
      </div>
      <div v-if="!verLog.length" class="muted">暂无更新日志</div>
    </el-drawer>
  </div>
</template>

<style scoped>
.scard { margin-bottom: 16px; }
.scard-h { display: flex; gap: 12px; align-items: flex-start; }
.ico { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; background: rgba(139, 92, 246, 0.2); }
.ttl { font-size: 15px; font-weight: 700; }
.sub { font-size: 12px; color: var(--admin-mut, #8b9bb4); margin-top: 3px; }
.muted { color: var(--admin-mut, #8b9bb4); font-size: 12.5px; }
.num { font-size: 22px; font-weight: 700; }
.vu-box { margin-top: 10px; padding: 10px; border: 1px solid var(--admin-line, #2a364d); border-radius: 8px; }
.sched-row { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.field-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.foot { margin-top: 8px; }
.bu-checks { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.bu-batch { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
.bu-pool { margin-bottom: 14px; }
.bu-pool-h { margin-bottom: 6px; }
.bu-cols { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.bu-col { padding: 10px; border: 1px solid var(--admin-line, #2a364d); border-radius: 10px; background: var(--admin-panel2, #1a2438); }
.vl { margin-bottom: 14px; }
.vl-h { display: flex; justify-content: space-between; margin-bottom: 4px; }
</style>
