"""Final stabilization hook, including document-relative Pagefind loading."""
from __future__ import annotations
import importlib.machinery, importlib.util
from pathlib import Path

_PATH = Path(__file__).with_name("site_stabilization.pre_pagefind_fix.py")
_LOADER = importlib.machinery.SourceFileLoader("ksignal._site_stabilization_pre_pagefind", str(_PATH))
_SPEC = importlib.util.spec_from_loader(_LOADER.name, _LOADER)
_MODULE = importlib.util.module_from_spec(_SPEC); _LOADER.exec_module(_MODULE)
for _name, _value in vars(_MODULE).items():
    if not _name.startswith("__"): globals()[_name] = _value

_before = _MODULE.stabilize_issue
def stabilize_issue(issue_dir: str | Path) -> None:
    _before(issue_dir)
    script = Path(issue_dir) / "assets" / "ksignal.js"
    if script.exists():
        text = script.read_text(encoding="utf-8")
        text = text.replace("import(search.dataset.pagefindUrl)", "import(new URL(search.dataset.pagefindUrl,document.baseURI).href)")
        script.write_text(text, encoding="utf-8")
