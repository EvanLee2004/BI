<script setup lang="ts">
/**
 * KPI 大数 count-up 展示。
 * 终值必须等于后端 value_disp；中间帧仅用 value 插值。
 */
import { onBeforeUnmount, ref, watch } from 'vue'
import { runCountUp } from '../utils/countUp'
import { themeMode } from '../utils/theme'

const props = defineProps<{
  value: number
  valueDisp: string
  /** 切换周期时变化，触发重播 */
  playKey?: string
}>()

const text = ref(props.valueDisp || '')
let cancel: (() => void) | null = null
const lastPlayKey = ref('')

function play() {
  cancel?.()
  cancel = runCountUp(Number(props.value), String(props.valueDisp ?? ''), {
    onFrame: (t) => {
      text.value = t
    },
    onDone: (d) => {
      text.value = d
    },
  })
}

watch(
  () => [props.valueDisp, props.value, props.playKey, themeMode.value] as const,
  ([disp, _v, key]) => {
    const pk = String(key ?? '') + '|' + String(disp)
    /* 同周期 re-render 不重播 */
    if (pk === lastPlayKey.value) {
      text.value = String(disp ?? '')
      return
    }
    lastPlayKey.value = pk
    play()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  cancel?.()
})
</script>

<template>
  <b class="count-up-num">{{ text }}</b>
</template>
