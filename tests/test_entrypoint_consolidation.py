import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ksignal.engine.cli import ENGINE_COMMANDS, register_engine_commands, run_command


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LEGACY_COMMANDS = (
    "run",
    "inspect-url",
    "build-from-inspect",
    "enrich-media",
    "rebuild-issue",
    "export-social",
    "check-links",
    "repair-links",
    "publish-audit",
    "create-host-package",
    "create-distribution-pack",
    "create-instagram-pack",
    "scout-creatives",
    "render-reels",
    "push-webhook",
)
LEGACY_HELP_COMMANDS = (
    "run",
    "inspect-url",
    "rebuild-issue",
    "export-social",
    "create-host-package",
    "create-instagram-pack",
    "render-reels",
    "push-webhook",
)


def run_entrypoint(*arguments, env=None):
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def test_main_help_includes_legacy_and_engine_commands():
    result = run_entrypoint("main.py", "--help")
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    help_text = result.stdout.decode()
    for command in (*LEGACY_COMMANDS, *ENGINE_COMMANDS):
        assert command in help_text


def test_compatibility_help_includes_engine_commands():
    result = run_entrypoint("ksignal_engine.py", "--help")
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    help_text = result.stdout.decode()
    for command in ENGINE_COMMANDS:
        assert command in help_text


def test_source_seed_entrypoints_match_with_cp1252_parent_encoding():
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "cp1252"
    arguments = ("source-seed", "--issue", "002", "--lane", "fandom")
    main_result = run_entrypoint("main.py", *arguments, env=child_env)
    compatibility_result = run_entrypoint("ksignal_engine.py", *arguments, env=child_env)

    decoded_outputs = []
    for result in (main_result, compatibility_result):
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        decoded = result.stdout.decode("utf-8")
        assert "한국" in decoded
        decoded_outputs.append(json.loads(decoded))
    assert decoded_outputs[0] == decoded_outputs[1]


@pytest.mark.parametrize("command", LEGACY_HELP_COMMANDS)
def test_legacy_help_commands_remain_available(command):
    result = run_entrypoint("main.py", command, "--help")
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def make_engine_parser():
    parser = argparse.ArgumentParser()
    register_engine_commands(parser.add_subparsers(required=True))
    return parser


@pytest.mark.parametrize("command", ENGINE_COMMANDS)
def test_shared_registration_dispatch_contract(command):
    args = make_engine_parser().parse_args([command])
    assert args.engine_command == command
    assert args.func is run_command


def test_shared_registration_default_contract():
    args = make_engine_parser().parse_args(["source-seed"])
    assert args.issue == "002"
    assert args.lane is None
    assert args.lanes is None
    assert args.candidate == "card_candidate_01"
    assert args.provider == "all"
    assert args.max_items == 20
    assert args.window == "24h"
    assert args.hashtags == ""
    assert args.urls is None
    assert args.auto_queue is False
    assert args.auto_queue_threshold == 7.5


@pytest.mark.parametrize(
    ("option", "value"),
    (("--lane", "invalid"), ("--provider", "invalid"), ("--window", "invalid")),
)
def test_shared_registration_rejects_invalid_choices(option, value):
    with pytest.raises(SystemExit):
        make_engine_parser().parse_args(["source-seed", option, value])
