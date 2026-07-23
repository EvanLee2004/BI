/**
 * 管理端独立挂载：仅此路径加载 Element Plus，避免污染看端包体。
 */
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import AdminApp from './AdminApp.vue'
import { adminRouter } from './router'
import './styles/admin.css'

import { syncThemeFromDom, themeMode } from '../utils/theme'
import { installFrontendErrorReporter } from '../utils/frontendErrorReporter'

export function bootAdmin() {
  /* 2.3.0：管理端恒暗色；不读/不写 localStorage，避免与看端主题互相污染 */
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = 'dark'
    document.documentElement.classList.remove('theme-light')
  }
  themeMode.value = 'dark'
  syncThemeFromDom()
  /* 不装 installThemeListeners：管理端不跟 localStorage/postMessage 切主题 */
  document.title = '经营看板·管理端'

  const app = createApp(AdminApp)
  // 任务书64·D5：管理端与看端同一套全局错误钩子 + 顶部错误条
  installFrontendErrorReporter(app)
  app.use(adminRouter)
  app.use(ElementPlus, { locale: zhCn, size: 'default' })
  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
  }
  app.mount('#app')
}
