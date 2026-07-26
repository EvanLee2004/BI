<script setup lang="ts">
/**
 * Layer 2 · RankBar
 * 序号 · 名称（省略 + title）· 条（单/双）· 主数值贴条尾 · 可选副数值列（须 metaLabel）
 */
defineProps<{
  rank: number | string
  name: string
  /** 主条宽度 0–100 */
  primaryWidth?: number
  /** 主数值显示串（贴条尾） */
  primaryValue?: string
  dual?: boolean
  secondaryWidth?: number
  secondaryValue?: string
  /** 副列显示串；无 metaLabel 时不渲染副列（F-4） */
  meta?: string
  metaLabel?: string
  /** 副列悬浮解释 */
  metaTitle?: string
}>()
</script>

<template>
  <div class="rank-bar" data-testid="rank-bar">
    <span class="rank-bar__no">{{ rank }}</span>
    <span class="rank-bar__name" :title="name">{{ name }}</span>
    <div v-if="dual" class="rank-bar__track-wrap rank-bar__track-wrap--dual">
      <div class="rank-bar__dual-row">
        <span class="rank-bar__track rank-bar__track--dual">
          <i
            class="rank-bar__fill rank-bar__fill--primary"
            :style="{ width: Math.max(0, Math.min(100, primaryWidth || 0)) + '%' }"
          />
        </span>
        <em v-if="primaryValue" class="rank-bar__amt">{{ primaryValue }}</em>
      </div>
      <div class="rank-bar__dual-row">
        <span class="rank-bar__track rank-bar__track--dual">
          <i
            class="rank-bar__fill rank-bar__fill--secondary"
            :style="{ width: Math.max(0, Math.min(100, secondaryWidth || 0)) + '%' }"
          />
        </span>
        <em v-if="secondaryValue" class="rank-bar__amt">{{ secondaryValue }}</em>
      </div>
    </div>
    <div v-else class="rank-bar__track-wrap">
      <span class="rank-bar__track">
        <i
          class="rank-bar__fill rank-bar__fill--primary"
          :style="{ width: Math.max(0, Math.min(100, primaryWidth || 0)) + '%' }"
        />
      </span>
      <em v-if="primaryValue" class="rank-bar__amt">{{ primaryValue }}</em>
    </div>
    <!-- F-4：无 metaLabel 不渲染副数值列 -->
    <span
      v-if="metaLabel && meta"
      class="rank-bar__meta"
      :title="metaTitle || metaLabel"
      data-testid="rank-bar-meta"
      >{{ meta }}</span
    >
  </div>
</template>
