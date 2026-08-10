import { test, expect, devices, type BrowserType, chromium, webkit } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const baseURL = process.env.KSIGNAL_BASE_URL || 'http://localhost:8080';
const outDir = path.resolve('outputs/issues/001/mobile_render_audit');
const routes = ['/', '/articles/card_01.html', '/articles/card_02.html', '/articles/card_03.html', '/articles/card_04.html', '/search.html', '/about.html', '/privacy.html'];
const findings: any[] = [];

const profiles = [
  { id: 'iphone_se', label: 'iPhone SE', engine: 'webkit', options: { ...devices['iPhone SE'] } },
  { id: 'iphone_13', label: 'iPhone 13', engine: 'webkit', options: { ...devices['iPhone 13'] } },
  { id: 'pixel_7', label: 'Pixel 7', engine: 'chromium', options: { ...(devices['Pixel 7'] || devices['Pixel 5']) } },
  { id: 'android_small', label: 'Galaxy S9-like Android', engine: 'chromium', options: { ...(devices['Galaxy S9+'] || devices['Pixel 5']), viewport: { width: 360, height: 740 } } },
  { id: 'stress_320', label: '320px Android stress', engine: 'chromium', options: { ...(devices['Pixel 5']), viewport: { width: 320, height: 568 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true } },
];

test.describe.configure({ mode: 'serial' });
test.beforeAll(() => fs.mkdirSync(outDir, { recursive: true }));

for (const profile of profiles) {
  test(`${profile.label} rendered mobile audit`, async () => {
    const browserType: BrowserType = profile.engine === 'webkit' ? webkit : chromium;
    const browser = await browserType.launch({ headless: true });
    const context = await browser.newContext(profile.options as any);
    const page = await context.newPage();
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
    page.on('console', message => { if (message.type() === 'error' && !/youtube|favicon/i.test(message.text())) errors.push(`console: ${message.text()}`); });
    for (const route of routes) {
      await page.goto(baseURL + route, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(250);
      const layout = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        viewport: [innerWidth, innerHeight],
        logoWidth: Math.round(document.querySelector<HTMLImageElement>('.brand img')?.getBoundingClientRect().width || 0),
        tinyTargets: [...document.querySelectorAll<HTMLElement>('button,a,input,textarea,select')].filter(el => {
          const r = el.getBoundingClientRect(), s = getComputedStyle(el);
          return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0 && (r.width < 40 || r.height < 40);
        }).slice(0, 12).map(el => `${el.tagName.toLowerCase()}.${el.className}:${Math.round(el.getBoundingClientRect().width)}x${Math.round(el.getBoundingClientRect().height)}`),
      }));
      if (layout.overflow > 1) errors.push(`${route}: horizontal overflow ${layout.overflow}px`);
      if (layout.logoWidth > 180) errors.push(`${route}: logo ${layout.logoWidth}px wide`);
      if (layout.tinyTargets.length) errors.push(`${route}: sub-40px targets ${layout.tinyTargets.join(', ')}`);
      await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += innerHeight * .8) { scrollTo(0, y); await new Promise(r => setTimeout(r, 30)); } scrollTo(0, 0); });
      expect(layout.overflow, `${profile.label} ${route} overflow`).toBeLessThanOrEqual(1);
    }

    await page.goto(baseURL + '/', { waitUntil: 'domcontentloaded' });
    const laneButtons = page.locator('.lane-trigger');
    await laneButtons.nth(0).tap(); await laneButtons.nth(1).tap();
    expect(await page.locator('.lane-item.is-open').count()).toBe(1);
    await page.locator('.search-toggle').tap();
    const headerSearch = page.locator('.site-search input');
    await headerSearch.fill('빌리'); await page.waitForTimeout(800);
    expect(await page.locator('.search-typeahead a').count()).toBeGreaterThan(0);
    if (profile.id !== 'stress_320') await page.screenshot({ path: path.join(outDir, `${profile.id}_home.png`), fullPage: true });

    await page.goto(baseURL + '/articles/card_02.html', { waitUntil: 'domcontentloaded' });
    await page.locator('.comment-toggle').tap();
    await expect(page.locator('.comment-panel')).toBeVisible();
    await expect(page.locator('.related-signals')).toBeVisible();
    await expect(page.locator('.more-from-issue')).toBeVisible();
    await expect(page.locator('.site-footer')).toBeVisible();
    if (profile.id !== 'stress_320') await page.screenshot({ path: path.join(outDir, `${profile.id}_card_02.png`), fullPage: true });

    await page.goto(baseURL + '/search.html?q=K리그', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);
    const pagefindResults = await page.locator('a[href*="card_03"]').count();
    if (!pagefindResults) errors.push('/search.html: K리그 did not expose card_03');
    findings.push({ profile: profile.label, engine: profile.engine, viewport: profile.options.viewport, userAgentType: profile.engine === 'webkit' ? 'iPhone Safari-style mobile UA' : 'Android Chromium mobile UA', pass: errors.length === 0, issues: errors });
    await browser.close();
  });
}

test.afterAll(() => {
  const lines = ['# True mobile rendering audit', '', `Base URL: ${baseURL}`, '', '| Device profile | Engine | Viewport | User agent | Result |', '|---|---|---:|---|---|'];
  for (const item of findings) lines.push(`| ${item.profile} | ${item.engine} | ${item.viewport.width}×${item.viewport.height} | ${item.userAgentType} | ${item.pass ? 'PASS' : 'FAIL'} |`);
  lines.push('', '## Screenshots', '', ...profiles.filter(p => p.id !== 'stress_320').flatMap(p => [`- [${p.label} homepage](mobile_render_audit/${p.id}_home.png)`, `- [${p.label} card 02](mobile_render_audit/${p.id}_card_02.png)`]), '', '## Issues found and fixes applied', '');
  const issues = findings.flatMap(item => item.issues.map((issue: string) => `- ${item.profile}: ${issue}`));
  lines.push(...(issues.length ? issues : ['- No blocking overflow, interaction, Pagefind, discovery, comments, or footer failures were found after the mobile CSS fixes.']), '', 'The renderer uses Playwright device descriptors with mobile user agents, touch input, `isMobile`, device scale factors, WebKit for iPhones, and Chromium for Android. The separate 320px profile is a narrow-screen stress case.');
  fs.writeFileSync(path.resolve('outputs/issues/001/mobile_render_audit.md'), lines.join('\n') + '\n');
});

