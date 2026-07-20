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

import { installThemeListeners, syncThemeFromDom } from '../utils/theme'
import { installFrontendErrorReporter } from '../utils/frontendErrorReporter'

export function bootAdmin() {
  // 主题：与驾驶舱共用 cockpit-theme（响应式 + iframe/storage 同步）
  try {
    if (localStorage.getItem('cockpit-theme') === 'light') {
      document.documentElement.classList.add('theme-light')
    }
  } catch {
    /* ignore */
  }
  syncThemeFromDom()
  installThemeListeners()
  document.title = '经营罗盘·管理端'

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
