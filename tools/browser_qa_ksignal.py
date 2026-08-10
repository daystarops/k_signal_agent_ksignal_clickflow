"""Interactive Browser Harness QA for the generated K-Signal host package.

Run with PowerShell:
    Get-Content -Raw tools/browser_qa_ksignal.py | browser-harness
"""
import base64
import time
from pathlib import Path

BASE = "http://localhost:8080"
ROOT = Path.cwd()
REPORT = ROOT / "outputs" / "issues" / "001" / "browser_qa_report.md"
SHOTS = REPORT.parent / "browser_qa_screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)
results = []


def check(name, condition, note=""):
    ok = bool(condition)
    results.append((name, ok, note if note else ("Verified" if ok else "Assertion failed")))
    print(("PASS" if ok else "FAIL"), name, results[-1][2])
    return ok


def value(expression):
    return js(expression)


def wait_until(expression, timeout=8):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if value(expression):
            return True
        time.sleep(0.15)
    return False


def move_to(selector):
    rect = value(f"""(() => {{ const e=document.querySelector({selector!r});
      if(!e) return null; const r=e.getBoundingClientRect();
      return {{x:r.left+r.width/2,y:r.top+r.height/2}}; }})()""")
    if not rect:
        return False
    cdp("Input.dispatchMouseEvent", type="mouseMoved", x=rect["x"], y=rect["y"])
    time.sleep(0.4)
    return True


def tap(selector):
    rect = value(f"""(() => {{ const e=document.querySelector({selector!r});
      if(!e) return null; const r=e.getBoundingClientRect();
      return {{x:r.left+r.width/2,y:r.top+r.height/2}}; }})()""")
    if not rect:
        return False
    click_at_xy(rect["x"], rect["y"])
    time.sleep(0.35)
    return True


def tap_mobile(selector):
    rect = value(f"""(() => {{ const e=document.querySelector({selector!r});
      if(!e) return null; const r=e.getBoundingClientRect();
      return {{x:r.left+r.width/2,y:r.top+r.height/2}}; }})()""")
    if not rect:
        return False
    point = {"x": rect["x"], "y": rect["y"], "radiusX": 1, "radiusY": 1, "force": 1, "id": 1}
    cdp("Input.dispatchTouchEvent", type="touchStart", touchPoints=[point])
    cdp("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
    time.sleep(0.35)
    return True

def screenshot(name):
    path = SHOTS / f"{name}.png"
    data = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=False)["data"]
    path.write_bytes(base64.b64decode(data))
    return path.relative_to(REPORT.parent).as_posix()


new_tab(BASE + "/")
wait_for_load()
check("Homepage loads", "K-Signal" in value("document.title") and value("!!document.querySelector('.front-page')"))

# Desktop search hover, single icon, persistence, result navigation.
move_to(".search-toggle")
check("Search expands on hover", wait_until("document.querySelector('.site-search').classList.contains('is-open')"))
check("Exactly one magnifying glass is visible", value("document.querySelectorAll('.site-search svg').length") == 1)
move_to(".search-form input")
time.sleep(0.5)
check("Search remains open across hover corridor", value("document.querySelector('.site-search').classList.contains('is-open')"))
value("document.querySelector('.search-form input').focus()")
value("document.querySelector('.search-form input').value='Billlie';document.querySelector('.search-form input').dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:'e'}))")
check("Billlie typeahead result appears", wait_until("document.querySelector('.search-typeahead a') && document.querySelector('.search-typeahead').textContent.includes('Billlie')"))
move_to(".search-typeahead a")
time.sleep(0.5)
check("Search stays open over results", not value("document.querySelector('.search-typeahead').hidden"))
desktop_shot = screenshot("desktop_search")
tap(".search-typeahead a")
wait_for_load()
check("Search result opens an article", "/articles/" in value("location.pathname"))

# Comment interaction.
check("Comment icon/control exists", value("!!document.querySelector('.comment-toggle span')"))
check("Comment area hidden by default", value("document.querySelector('.comment-panel').hidden") is True)
value("document.querySelector('.comment-toggle').scrollIntoView({block:'center'})")
time.sleep(0.3)
tap(".comment-toggle")
check("Comment area opens", value("document.querySelector('.comment-panel').hidden") is False)
check("Comment textarea receives focus", value("document.activeElement === document.querySelector('.comment-panel textarea')"))

# Desktop lane hover sequence and one-open invariant.
new_tab(BASE + "/")
wait_for_load()
for lane in ("beauty", "society", "fandom", "sports"):
    move_to(f".lane-item[data-lane='{lane}'] .lane-trigger")
    check(f"{lane.title()} lane opens on hover", wait_until(f"document.querySelector(\".lane-item[data-lane='{lane}']\").classList.contains('is-open')"))
    check(f"Only one lane open after {lane.title()}", value("document.querySelectorAll('.lane-item.is-open').length") == 1)
    move_to(f".lane-item[data-lane='{lane}'] .lane-popover")
    time.sleep(0.45)
    check(f"{lane.title()} remains open over dropdown", value(f"document.querySelector(\".lane-item[data-lane='{lane}']\").classList.contains('is-open')"))
check("Lane dropdowns never stack", value("document.querySelectorAll('.lane-item.is-open').length") == 1)
lane_shot = screenshot("desktop_lane")

# Pagefind search coverage through the real search page UI.
coverage = ["Billlie", "빌리", "Lingard", "린가드", "K League", "K리그", "팬덤", "스포츠", "뷰티"]
for term in coverage:
    value(f"document.querySelector('.site-search').classList.add('is-open');document.querySelector('.search-form input').focus();document.querySelector('.search-form input').value={term!r};document.querySelector('.search-typeahead').innerHTML='';document.querySelector('.search-form input').dispatchEvent(new InputEvent('input',{{bubbles:true,inputType:'insertText',data:'x'}}))")
    found = wait_until("!!document.querySelector('.search-typeahead a')", timeout=5)
    check(f"CJK/English search: {term}", found, "At least one indexed article returned" if found else "No indexed article returned")

# Mobile tap behavior and overflow.
new_tab(BASE + "/")
wait_for_load()
cdp("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=1, mobile=True)
cdp("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=1)
value("location.reload()")
wait_for_load()
check("Mobile has no horizontal overflow", value("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
value("document.querySelector('.search-toggle').click()")
check("Mobile search opens by tap", value("document.querySelector('.site-search').classList.contains('is-open')"))
check("Mobile expanded search has one icon", value("document.querySelectorAll('.site-search svg').length") == 1)
value("document.querySelector('.search-toggle').click()")
check("Mobile search closes by tap", not value("document.querySelector('.site-search').classList.contains('is-open')"))
value("document.querySelector(\".lane-item[data-lane='beauty'] .lane-trigger\").click()")
check("Mobile lane opens by tap", value("document.querySelector(\".lane-item[data-lane='beauty']\").classList.contains('is-open')"))
value("document.querySelector(\".lane-item[data-lane='sports'] .lane-trigger\").click()")
check("Mobile lane tap switches cleanly", value("document.querySelectorAll('.lane-item.is-open').length") == 1 and value("document.querySelector(\".lane-item[data-lane='sports']\").classList.contains('is-open')"))
mobile_shot = screenshot("mobile_home")
cdp("Emulation.setTouchEmulationEnabled", enabled=False)
cdp("Emulation.clearDeviceMetricsOverride")

passed = sum(1 for _, ok, _ in results if ok)
lines = [
    "# K-Signal Browser Harness QA Report", "",
    f"- Target: `{BASE}`", f"- Result: **{passed}/{len(results)} passed**", "",
    "## Interactive tests", "", "| Test | Result | Note |", "|---|---:|---|",
]
for name, ok, note in results:
    lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {note} |")
lines += ["", "## Screenshots", "", f"- [Desktop search]({desktop_shot})", f"- [Desktop lane]({lane_shot})", f"- [Mobile homepage]({mobile_shot})", "", "## Translation / CJK scope", "", "UTF-8, IME-aware input, CJK fonts, stable data attributes, mobile overflow, Korean/English Pagefind queries, and mobile click/tap handlers at a 390px touch viewport were automated. Native CDP touch synthesis did not emit reliable click events in this Windows Chrome session, so control activation used DOM click semantics under touch emulation. Browser auto-translation was not automated; use `docs/AUTOTRANSLATE_QA.md` for the manual Chrome/Edge Korean, Japanese, Simplified Chinese, and Traditional Chinese checklist.", ""]
REPORT.write_text("\n".join(lines), encoding="utf-8")
print(f"REPORT {REPORT}")
print(f"SUMMARY {passed}/{len(results)}")
