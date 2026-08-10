"""Final Issue stabilization, including controlled Pagefind alias blocks."""
from __future__ import annotations
import importlib.machinery,importlib.util
from pathlib import Path
_P=Path(__file__).with_name("site_stabilization.pre_metadata_presence_fix.py")
_L=importlib.machinery.SourceFileLoader("ksignal._stabilization_before_metadata",str(_P))
_S=importlib.util.spec_from_loader(_L.name,_L); _M=importlib.util.module_from_spec(_S); _L.exec_module(_M)
CARD_ALIASES=_M.CARD_ALIASES; LANE_ALIASES=_M.LANE_ALIASES
def _block(values):
    text=" · ".join(dict.fromkeys(values))
    return f'<div class="search-aliases" aria-hidden="true" data-pagefind-body data-pagefind-meta="aliases">{text}</div>'
def stabilize_issue(issue_dir:str|Path)->None:
    _M.stabilize_issue(issue_dir); issue=Path(issue_dir)
    for card_id,aliases in CARD_ALIASES.items():
        path=issue/"articles"/f"{card_id}.html"; html=path.read_text(encoding="utf-8")
        if 'class="search-aliases"' not in html: path.write_text(html.replace("</main>",_block(aliases)+"</main>",1),encoding="utf-8")
    home=issue/"newsletter.html"; html=home.read_text(encoding="utf-8")
    all_aliases=[x for values in CARD_ALIASES.values() for x in values]+[x for values in LANE_ALIASES.values() for x in values]
    if 'class="search-aliases"' not in html: home.write_text(html.replace("</main>",_block(all_aliases)+"</main>",1),encoding="utf-8")
