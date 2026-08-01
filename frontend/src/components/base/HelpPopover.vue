<script setup lang="ts">
/**
 * 统一解释性「?」帮助层（3.7.4）
 * - 桌面：hover 预览、click 固定；键盘 Tab/Enter|Space/Escape/点外关闭
 * - 手机：click 打开 Teleport 抽屉/对话框，可滚动可关闭
 * - 禁止承载黄/红状态、抓数异常、确认操作或空态（仅解释性文案）
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
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
const isNarrow = ref(false)

const open = computed(() => pinned.value || hover.value)

function mqCheck() {
  try {
    isNarrow.value = window.matchMedia('(max-width: 520px)').matches
  } catch {
    isNarrow.value = false
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
  if (!pinned.value) return
  const t = e.target as Node | null
  if (!t || !rootEl.value) return
  if (rootEl.value.contains(t)) return
  pinned.value = false
}

function togglePin() {
  if (isNarrow.value) {
    mobileOpen.value = !mobileOpen.value
    pinned.value = false
    hover.value = false
    return
  }
  pinned.value = !pinned.value
  if (pinned.value) hover.value = false
}

function onBtnKey(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    togglePin()
  }
}

onMounted(() => {
  mqCheck()
  window.addEventListener('resize', mqCheck, { passive: true })
  document.addEventListener('keydown', onKey)
  document.addEventListener('pointerdown', onDocPointer, true)
})
onUnmounted(() => {
  window.removeEventListener('resize', mqCheck)
  document.removeEventListener('keydown', onKey)
  document.removeEventListener('pointerdown', onDocPointer, true)
})

watch(
  () => props.lines,
  () => {
    /* content-only */
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
      @mouseenter="!isNarrow && (hover = true)"
      @mouseleave="!pinned && (hover = false)"
      @click.stop="togglePin"
      @keydown="onBtnKey"
      @focus="!isNarrow && (hover = true)"
      @blur="!pinned && (hover = false)"
    >
      ?
    </button>
    <!-- 桌面浮层：Teleport body，避免裁切 -->
    <Teleport to="body">
      <div
        v-if="open && !isNarrow"
        :id="testId + '-popover'"
        class="help-pop__panel kc-help-popover"
        :data-testid="testId + '-popover'"
        role="tooltip"
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
