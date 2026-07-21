<script setup lang="ts">
/** 设置页壳（54.13） */
import { useSettingsForm } from '../composables/useSettingsForm'

const {
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
  sFeishuHook,
  sLogKeep,
  sDiskMin,
  sArchYear,
  sArchMsg,
  sBakInfo,
  sZyUser,
  sZyPwd,
  sLedgerPath,
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
  salesArr
} = useSettingsForm()
import './settings-view.css'
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
            <el-button type="primary" plain style="margin-top: 8px" @click="zyDrawer = true">智云服务器与抓取表（一般不用改）</el-button>
            <el-drawer v-model="zyDrawer" title="智云服务器与抓取表" direction="rtl" size="420px" append-to-body>
              <el-form label-position="top">
                <el-form-item label="智云服务器地址"><el-input v-model="sZyUrl" @input="mark('zy')" /></el-form-item>
                <el-form-item label="下单 表ID"><el-input v-model="sTblOrders" @input="mark('zy')" /></el-form-item>
                <el-form-item label="回款记录 表ID"><el-input v-model="sTblReceipts" @input="mark('zy')" /></el-form-item>
                <el-form-item label="项目明细 表ID"><el-input v-model="sTblProject" @input="mark('zy')" /></el-form-item>
                <el-form-item label="内部译员 表ID"><el-input v-model="sTblInhouse" @input="mark('zy')" /></el-form-item>
              </el-form>
              <template #footer>
                <el-button type="primary" @click="zyDrawer = false">完成</el-button>
              </template>
            </el-drawer>
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
                    <el-option label="整体（展示全部）" value="整体" />
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
            <el-table-column label="密码" width="220">
              <template #default="{ row, $index }">
                <el-input
                  v-model="row.密码"
                  size="small"
                  :type="acctPwShow[$index] ? 'text' : 'password'"
                  style="width: 100px"
                  @input="() => { row.初始密码 = false; mark('acct') }"
                />
                <el-button text size="small" @click="acctPwShow[$index] = !acctPwShow[$index]">{{ acctPwShow[$index] ? '🙈' : '👁' }}</el-button>
                <el-button size="small" text @click="resetAcctPasswd(row)" :disabled="!String(row.账号 || '').trim()">重置</el-button>
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

    <!-- 2.2.4·F：退出从顶栏移到设置页最下 -->
    <div class="admin-logout-foot" style="margin-top: 32px; padding-top: 20px; border-top: 1px solid var(--el-border-color, #334155); text-align: center">
      <div class="muted" style="margin-bottom: 10px; font-size: 12px">退出登录</div>
      <a class="logout" href="/admin/logout" style="display: inline-block; padding: 8px 24px; border-radius: 8px; border: 1px solid var(--el-border-color, #475569); color: var(--el-text-color-regular, #e2e8f0); text-decoration: none">退出</a>
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

