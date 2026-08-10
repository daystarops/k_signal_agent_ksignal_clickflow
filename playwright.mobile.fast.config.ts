import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tools',testMatch:'mobile_render_qa_fast.spec.ts',timeout:60000,fullyParallel:false,workers:1});
