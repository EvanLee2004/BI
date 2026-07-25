import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  base: '/app/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        // 2.6.3·D1：Vue/pinia 单独分片，避免被 rollup 并进 element-plus chunk
        // （旧 bug：看端 boot-cockpit 为拿 Vue 被迫整包加载管理端 element-plus）
        manualChunks(id) {
          if (id.includes('node_modules/element-plus') || id.includes('node_modules/@element-plus')) {
            return 'element-plus'
          }
          if (
            id.includes('node_modules/vue/') ||
            id.includes('node_modules/@vue/') ||
            id.includes('node_modules/vue-router') ||
            id.includes('node_modules/pinia')
          ) {
            return 'vue-runtime'
          }
          if (id.includes('node_modules/echarts') || id.includes('node_modules/zrender')) {
            return 'echarts'
          }
        },
      },
    },
  },
  resolve: {
    alias: { '@': resolve(__dirname, 'src') },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8018',
      '/static': 'http://127.0.0.1:8018',
      '/login': 'http://127.0.0.1:8018',
      '/admin': 'http://127.0.0.1:8018',
    },
  },
})
