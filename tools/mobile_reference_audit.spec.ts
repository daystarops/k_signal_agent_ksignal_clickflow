import {test,devices,webkit,chromium} from '@playwright/test';
import fs from 'node:fs'; import path from 'node:path';
const out=path.resolve('outputs/research/mobile_reference_audit_second_pass');
const refs=[
 ['nyt_mobile_home_chromium.png','https://www.nytimes.com/'],
 ['buzzfeed_mobile_article_chromium.png','https://www.buzzfeed.com/'],
 ['vice_mobile_article_chromium.png','https://www.vice.com/'],
 ['theqoo_mobile_home_chromium.png','https://theqoo.net/']
];
test('public mobile reference screenshots',async()=>{fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true});const ctx=await browser.newContext({...devices['Pixel 7']});for(const [name,url] of refs){const p=await ctx.newPage();try{await p.goto(url,{waitUntil:'domcontentloaded',timeout:30000});await p.waitForTimeout(1500);await p.screenshot({path:path.join(out,name),fullPage:false});}catch(e){fs.writeFileSync(path.join(out,name.replace('.png','.blocked.txt')),String(e));}await p.close();}await browser.close();});
