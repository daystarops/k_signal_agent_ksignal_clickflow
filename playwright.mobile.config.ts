import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tools',
  testMatch: 'mobile_render_qa_ksignal.spec.ts',
  timeout: 120_000,
  fullyParallel: false,
  workers: 1,
});
