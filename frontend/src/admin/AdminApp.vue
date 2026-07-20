<script setup lang="ts">
import { onErrorCaptured } from 'vue'
import { RouterView } from 'vue-router'
import { onVueErrorCaptured } from '../utils/frontendErrorReporter'

onErrorCaptured((err) => onVueErrorCaptured(err))
</script>

<template>
  <div class="admin-root">
    <RouterView />
  </div>
</template>
