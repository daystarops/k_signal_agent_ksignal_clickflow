import { test, expect, devices, chromium, webkit } from '@playwright/test';
import fs from 'node:fs'; import path from 'node:path';
const base = process.env.KSIGNAL_BASE_URL || 'http://localhost:8080';
const out = path.resolve('outputs/issues/001/mobile_render_audit');
const routes = ['/', '/articles/card_01.html', '/articles/card_02.html', '/articles/card_03.html', '/articles/card_04.html', '/search.html', '/about.html', '/privacy.html'];
const profiles = [
 {id:'iphone_se',label:'iPhone SE',engine:'webkit',o:{...devices['iPhone SE']}},
 {id:'iphone_13',label:'iPhone 13',engine:'webkit',o:{...devices['iPhone 13']}},
 {id:'pixel_7',label:'Pixel 7',engine:'chromium',o:{...(devices['Pixel 7']||devices['Pixel 5'])}},
 {id:'android_small',label:'Galaxy/Samsung-like Android',engine:'chromium',o:{...(devices['Galaxy S9+']||devices['Pixel 5']),viewport:{width:360,height:740}}},
 {id:'stress_320',label:'320px stress',engine:'chromium',o:{...devices['Pixel 5'],viewport:{width:320,height:568},deviceScaleFactor:2,isMobile:true,hasTouch:true}},
];
const results:any[]=[]; test.describe.configure({mode:'serial'}); test.beforeAll(()=>fs.mkdirSync(out,{recursive:true}));
for(const p of profiles)test(`${p.label} true mobile render`,async()=>{
 const bt=p.engine==='webkit'?webkit:chromium,b=await bt.launch(),c=await b.newContext(p.o as any),page=await c.newPage(),issues:string[]=[];
 page.on('pageerror',e=>issues.push(`pageerror: ${e.message}`));
 for(const route of routes){await page.goto(base+route,{waitUntil:'domcontentloaded',timeout:20000}); await page.evaluate(()=>scrollTo(0,document.body.scrollHeight/2)); await page.evaluate(()=>scrollTo(0,document.body.scrollHeight)); await page.evaluate(()=>scrollTo(0,0)); const x=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth); if(x>1)issues.push(`${route}: ${x}px horizontal overflow`); expect(x).toBeLessThanOrEqual(1)}
 await page.goto(base+'/'); await page.locator('.lane-trigger').nth(0).tap(); await page.locator('.lane-trigger').nth(1).tap(); expect(await page.locator('.lane-item.is-open').count()).toBe(1); await page.locator('.search-toggle').tap(); await page.locator('.site-search input').fill('빌리'); await expect(page.locator('.search-typeahead a').first()).toBeVisible({timeout:5000}); if(p.id!=='stress_320')await page.screenshot({path:path.join(out,`${p.id}_home.png`),fullPage:true});
 await page.goto(base+'/articles/card_02.html'); await page.locator('.comment-toggle').tap(); await expect(page.locator('.comment-panel')).toBeVisible(); await expect(page.locator('.related-signals')).toBeVisible(); await expect(page.locator('.more-from-issue')).toBeVisible(); await expect(page.locator('.site-footer')).toBeVisible(); if(p.id!=='stress_320')await page.screenshot({path:path.join(out,`${p.id}_card_02.png`),fullPage:true});
 await page.goto(base+'/search.html?q=K리그'); await expect(page.locator('a[href*="card_03"]').first()).toBeVisible({timeout:5000}); results.push({label:p.label,engine:p.engine,viewport:(p.o as any).viewport,ua:p.engine==='webkit'?'iPhone Safari-style mobile':'Android Chromium mobile',issues}); await b.close();
});
test.afterAll(()=>{const l=['# True mobile rendering audit','','| Device profile | Engine | Viewport | User agent | Result |','|---|---|---:|---|---|',...results.map(r=>`| ${r.label} | ${r.engine} | ${r.viewport.width}×${r.viewport.height} | ${r.ua} | ${r.issues.length?'FAIL':'PASS'} |`),'','## Screenshots','',...profiles.filter(p=>p.id!=='stress_320').flatMap(p=>[`- [${p.label} homepage](mobile_render_audit/${p.id}_home.png)`,`- [${p.label} card 02](mobile_render_audit/${p.id}_card_02.png)`]),'','## Issues found and fixes applied','',...((results.flatMap(r=>r.issues.map((i:string)=>`- ${r.label}: ${i}`)))||[]),'- Fixed Pagefind module resolution after moving interaction JavaScript: dynamic imports now resolve against the document URL, not `assets/ksignal.js`.','- Added mobile overflow containment, font clamps, 44px primary touch targets, 16px form controls, safe-area padding, and 320px layout rules.','','All profiles use mobile user agents, touch, `isMobile`, and device scale factors. iPhones run in Playwright WebKit; Android profiles run in Chromium.']; fs.writeFileSync('outputs/issues/001/mobile_render_audit.md',l.join('\n')+'\n')});
