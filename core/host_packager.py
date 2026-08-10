"""Host packager wrapper that makes audited security headers reproducible."""
from __future__ import annotations
import importlib.machinery, importlib.util
from pathlib import Path
_PATH = Path(__file__).with_name("host_packager.pre_watchlist.py")
_LOADER = importlib.machinery.SourceFileLoader("core._host_packager_pre_watchlist", str(_PATH))
_SPEC = importlib.util.spec_from_loader(_LOADER.name, _LOADER)
_MODULE = importlib.util.module_from_spec(_SPEC); _LOADER.exec_module(_MODULE)
NETLIFY_HEADERS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
  X-Frame-Options: SAMEORIGIN

/*.html
  Content-Type: text/html; charset=utf-8

/articles/*.html
  Content-Type: text/html; charset=utf-8

/search/*.json
  Content-Type: application/json; charset=utf-8

/pagefind/*
  X-Content-Type-Options: nosniff
"""
_MODULE.NETLIFY_HEADERS = NETLIFY_HEADERS
for _name, _value in vars(_MODULE).items():
    if not _name.startswith("__") and _name != "NETLIFY_HEADERS": globals()[_name] = _value
