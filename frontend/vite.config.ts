import { defineConfig, loadEnv } from 'vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'LEDGEROPS_');
  return {
    plugins: [tailwindcss()],
    server: {
      watch: env.LEDGEROPS_POLL_FILES === 'true' ? { usePolling: true, interval: 300 } : undefined,
      proxy: { '/health': 'http://127.0.0.1:8000' },
    },
  };
});
