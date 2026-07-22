import { createApp } from 'vue'
import { createPinia } from 'pinia'
/* SciFi kit CSS (vendored, no CDN) + bridge to theme.css */
import './vendor/scifi-kit/DynamicSciFiDashboardKit.css'
import './vendor/scifi-kit/scifi-bridge.css'
import App from './App.vue'
import { installThemeListeners, migrateThemeIfNeeded } from './utils/theme'
import { installFrontendErrorReporter } from './utils/frontendErrorReporter'

export function bootCockpit() {
  /* 2.3.0：无 v2 标记则强制霓虹；有标记则尊重用户选择 */
  migrateThemeIfNeeded()
  installThemeListeners()
  const app = createApp(App)
  // 任务书64·D5：errorHandler + window 钩子 + 顶部错误条
  installFrontendErrorReporter(app)
  app.use(createPinia())
  app.mount('#app')
}
