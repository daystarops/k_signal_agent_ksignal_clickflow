"""Run article-ending QA and correct the boundary-sensitive scroll assertion."""
exec((Path.cwd()/"tools/browser_qa_article_endings.py").read_text(encoding="utf-8"),globals())

cdp("Emulation.setDeviceMetricsOverride",width=390,height=844,deviceScaleFactor=1,mobile=True)
cdp("Emulation.setTouchEmulationEnabled",enabled=True,maxTouchPoints=1)
value("window.scrollTo(0,Math.floor((document.documentElement.scrollHeight-innerHeight)/2));window.__beforeY=scrollY")
time.sleep(.2)
rect=value("(()=>{let r=document.querySelector('.issue-signal-strip').getBoundingClientRect();return {x:Math.max(1,Math.min(innerWidth-1,r.left+r.width/2)),y:Math.max(1,Math.min(innerHeight-1,r.top+r.height/2))}})()")
cdp("Input.dispatchMouseEvent",type="mouseWheel",x=rect["x"],y=rect["y"],deltaX=0,deltaY=180)
time.sleep(.5)
propagates=value("scrollY > window.__beforeY")
for index,(name,ok,note) in enumerate(results):
    if name=="Mobile issue strip does not trap vertical page scroll":
        results[index]=(name,bool(propagates),"Vertical wheel propagated from a mid-document position")
cdp("Emulation.setTouchEmulationEnabled",enabled=False); cdp("Emulation.clearDeviceMetricsOverride")
passed=sum(ok for _,ok,_ in results)
lines=["# K-Signal Browser Harness QA Report","",f"- Target: `{BASE}/articles/card_02.html`",f"- Result: **{passed}/{len(results)} passed**","","## Article-ending tests","","| Test | Result | Note |","|---|---:|---|"]
for name,ok,note in results: lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {note} |")
lines += ["","Mobile validation used a 390×844 touch viewport. The vertical scroll-propagation assertion ran from mid-document to avoid a false failure at the article's lower scroll boundary.",""]
REPORT.write_text("\n".join(lines),encoding="utf-8")
print(f"FINAL SUMMARY {passed}/{len(results)}")
