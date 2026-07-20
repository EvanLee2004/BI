import { createApp } from 'vue'
import { createPinia } from 'pinia'
/* SciFi kit CSS (vendored, no CDN) + bridge to theme.css */
import './vendor/scifi-kit/DynamicSciFiDashboardKit.css'
import './vendor/scifi-kit/scifi-bridge.css'
import App from './App.vue'
import { installThemeListeners, syncThemeFromDom } from './utils/theme'
import { installFrontendErrorReporter } from './utils/frontendErrorReporter'

export function bootCockpit() {
  syncThemeFromDom()
  installThemeListeners()
  const app = createApp(App)
  // 任务书64·D5：errorHandler + window 钩子 + 顶部错误条
  installFrontendErrorReporter(app)
  app.use(createPinia())
  app.mount('#app')
}
