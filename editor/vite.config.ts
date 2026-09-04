import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'react-flow',
              test: /node_modules[\\/](?:@reactflow|reactflow)[\\/]/,
              priority: 20,
            },
            {
              name: 'react-runtime',
              test: /node_modules[\\/](?:react|react-dom|scheduler|zustand)[\\/]/,
              priority: 10,
            },
          ],
        },
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:7777',
        changeOrigin: true,
        ws: true,
        rewrite: path => path.replace(/^\/api/, ''),
      },
    },
  },
})
