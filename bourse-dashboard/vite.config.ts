import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Proxy de développement (npm run dev) : le navigateur appelle /api/..., Vite transmet à l'API.
// Variables (fichier .env.local, non commité) :
//   API_TARGET : http://localhost:8000 par défaut (uvicorn local), ou https://issuer-hub.pdf-libre.de
//   API_AUTH   : base64 de « utilisateur:mot de passe » si API_TARGET est le serveur (echo -n 'user:pass' | base64)
// En production, ce proxy n'existe pas : Caddy sert le front et l'API sur le même domaine.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        '/api': {
          target: env.API_TARGET || 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
          headers: env.API_AUTH ? { Authorization: `Basic ${env.API_AUTH}` } : {},
        },
      },
    },
  }
})
