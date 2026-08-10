"""Combined stable output normalization for Issue builds."""
from __future__ import annotations
import importlib.machinery,importlib.util
from pathlib import Path
_PATH=Path(__file__).with_name("site_stabilization.pre_pagefind_fix.py")
_L=importlib.machinery.SourceFileLoader("ksignal._stabilization_base_final",str(_PATH))
_S=importlib.util.spec_from_loader(_L.name,_L); _M=importlib.util.module_from_spec(_S); _L.exec_module(_M)
for _n in ("CARD_ALIASES","LANE_ALIASES","enrich_search_indexes","stabilize_html"):
    globals()[_n]=getattr(_M,_n)
def stabilize_issue(issue_dir:str|Path)->None:
    issue=Path(issue_dir); enrich_search_indexes(issue); stabilize_html(issue)
    home=issue/"newsletter.html"
    if home.exists():
        html=home.read_text(encoding="utf-8")
        lane_text=" · ".join(dict.fromkeys(x for values in LANE_ALIASES.values() for x in values))
        marker='</div></main>'
        if 'class="search-aliases"' in html and lane_text not in html:
            html=html.replace(marker,f' · {lane_text}{marker}',1); home.write_text(html,encoding="utf-8")
    script=issue/"assets"/"ksignal.js"
    if not script.exists(): return
    text=script.read_text(encoding="utf-8")
    text=text.replace("import(search.dataset.pagefindUrl)","import(new URL(search.dataset.pagefindUrl,document.baseURI).href)")
    old="toggle.addEventListener('click',()=>{if(search.classList.contains('is-open')&&mobile())closeSearch(search);else{open();input.focus()}})"
    new="toggle.addEventListener('pointerdown',()=>toggle.dataset.wasOpen=String(search.classList.contains('is-open')));toggle.addEventListener('click',()=>{if(toggle.dataset.wasOpen==='true'&&mobile())closeSearch(search);else{open();input.focus()}})"
    script.write_text(text.replace(old,new),encoding="utf-8")
