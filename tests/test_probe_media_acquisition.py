import pytest

import scripts.probe_media_acquisition as probe


def test_help_does_not_perform_network_acquisition(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("network acquisition must not run for --help")

    monkeypatch.setattr(probe, "search_youtube_media", forbidden)
    monkeypatch.setattr(probe, "search_wikimedia_commons", forbidden)
    monkeypatch.setattr(probe, "search_openverse", forbidden)

    with pytest.raises(SystemExit) as exc_info:
        probe.main(["--help"])

    assert exc_info.value.code == 0
    assert "usage:" in capsys.readouterr().out
