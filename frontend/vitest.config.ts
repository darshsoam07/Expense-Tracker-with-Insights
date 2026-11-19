import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    // Exercise the financial display rules from the same stylesheet as the application.
    css: { include: [/src[\\/]index\.css/] },
  },
});
