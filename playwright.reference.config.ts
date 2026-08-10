import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tools',testMatch:'mobile_reference_audit.spec.ts',timeout:120000,workers:1});
