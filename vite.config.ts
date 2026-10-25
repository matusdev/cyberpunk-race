import { defineConfig } from 'vite';

// base './' so the same build runs from a web server, a sub-folder, or inside the Android WebView
export default defineConfig({
  base: './',
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 2000,
    assetsInlineLimit: 0
  },
  server: { port: 5180 }
});
