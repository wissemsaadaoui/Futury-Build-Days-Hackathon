import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { env } from 'node:process'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  
  return{
  plugins: [react(), tailwindcss()],
  server: {
      proxy: {
        '/api': {
          target: 'https://issuer-hub.pdf-libre.de',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
          headers: {
            Authorization: `Basic ${env.API_AUTH}`,
          },
        },
      },
    },
  }
}
)