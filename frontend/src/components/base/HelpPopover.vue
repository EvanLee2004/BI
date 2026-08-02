<script setup lang="ts">
/**
 * 统一解释性「?」帮助层（3.7.4）
 * - 桌面：hover 预览、click 固定；键盘 Tab/Enter|Space/Escape/点外关闭
 * - 手机：click 打开 Teleport 抽屉/对话框，可滚动可关闭
 * - 禁止承载黄/红状态、抓数异常、确认操作或空态（仅解释性文案）
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import DataModal from './DataModal.vue'

const props = withDefaults(
  defineProps<{
    label?: string
    title?: string
    lines?: string[]
    testId?: string
  }>(),
  {
    label: '说明',
    title: '说明',
    lines: () => [],
    testId: 'help-popover',
  },
)

const pinned = ref(false)
const hover = ref(false)
const mobileOpen = ref(false)
const rootEl = ref<HTMLElement | null>(null)
const panelEl = ref<HTMLElement | null>(null)
const isNarrow = ref(false)
const panelStyle = ref<Record<string, string>>({})

const open = computed(() => pinned.value || hover.value)

function mqCheck() {
  try {
    isNarrow.value = window.matchMedia('(max-width: 520px)').matches
  } catch {
    isNarrow.value = false
  }
}

/** 锚定触发器下方；不遮挡按钮；视口内可滚 */
function placePanel() {
  const btn = rootEl.value?.querySelector('button') as HTMLElement | null
  if (!btn) return
  const r = btn.getBoundingClientRect()
  const gap = 8
  const maxW = Math.min(22 * 16, window.innerWidth - 24)
  let left = r.left + r.width / 2 - maxW / 2
  left = Math.max(12, Math.min(left, window.innerWidth - maxW - 12))
  let top = r.bottom + gap
  const maxH = Math.min(window.innerHeight * 0.6, 24 * 16)
  if (top + Math.min(200, maxH) > window.innerHeight - 12) {
    // 上方放
    top = Math.max(12, r.top - gap - Math.min(200, maxH))
  }
  panelStyle.value = {
    top: `${Math.round(top)}px`,
    left: `${Math.round(left)}px`,
    width: `${Math.round(maxW)}px`,
    maxHeight: `${Math.round(maxH)}px`,
    transform: 'none',
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (mobileOpen.value) {
      e.preventDefault()
      mobileOpen.value = false
      return
    }
    if (pinned.value || hover.value) {
      e.preventDefault()
      pinned.value = false
      hover.value = false
    }
  }
}

function onDocPointer(e: MouseEvent) {
  if (!pinned.value && !hover.value) return
  const t = e.target as Node | null
  if (!t) return
  if (rootEl.value?.contains(t)) return
  if (panelEl.value?.contains(t)) return
  pinned.value = false
  hover.value = false
}

function togglePin() {
  if (isNarrow.value) {
    mobileOpen.value = !mobileOpen.value
    pinned.value = false
    hover.value = false
    return
  }
  pinned.value = !pinned.value
  if (pinned.value) {
    hover.value = false
    nextTick(() => placePanel())
  }
}

function onBtnKey(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    togglePin()
  }
}

function onHoverIn() {
  if (isNarrow.value) return
  hover.value = true
  nextTick(() => placePanel())
}

function onHoverOut() {
  if (!pinned.value) hover.value = false
}

onMounted(() => {
  mqCheck()
  window.addEventListener('resize', mqCheck, { passive: true })
  window.addEventListener('scroll', placePanel, { passive: true, capture: true })
  document.addEventListener('keydown', onKey)
  document.addEventListener('pointerdown', onDocPointer, true)
})
onUnmounted(() => {
  window.removeEventListener('resize', mqCheck)
  window.removeEventListener('scroll', placePanel, true)
  document.removeEventListener('keydown', onKey)
  document.removeEventListener('pointerdown', onDocPointer, true)
})

watch(open, (v) => {
  if (v) nextTick(() => placePanel())
})

watch(
  () => props.lines,
  () => {
    if (open.value) nextTick(() => placePanel())
  },
)
</script>

<template>
  <span ref="rootEl" class="help-pop" :data-testid="testId + '-wrap'">
    <button
      type="button"
      class="help-pop__btn kc-help-btn"
      :data-testid="testId + '-btn'"
      :aria-label="label"
      :aria-expanded="(open || mobileOpen) ? 'true' : 'false'"
      :aria-controls="testId + '-popover'"
      @mouseenter="onHoverIn"
      @mouseleave="onHoverOut"
      @click.stop="togglePin"
      @keydown="onBtnKey"
      @focus="onHoverIn"
      @blur="onHoverOut"
    >
      ?
    </button>
    <!-- 桌面浮层：Teleport body + 锚定触发器，避免裁切 -->
    <Teleport to="body">
      <div
        v-if="open && !isNarrow"
        ref="panelEl"
        :id="testId + '-popover'"
        class="help-pop__panel kc-help-popover"
        :data-testid="testId + '-popover'"
        role="tooltip"
        :style="panelStyle"
      >
        <p v-if="title" class="help-pop__title">{{ title }}</p>
        <p
          v-for="(line, i) in lines"
          :key="'hl' + i"
          class="help-pop__line"
        >
          {{ line }}
        </p>
        <slot />
      </div>
    </Teleport>
    <!-- 手机：DataModal 抽屉式对话框 -->
    <DataModal
      :open="mobileOpen && isNarrow"
      :title="title || label"
      @close="mobileOpen = false"
    >
      <div :data-testid="testId + '-mobile'" class="help-pop__mobile-body">
        <p
          v-for="(line, i) in lines"
          :key="'mhl' + i"
          class="help-pop__line"
        >
          {{ line }}
        </p>
        <slot />
      </div>
    </DataModal>
  </span>
</template>
