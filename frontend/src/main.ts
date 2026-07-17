import { createApp } from 'vue'
import { createPinia } from 'pinia'
/* SciFi kit CSS (vendored, no CDN) + bridge to theme.css */
import './vendor/scifi-kit/DynamicSciFiDashboardKit.css'
import './vendor/scifi-kit/scifi-bridge.css'
import App from './App.vue'

const app = createApp(App)
app.use(createPinia())
app.mount('#app')
