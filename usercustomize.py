"""Narrow command hooks for predeploy fixes around recovered source modules."""
from __future__ import annotations

from pathlib import Path
import sys


if Path(sys.argv[0]).name == "main.py" and len(sys.argv) > 1:
    if sys.argv[1] == "export-social":
        import ksignal.issue_builder as issue_builder
        from ksignal.social_exporter import export_social
        issue_builder.export_social = export_social
    elif sys.argv[1] == "create-host-package":
        import core.host_packager as host_packager
        host_packager.NETLIFY_HEADERS = """/*
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
