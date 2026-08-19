"""Final Issue stabilization, including controlled Pagefind alias blocks."""
from __future__ import annotations
import importlib.machinery,importlib.util
import json,re
from html import escape
from pathlib import Path
_P=Path(__file__).with_name("site_stabilization.pre_metadata_presence_fix.py")
_L=importlib.machinery.SourceFileLoader("ksignal._stabilization_before_metadata",str(_P))
_S=importlib.util.spec_from_loader(_L.name,_L); _M=importlib.util.module_from_spec(_S); _L.exec_module(_M)
CARD_ALIASES=_M.CARD_ALIASES; LANE_ALIASES=_M.LANE_ALIASES
def _block(values):
    text=" · ".join(dict.fromkeys(values))
    return f'<div class="search-aliases" aria-hidden="true" data-pagefind-body data-pagefind-meta="aliases">{text}</div>'
def _current_metadata(issue:Path)->None:
    cards_path=issue/"editorial_cards.json"
    if not cards_path.exists(): return
    cards=json.loads(cards_path.read_text(encoding="utf-8"))
    alias_pattern=re.compile(r'<div class="search-aliases".*?</div>',re.DOTALL)
    home_aliases=[]
    for index,card in enumerate(cards,1):
        aliases=[card.get("title", ""),*card.get("watch_next",[]),*LANE_ALIASES.get(card.get("lane","").title(),[])]
        aliases=[value for value in aliases if value]
        home_aliases.extend(aliases)
        path=issue/"articles"/f"card_{index:02d}.html"
        if not path.exists(): continue
        html=path.read_text(encoding="utf-8")
        html=alias_pattern.sub(_block(aliases),html,count=1)
        if card.get("video_embed_url") or card.get("video_url"):
            description=card.get("hero_caption") or card.get("title") or "K-Signal story video"
            iframe_title=escape(f"{description} — YouTube video",quote=True)
            html=re.sub(r'(<iframe\b[^>]*\btitle=")[^"]*(")',rf'\g<1>{iframe_title}\2',html,count=1)
        html=re.sub(
            r'<a\b(?![^>]*\btarget=)(?=[^>]*\bhref="https?://)([^>]*)>',
            r'<a\1 target="_blank" rel="noopener noreferrer">',
            html,
        )
        path.write_text(html,encoding="utf-8")
    home=issue/"newsletter.html"
    if home.exists():
        html=home.read_text(encoding="utf-8")
        home.write_text(alias_pattern.sub(_block(home_aliases),html,count=1),encoding="utf-8")
def stabilize_issue(issue_dir:str|Path)->None:
    _M.stabilize_issue(issue_dir); issue=Path(issue_dir)
    for card_id,aliases in CARD_ALIASES.items():
        path=issue/"articles"/f"{card_id}.html"; html=path.read_text(encoding="utf-8")
        if 'class="search-aliases"' not in html: path.write_text(html.replace("</main>",_block(aliases)+"</main>",1),encoding="utf-8")
    home=issue/"newsletter.html"; html=home.read_text(encoding="utf-8")
    all_aliases=[x for values in CARD_ALIASES.values() for x in values]+[x for values in LANE_ALIASES.values() for x in values]
    if 'class="search-aliases"' not in html: home.write_text(html.replace("</main>",_block(all_aliases)+"</main>",1),encoding="utf-8")
    _current_metadata(issue)
