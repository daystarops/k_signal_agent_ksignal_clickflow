from __future__ import annotations
import importlib.machinery, importlib.util
from pathlib import Path
from pydantic import ValidationError
from ksignal.article_package import ArticlePackage
from ksignal.article_package_renderer import render_article_package
_P=Path(__file__).with_name("_issue_builder_original.pyc")
_L=importlib.machinery.SourcelessFileLoader("ksignal._issue_builder_original",str(_P))
_S=importlib.util.spec_from_loader(_L.name,_L)
_I=importlib.util.module_from_spec(_S); _L.exec_module(_I)
for _n,_v in vars(_I).items():
    if not _n.startswith("__"): globals()[_n]=_v
_FCSS="""
.watermark-page main,.site-header,.site-footer{position:relative;z-index:1}.site-footer{max-width:1200px;margin:0 auto 24px;padding:18px 22px 20px;background:#fff;border-top:2px solid var(--navy);box-shadow:inset 0 1px 0 var(--red);display:flex;align-items:center;justify-content:space-between;gap:18px;color:var(--muted);font-size:11px}.site-footer nav{display:flex;flex-wrap:wrap;gap:10px 18px}.site-footer a{color:var(--navy);text-decoration:none}.site-footer a:hover,.site-footer a:focus{text-decoration:underline;text-decoration-color:var(--red);text-underline-offset:3px}.site-footer p{margin:0;white-space:nowrap}.policy-shell{max-width:760px;min-height:52vh;margin:0 auto 60px;padding:42px 42px 64px;background:#fff}.policy-shell header{border-top:2px solid var(--navy);padding-top:18px;margin-bottom:30px}.policy-shell h1{font:700 42px/1.08 Georgia,serif;margin:8px 0}.policy-shell>p,.policy-shell section p{font:16px/1.65 Georgia,serif}.policy-kicker{color:var(--red);font:800 10px/1.2 Arial,sans-serif!important;letter-spacing:.1em;text-transform:uppercase}.policy-shell section{border-top:1px solid var(--line);margin-top:30px;padding-top:22px}.policy-shell section h2{font:700 22px Georgia,serif}@media(max-width:760px){.site-footer{margin:0 8px 12px;padding:16px 14px;display:block}.site-footer nav{gap:12px 16px}.site-footer a{display:inline-block;padding:4px 0;min-height:24px}.site-footer p{margin-top:12px}.policy-shell{margin:0 8px 40px;padding:26px 16px 44px}.policy-shell h1{font-size:34px}}
"""
_ARTICLE_PACKAGE_CSS=""".article-package-depth{margin-top:32px}.article-package-depth .article-section{margin-top:32px}.article-package-depth .article-section h2,.article-package-depth .article-sources h2{margin:0 0 14px}.article-package-depth .article-section p{margin:0 0 1.25em}.supporting-media{margin:24px 0}.supporting-media img{display:block;max-width:100%;height:auto}.supporting-media figcaption{margin-top:8px;color:var(--muted);font-size:12px;line-height:1.45}.media-caption,.media-credit{display:inline}.article-sources{margin-top:36px}.article-sources li{margin:8px 0}"""
CSS=_I.CSS+_FCSS; _I.CSS=CSS
def _site_footer(prefix=""):
    links=(("about.html","About"),("contact.html","Contact"),("privacy.html","Privacy"),("privacy.html#cookie-settings","Cookie Settings"),("accessibility.html","Accessibility"),("terms.html","Terms"))
    nav="".join(f'<a href="{prefix}{p}">{label}</a>' for p,label in links)
    return f'<footer class="site-footer" data-pagefind-ignore><nav aria-label="Publication information">{nav}</nav><p>© 2026 K-Signal</p></footer>'
def _add_footer(path,prefix=""):
    html=path.read_text(encoding="utf-8")
    if 'class="site-footer"' in html:return
    footer=_site_footer(prefix)
    html=html.replace(INTERACTION_SCRIPT,footer+INTERACTION_SCRIPT,1) if INTERACTION_SCRIPT in html else html.replace("</body>",footer+"</body>",1)
    path.write_text(html,encoding="utf-8")
def _write_publication_pages(issue_dir):
    pages={"about.html":("About K-Signal","K-Signal reads Korean internet conversations for an English-speaking audience, preserving context instead of flattening it.","This is an early publication. Our editorial framing and public documentation will grow as the product matures."),"contact.html":("Contact","Questions, corrections, and thoughtful pushback are welcome.","For now, use the correction form on an article. A dedicated publication contact channel will be added as operations mature."),"privacy.html":("Privacy","K-Signal is keeping its privacy approach simple while the product is early.","We do not claim a mature account or advertising system. This notice will be expanded before either is introduced."),"accessibility.html":("Accessibility","K-Signal aims to make its reporting usable across devices, input methods, and assistive technology.","If something blocks access, please flag it through an article correction form. This statement will mature with the product and its support process."),"terms.html":("Terms","K-Signal is an editorial publication in development. Read and share links responsibly; source material remains subject to its original rights and context.","Full terms will be introduced if the service adds accounts, payments, or other features that require them.")}
    for filename,(title,intro,note) in pages.items():
        cookie='<section id="cookie-settings"><h2>Cookie settings</h2><p>K-Signal does not currently offer a separate cookie preference panel. If optional cookies are introduced, controls and clear choices will be added here.</p></section>' if filename=="privacy.html" else ""
        html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · K-Signal</title><style>{CSS}</style></head><body class="watermark-page">{_site_header("","newsletter.html")}<main class="policy-shell"><a class="article-back" href="newsletter.html">← K-Signal home</a><header><p class="policy-kicker">K-Signal publication notes</p><h1>{title}</h1></header><p>{intro}</p><p>{note}</p>{cookie}</main>{_site_footer()}{INTERACTION_SCRIPT}</body></html>'''
        (issue_dir/filename).write_text(html,encoding="utf-8")
_owa=_I._write_articles
def _load_article_packages(editorial,issue,issue_dir):
    package_dir=Path(issue_dir)/"article_packages"
    if not package_dir.is_dir():return []
    packages=[]
    for path in sorted(package_dir.glob("*.json")):
        try: packages.append(ArticlePackage.model_validate_json(path.read_text(encoding="utf-8")))
        except (OSError,UnicodeError,ValidationError,ValueError) as exc:
            raise ValueError(f"Invalid ArticlePackage {path}: {exc}") from exc
    slugs=[package.article_slug for package in packages]
    duplicates=sorted({slug for slug in slugs if slugs.count(slug)>1})
    if duplicates:raise ValueError(f"Duplicate ArticlePackage article_slug: {', '.join(duplicates)}")
    current={card.article_slug:card for card in editorial}
    for package in packages:
        if package.issue_id!=str(issue):
            raise ValueError(f"ArticlePackage issue_id mismatch for {package.article_slug}: expected {issue}, got {package.issue_id}")
        if package.article_slug not in current:
            raise ValueError(f"ArticlePackage article_slug has no EditorialCard: {package.article_slug}")
    return [(package,current[package.article_slug]) for package in packages]
def _write_articles(editorial,issue,issue_dir):
    result=_owa(editorial,issue,issue_dir)
    for package,card in _load_article_packages(editorial,issue,issue_dir):
        path=Path(issue_dir)/"articles"/f"{package.article_slug}.html"
        html=path.read_text(encoding="utf-8")
        anchor="<section><h2>Context & receipts</h2>"
        if anchor not in html:
            raise ValueError(f"ArticlePackage insertion anchor missing for {package.article_slug}: {anchor}")
        html=html.replace(anchor,render_article_package(package)+anchor,1)
        if "</style>" not in html:
            raise ValueError(f"ArticlePackage style anchor missing for {package.article_slug}: </style>")
        html=html.replace("</style>",_ARTICLE_PACKAGE_CSS+"</style>",1)
        path.write_text(html,encoding="utf-8")
    for article in (Path(issue_dir)/"articles").glob("*.html"):_add_footer(article,"../")
    return result
_I._write_articles=_write_articles
_ows=_I._write_search_indexes
def _write_search_indexes(cards,issue,issue_dir):
    result=_ows(cards,issue,issue_dir); _add_footer(Path(issue_dir)/"search.html"); return result
_I._write_search_indexes=_write_search_indexes
_owe=_I._write_editorial_issue
def _write_editorial_issue(editorial,issue,output_root,require_media):
    result=_owe(editorial,issue,output_root,require_media); issue_dir=Path(output_root)/issue; _add_footer(issue_dir/"newsletter.html"); _write_publication_pages(issue_dir); return result
_I._write_editorial_issue=_write_editorial_issue
