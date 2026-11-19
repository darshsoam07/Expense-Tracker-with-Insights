import { defineConfig, loadEnv } from 'vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', ['LEDGEROPS_', 'BACKEND_']);
  const backendTarget =
    env.LEDGEROPS_BACKEND_URL ||
    env.BACKEND_URL ||
    'http://127.0.0.1:8000';

  return {
    plugins: [tailwindcss()],
    server: {
      watch: env.LEDGEROPS_POLL_FILES === 'true' ? { usePolling: true, interval: 300 } : undefined,
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/health': {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
