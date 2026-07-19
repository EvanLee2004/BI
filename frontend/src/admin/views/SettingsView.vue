<script setup lang="ts">
/** 设置页（54.13：逻辑在 useSettingsForm，本文件仅模板编排）。 */
import { useSettingsForm } from '../composables/useSettingsForm'

const {
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
  mark,
  acctList,
  acctPwShow,
  masterAccount,
  buList,
  salesPool,
  buPicked,
  buUnassigned,
  buAllocLegacy,
  dragName,
  schedAdd,
  schedDel,
  permType,
  isMaster,
  adminCount,
  acctAdd,
  acctDel,
  claimedSales,
  poolNames,
  buAdd,
  buDel,
  moveToPool,
  moveToBu,
  onDragStart,
  onDropPool,
  onDropBu,
  togglePick,
  pickTo,
  applyBatch,
  buAllocEnabled,
  discard,
  ownerStr,
  setOwner,
  onPermType,
  onBuVisible
} = useSettingsForm()
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
