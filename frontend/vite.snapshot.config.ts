/**
 * 2.2.9 快照导出专用构建：单入口 ES + 全量内联动态导入 + 资源内联，
 * 供后端把 JS/CSS 塞进一个可 file:// 打开的 HTML。
 */
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    outDir: 'dist-snapshot',
    emptyOutDir: true,
    cssCodeSplit: false,
    assetsInlineLimit: 10_000_000,
    rollupOptions: {
      input: resolve(__dirname, 'snapshot.html'),
      output: {
        format: 'es',
        inlineDynamicImports: true,
        entryFileNames: 'snapshot.js',
        assetFileNames: 'snapshot.[ext]',
      },
    },
  },
  resolve: {
    alias: { '@': resolve(__dirname, 'src') },
  },
})
