"""Browser Harness QA for K-Signal article discovery endings."""
import time
from pathlib import Path

BASE="http://localhost:8080"; REPORT=Path.cwd()/"outputs/issues/001/browser_qa_report.md"; results=[]
def check(name,condition,note=""):
    ok=bool(condition); results.append((name,ok,note or ("Verified" if ok else "Assertion failed"))); print("PASS" if ok else "FAIL",name)
def value(expr): return js(expr)
def wait_until(expr,timeout=8):
    end=time.time()+timeout
    while time.time()<end:
        if value(expr):return True
        time.sleep(.15)
    return False

new_tab(BASE+"/articles/card_02.html"); wait_for_load()
check("card_02 article opens",value("document.querySelector('main').dataset.cardId") == "card_02")
check("Related signals section exists",value("!!document.querySelector('.related-signals')"))
check("Related signals shows exactly 2 cards",value("document.querySelectorAll('.related-signal-card').length") == 2)
check("Related signals excludes current article",value("[...document.querySelectorAll('.related-signal-card')].every(a=>a.dataset.relatedCardId!=='card_02')"))
check("Related links are internal articles",value("[...document.querySelectorAll('.related-signal-card')].every(a=>new URL(a.href).origin===location.origin&&new URL(a.href).pathname.includes('/articles/'))"))
check("Scores and reasons are not public",not value("document.querySelector('.discovery').textContent.toLowerCase().includes('score') || /same lane \\+25|shared topic \\+12/.test(document.querySelector('.discovery').textContent)"))
check("More from Issue 001 exists",value("document.querySelector('.more-from-issue h2').textContent.trim()") == "More from Issue 001")
check("More from Issue excludes current",value("[...document.querySelectorAll('.issue-signal-card')].every(a=>a.dataset.issueCardId!=='card_02')"))
check("More from Issue preserves editorial order",value("JSON.stringify([...document.querySelectorAll('.issue-signal-card')].map(a=>+a.dataset.editorialOrder))") == "[1,3,4]")
check("Comment area hidden initially",value("document.querySelector('.comment-panel').hidden") is True)
value("document.querySelector('.comment-toggle').click()")
check("Comment toggle still works",value("document.querySelector('.comment-panel').hidden") is False)
value("document.querySelector('.site-search').classList.add('is-open');let i=document.querySelector('.search-form input');i.value='Billlie';i.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:'e'}))")
check("Pagefind search still works",wait_until("!!document.querySelector('.search-typeahead a')"))

cdp("Emulation.setDeviceMetricsOverride",width=390,height=844,deviceScaleFactor=1,mobile=True); cdp("Emulation.setTouchEmulationEnabled",enabled=True,maxTouchPoints=1); value("location.reload()"); wait_for_load()
check("Mobile article ending has no overflow",value("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
value("document.querySelector('.more-from-issue').scrollIntoView({block:'center'});window.__beforeY=scrollY")
rect=value("(()=>{let r=document.querySelector('.issue-signal-strip').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()")
cdp("Input.dispatchMouseEvent",type="mouseWheel",x=rect["x"],y=rect["y"],deltaX=0,deltaY=180); time.sleep(.5)
check("Mobile issue strip does not trap vertical page scroll",value("scrollY > window.__beforeY"))
check("Mobile issue strip allows horizontal discovery",value("getComputedStyle(document.querySelector('.issue-signal-strip')).overflowX") in ("auto","scroll"))
cdp("Emulation.setTouchEmulationEnabled",enabled=False); cdp("Emulation.clearDeviceMetricsOverride")

passed=sum(ok for _,ok,_ in results); lines=["# K-Signal Browser Harness QA Report","",f"- Target: `{BASE}/articles/card_02.html`",f"- Result: **{passed}/{len(results)} passed**","","## Article-ending tests","","| Test | Result | Note |","|---|---:|---|"]
for name,ok,note in results: lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {note} |")
lines += ["","Mobile validation used a 390×844 touch viewport and verified document overflow plus vertical wheel propagation while the pointer was over the issue strip.",""]
REPORT.write_text("\n".join(lines),encoding="utf-8"); print(f"REPORT {REPORT}"); print(f"SUMMARY {passed}/{len(results)}")
