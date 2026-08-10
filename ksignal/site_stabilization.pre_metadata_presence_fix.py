"""Final stabilization hook with touch and DOM-click compatible toggles."""
from __future__ import annotations
import importlib.machinery,importlib.util
from pathlib import Path
_P=Path(__file__).with_name("site_stabilization.pre_dom_click_fix.py")
_L=importlib.machinery.SourceFileLoader("ksignal._stabilization_before_dom_click",str(_P))
_S=importlib.util.spec_from_loader(_L.name,_L); _M=importlib.util.module_from_spec(_S); _L.exec_module(_M)
CARD_ALIASES=_M.CARD_ALIASES; LANE_ALIASES=_M.LANE_ALIASES
def stabilize_issue(issue_dir:str|Path)->None:
    _M.stabilize_issue(issue_dir)
    script=Path(issue_dir)/"assets"/"ksignal.js"
    if not script.exists(): return
    text=script.read_text(encoding="utf-8")
    old="toggle.addEventListener('click',()=>{if(toggle.dataset.wasOpen==='true'&&mobile())closeSearch(search);else{open();input.focus()}})"
    new="toggle.addEventListener('click',()=>{const pointerState=toggle.dataset.wasOpen;delete toggle.dataset.wasOpen;const shouldClose=pointerState==='true'||(pointerState===undefined&&search.classList.contains('is-open'));if(shouldClose&&mobile())closeSearch(search);else{open();input.focus()}})"
    script.write_text(text.replace(old,new),encoding="utf-8")

