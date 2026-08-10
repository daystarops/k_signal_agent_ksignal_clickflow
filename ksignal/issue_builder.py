"""Source-level stabilization wrapper for the recovered Issue builder."""
from __future__ import annotations
import importlib.machinery, importlib.util
from pathlib import Path
from .site_stabilization import stabilize_issue

_PATH = Path(__file__).with_name("issue_builder.pre_watchlist.py")
_LOADER = importlib.machinery.SourceFileLoader("ksignal._issue_builder_pre_watchlist", str(_PATH))
_SPEC = importlib.util.spec_from_loader(_LOADER.name, _LOADER)
_MODULE = importlib.util.module_from_spec(_SPEC); _LOADER.exec_module(_MODULE)
MOBILE_CSS = """
.search-aliases{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}
@media(max-width:760px){html,body{max-width:100%;overflow-x:clip}.site-header{padding-left:max(12px,env(safe-area-inset-left));padding-right:max(12px,env(safe-area-inset-right))}.lane-nav{row-gap:4px}.lane-trigger,.search-toggle,.comment-toggle,.pill,.read-signal,.site-footer a,.related-signals-list a,.more-from-issue-list a{min-height:44px}.lane-trigger,.read-signal,.site-footer a,.related-signals-list a,.more-from-issue-list a{display:inline-flex;align-items:center}.search-typeahead a{min-height:48px}.article-body p a:not(.pill){display:inline;padding:10px 3px;margin:-10px -3px;line-height:2.55;box-decoration-break:clone;-webkit-box-decoration-break:clone}.article-head h1{font-size:clamp(30px,9.4vw,36px);overflow-wrap:anywhere}.article-head .dek{font-size:clamp(16px,4.6vw,17px)!important}.hero img,.story-preview img{max-width:100%;object-fit:cover}.embed{overflow:hidden}.receipts .pill{display:inline-flex;align-items:center}.comment-panel input,.comment-panel textarea,.search-form input{font-size:16px}.related-signals-list,.more-from-issue-list{overscroll-behavior-inline:contain;scroll-snap-type:none}.site-footer nav{align-items:center}.site-footer p{white-space:normal}}
@media(max-width:340px){.site-header{padding-left:8px;padding-right:8px}.brand img{width:124px}.lane-nav{gap:2px}.lane-trigger{font-size:9px;padding-left:2px;padding-right:2px}.home-shell,.article-shell,.policy-shell{margin-left:4px;margin-right:4px}.article-shell{padding-left:10px;padding-right:10px}.story-preview.supporting{grid-template-columns:88px minmax(0,1fr)}.site-search.is-open{width:calc(100vw - 16px);right:8px}.search-typeahead{left:8px;right:8px}}
"""
_MODULE.CSS += MOBILE_CSS; _MODULE._I.CSS = _MODULE.CSS
for _name, _value in vars(_MODULE).items():
    if not _name.startswith("__"): globals()[_name] = _value
_before = _MODULE._I._write_editorial_issue
def _write_editorial_issue(editorial, issue, output_root, require_media):
    result = _before(editorial, issue, output_root, require_media)
    stabilize_issue(Path(output_root) / issue)
    return result
_MODULE._I._write_editorial_issue = _write_editorial_issue
