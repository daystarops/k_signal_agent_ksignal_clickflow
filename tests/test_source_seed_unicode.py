import json
import os
from pathlib import Path
import subprocess
import sys


def test_source_seed_emits_literal_korean_as_utf8_with_narrow_stdout():
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"

    result = subprocess.run(
        [
            sys.executable,
            "ksignal_engine.py",
            "source-seed",
            "--issue",
            "002",
            "--lane",
            "fandom",
        ],
        cwd=repository_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )

    assert result.returncode == 0
    stdout_text = result.stdout.decode("utf-8")
    assert any("\uac00" <= char <= "\ud7a3" for char in stdout_text)
    payload = json.loads(stdout_text)
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["lane"] == "fandom"
    assert b"UnicodeEncodeError" not in result.stderr
