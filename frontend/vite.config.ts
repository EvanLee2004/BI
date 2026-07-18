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
        // 管理端 Element Plus 单独分包，看端不吞进主包
        manualChunks(id) {
          if (id.includes('node_modules/element-plus') || id.includes('node_modules/@element-plus')) {
            return 'element-plus'
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
