/**
 * 设置页状态与保存逻辑（54.13 从 SettingsView 纯搬家）。
 */
import { inject, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { jget, jpost, downloadBlob } from '../api'
import { friendlyError } from '../../utils/friendlyError'
import { SRC_MAP, salesArr } from '../utils'

/**
 * 3.7.10：用户可勾能力仅三项「导出内容」（key 仍与后端看端导出对齐）。
 * 管理类 / view_main / 管端导出 / 归档 绑管理员角色，不进设置页勾选。
 * 不展示 export_page_png（无顶栏 PNG 按钮）。
 */
export const CAP_KEYS = [
  'export_page_html',
  'export_pl_xlsx',
  'export_ledger_xlsx',
] as const

export type CapKey = (typeof CAP_KEYS)[number]

export const CAP_LABELS: Record<CapKey, string> = {
  export_page_html: '全部视图',
  export_pl_xlsx: '管理利润表',
  export_ledger_xlsx: '收单台账明细',
}

export type Acct = {
  账号?: string
  显示名?: string
  权限?: string
  /** 3.7.8：管理端 GET 回显看板明文；编辑后可改；留空保存=不改 */
  密码?: string
  可见BU?: string[]
  初始密码?: boolean
  password_set?: boolean
  能力?: Partial<Record<CapKey, boolean>>
  caps?: Partial<Record<CapKey, boolean>>
}

export type BuItem = {
  name: string
  负责人?: string | string[]
  销售?: string | string[]
  分摊比例?: number | null
}

export function useSettingsForm() {
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
  const sLogKeep = ref(365)
  const sDiskMin = ref(10)
  const sArchYear = ref(new Date().getFullYear())
  const sArchMsg = ref('')
  const sBakInfo = ref('')
  const sZyUser = ref('')
  const sZyPwd = ref('')
  const sLedgerPath = ref('')
  /** 3.7.14：管理员只读路径 exists 探测 */
  const sLedgerPathExists = ref<boolean | null>(null)
  const sZyUrl = ref('')
  const sTblOrders = ref('')
  const sTblReceipts = ref('')
  const sTblProject = ref('')
  const sTblInhouse = ref('')
  /** R-03：智云表 ID 右侧抽屉（不在设置页原地展开） */
  const zyDrawer = ref(false)
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
  type AcctLocal = Acct & {
    账号: string
    最后登录?: string
  }
  const acctList = ref<AcctLocal[]>([])
  const acctPwShow = ref<Record<number, boolean>>({})
  const masterAccount = ref('lushasha')
  /** 角色默认模板（GET accounts 下发；失败则本地兜底） */
  const capTemplates = ref<Record<string, Partial<Record<CapKey, boolean>>>>({})
  /** 智云密码是否已在服务端设置（GET 不回显明文） */
  const sZyPwdSet = ref(false)

  function emptyCaps(allOn = false): Record<CapKey, boolean> {
    const o = {} as Record<CapKey, boolean>
    for (const k of CAP_KEYS) o[k] = allOn
    return o
  }

  function ensureCaps(row: AcctLocal): Record<CapKey, boolean> {
    const src = row.能力 || row.caps || {}
    const o = emptyCaps(false)
    for (const k of CAP_KEYS) {
      if (typeof (src as Record<string, unknown>)[k] === 'boolean') {
        o[k] = !!(src as Record<string, boolean>)[k]
      }
    }
    row.能力 = o
    return o
  }

  function setCap(row: AcctLocal, key: CapKey, on: boolean) {
    // 3.7.10：管理员行无能力勾；仅整体/BU 可改三项导出内容
    if (permType(row) === '管理员') return
    const caps = ensureCaps(row)
    caps[key] = on
    row.能力 = { ...caps }
    mark('acct')
  }

  function applyRoleTemplate(row: AcctLocal) {
    const role = permType(row)
    if (role === '管理员') {
      // 管理员固定全权，前端不写可关管理 key
      row.能力 = emptyCaps(true)
      mark('acct')
      return
    }
    const tpl =
      capTemplates.value[role] ||
      (role === '整体'
        ? {
            ...emptyCaps(false),
            export_page_html: true,
            export_pl_xlsx: true,
            export_ledger_xlsx: true,
          }
        : emptyCaps(false))
    // 仅保留三项导出内容
    const next = emptyCaps(false)
    for (const k of CAP_KEYS) {
      if (typeof (tpl as Record<string, unknown>)[k] === 'boolean') {
        next[k] = !!(tpl as Record<string, boolean>)[k]
      }
    }
    row.能力 = next
    mark('acct')
  }

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
        '/api/v1/version',
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
      }>('/api/v1/update/check')
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
      await ElMessageBox.confirm(
        '确认一键更新？将拉取新代码并重启服务。用户端将显示「系统正在更新中」维护页，就绪后自动刷新；管理端请稍后刷新。',
        '一键更新',
      )
    } catch {
      return
    }
    vuAvail.value = '更新中…拉取新代码…用户端将显示「系统正在更新中」…'
    try {
      const d = await jpost<{ ok?: boolean; from?: string; to?: string; reason?: string }>('/api/v1/admin/update/apply', {})
      if (d.ok) {
        vuAvail.value = `✓ 已拉取 ${d.from || ''} → ${d.to || ''}，服务重启中。用户端显示「系统正在更新中」，就绪后自动恢复…`
        setTimeout(() => location.reload(), 12000)
      } else {
        vuAvail.value = '未更新：' + (d.reason || '')
      }
    } catch {
      vuAvail.value = '更新请求已发出，服务可能正在重启；用户端将显示「系统正在更新中」…'
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
        zhiyun_password_set?: boolean
        ledger_share_path?: string
        ledger_path_exists?: boolean
        run_log_keep_days?: number
        disk_free_min_ratio?: number
        zhiyun_conn?: { base_url?: string; tables?: Record<string, string> }
        backup_stats?: { count?: number; mb?: number }
      }>('/api/v1/admin/settings')
      scheduleTimes.value =
        s.schedule_times && s.schedule_times.length ? s.schedule_times.slice() : [s.schedule_time || '09:30']
      sKeep.value = s.backup_keep_days || 30
      sZyUser.value = s.zhiyun_username || ''
      // 3.7.5：永不预填已存密码；仅状态
      sZyPwd.value = ''
      sZyPwdSet.value = !!s.zhiyun_password_set
      sLedgerPath.value = s.ledger_share_path || ''
      sLedgerPathExists.value =
        typeof s.ledger_path_exists === 'boolean' ? s.ledger_path_exists : null
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
        '/api/v1/admin/archive_export?year=' + encodeURIComponent(String(sArchYear.value)),
        '审计归档_' + sArchYear.value + '.xlsx',
      )
      sArchMsg.value = '✓ 已下载 ' + sArchYear.value + ' 年归档（库内未删）'
    } catch (e) {
      sArchMsg.value = '失败：' + friendlyError(e)
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
    // 新账号：整体默认三项导出内容开（3.7.10）+ 须显式设密
    const row: AcctLocal = {
      账号: '',
      显示名: '',
      权限: '整体',
      密码: '',
      初始密码: true,
      password_set: false,
      最后登录: '',
      能力: {
        ...emptyCaps(false),
        export_page_html: true,
        export_pl_xlsx: true,
        export_ledger_xlsx: true,
      },
    }
    acctList.value.push(row)
    mark('acct')
  }

  async function resetAcctPasswd(row: AcctLocal) {
    const acct = String(row.账号 || '').trim()
    if (!acct) {
      ElMessage.warning('请先填写账号名并保存')
      return
    }
    try {
      const { value } = await ElMessageBox.prompt(
        '请输入新密码（必填）。保存后列表可见明文。',
        '设置新密码 · ' + acct,
        {
          inputPlaceholder: '新密码（必填）',
          inputValue: '',
          confirmButtonText: '设置',
          cancelButtonText: '取消',
          inputType: 'password',
          inputValidator: (v: string) => {
            if (!String(v || '').trim()) return '新密码不能为空'
            return true
          },
        },
      )
      const typed = String(value || '').trim()
      if (!typed) {
        ElMessage.warning('新密码不能为空')
        return
      }
      await jpost<{ note?: string; status?: string }>(
        `/api/v1/admin/accounts/${encodeURIComponent(acct)}/reset_passwd`,
        { new: typed },
      )
      ElMessage.success('已设置新密码')
      await loadAccts()
    } catch {
      /* 取消 */
    }
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
      const d = await jget<{
        accounts?: AcctLocal[]
        master_account?: string
        cap_templates?: Record<string, Partial<Record<CapKey, boolean>>>
      }>('/api/v1/admin/accounts')
      // 3.7.8：API 回显看板明文密码（MADR-0020）；智云密码仍不下发
      acctList.value = (d.accounts || []).map((a) => {
        const row: AcctLocal = {
          ...a,
          密码: a.密码 != null ? String(a.密码) : '',
          能力: { ...emptyCaps(false), ...(a.能力 || a.caps || {}) },
        }
        return row
      })
      if (d.master_account) masterAccount.value = d.master_account
      if (d.cap_templates) capTemplates.value = d.cap_templates
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
        jget<{ bus?: BuItem[]; 公共费用分摊启用?: boolean }>('/api/v1/admin/bu_config'),
        jget<PoolRes>('/api/v1/admin/sales_pool').catch((): PoolRes => ({ sales: [] })),
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
      const d = await jpost<{ schedule_times?: string[]; note?: string }>('/api/v1/admin/settings', { schedule_times: times })
      if (d.schedule_times?.length) scheduleTimes.value = d.schedule_times.slice()
      setMsgs.sched = d.note || '已保存'
      return true
    } catch (e) {
      setMsgs.sched = '失败：' + friendlyError(e)
      return false
    }
  }
  async function saveBackup() {
    setMsgs.backup = '保存中…'
    try {
      const d = await jpost<{ note?: string }>('/api/v1/admin/settings', { backup_keep_days: sKeep.value })
      setMsgs.backup = d.note || '已保存'
      return true
    } catch (e) {
      setMsgs.backup = '失败：' + friendlyError(e)
      return false
    }
  }
  async function saveAlert() {
    setMsgs.alert = '保存中…'
    const pct = sDiskMin.value || 10
    try {
      const d = await jpost<{ note?: string }>('/api/v1/admin/settings', {
        run_log_keep_days: sLogKeep.value,
        disk_free_min_ratio: pct * 1e-2,
      })
      setMsgs.alert = d.note || '已保存'
      return true
    } catch (e) {
      setMsgs.alert = '失败：' + friendlyError(e)
      return false
    }
  }
  async function saveZhiyun() {
    setMsgs.zy = '保存中…'
    const p: Record<string, unknown> = { ledger_share_path: sLedgerPath.value }
    if (sZyUser.value || sZyPwd.value) {
      p.zhiyun_username = sZyUser.value
      // 留空不改：仅当用户明确填入新密码时才传
      if (sZyPwd.value) p.zhiyun_password = sZyPwd.value
      else if (sZyUser.value) p.zhiyun_username = sZyUser.value
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
      const d = await jpost<{ note?: string }>('/api/v1/admin/settings', p)
      setMsgs.zy = d.note || '已保存'
      sZyPwd.value = ''
      try {
        const s = await jget<{ zhiyun_password_set?: boolean }>('/api/v1/admin/settings')
        sZyPwdSet.value = !!s.zhiyun_password_set
      } catch {
        /* ignore */
      }
      return true
    } catch (e) {
      setMsgs.zy = '失败：' + friendlyError(e)
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
      // 密码：有值则提交（含明文回显后未改）；空串=留空不改（后端沿用）
      // 能力：整表提交，便于陆总统领
      const payload = acctList.value.map((a) => {
        const row: Record<string, unknown> = {
          账号: a.账号,
          显示名: a.显示名,
          权限: a.权限,
          可见BU: a.可见BU,
          能力: ensureCaps(a),
        }
        const pw = String(a.密码 || '').trim()
        if (pw) row['密码'] = pw
        return row
      })
      const d = await jpost<{
        accounts?: AcctLocal[]
        master_account?: string
        note?: string
        count?: number
      }>('/api/v1/admin/accounts', { accounts: payload })
      acctList.value = (d.accounts || []).map((a) => ({
        ...a,
        密码: a.密码 != null ? String(a.密码) : '',
        能力: { ...emptyCaps(false), ...(a.能力 || a.caps || {}) },
      }))
      if (d.master_account) masterAccount.value = d.master_account
      setMsgs.acct = (d.note || '已保存') + '（共 ' + d.count + ' 个）'
      return true
    } catch (e) {
      setMsgs.acct = '保存失败：' + friendlyError(e)
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
      const d = await jpost<{ bus?: BuItem[]; 公共费用分摊启用?: boolean; note?: string; count?: number }>('/api/v1/admin/bu_config', {
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
      setMsgs.bu = '保存失败：' + friendlyError(e)
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
  return {
    reloadDash,
    health,
    verNum,
    verStage,
    verNext,
    verLog,
    verDrawer,
    vuMsg,
    vuAvail,
    canUpdate,
    updatePayload,
    scheduleTimes,
    sKeep,
    sLogKeep,
    sDiskMin,
    sArchYear,
    sArchMsg,
    sBakInfo,
    sZyUser,
    sZyPwd,
    sZyPwdSet,
    sLedgerPath,
    sLedgerPathExists,
    sZyUrl,
    sTblOrders,
    sTblReceipts,
    sTblProject,
    sTblInhouse,
    zyDrawer,
    srcRows,
    dirty,
    setMsgs,
    saving,
    acctList,
    acctPwShow,
    masterAccount,
    capTemplates,
    CAP_KEYS,
    CAP_LABELS,
    ensureCaps,
    setCap,
    applyRoleTemplate,
    resetAcctPasswd,
    buList,
    salesPool,
    buPicked,
    buUnassigned,
    buAllocLegacy,
    dragName,
    poolNames,
    pickTo,
    mark,
    loadVersion,
    checkUpdate,
    applyUpdate,
    loadSettings,
    schedAdd,
    schedDel,
    exportArchive,
    permType,
    isMaster,
    adminCount,
    acctAdd,
    acctDel,
    loadAccts,
    claimedSales,
    buAdd,
    buDel,
    moveToPool,
    moveToBu,
    onDragStart,
    onDropPool,
    onDropBu,
    togglePick,
    applyBatch,
    buAllocEnabled,
    loadBuCfg,
    saveSchedule,
    saveBackup,
    saveAlert,
    saveZhiyun,
    saveAccts,
    saveBu,
    saveAll,
    discard,
    ownerStr,
    setOwner,
    onPermType,
    onBuVisible,
    salesArr,
  }
}
