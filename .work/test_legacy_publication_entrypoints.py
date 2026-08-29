"""Safety contracts for retired and Preview-only publication entry points."""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

import generate_grounded_notes
import generate_notes
from episode_synthesizer import EpisodeNoteSynthesizer, OUTPUT_DIR


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def formal_tree_status() -> str:
    result = subprocess.run(
        ["git", "status", "--short", "--", "gooaye-youtube-notes"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        check=True,
    )
    return result.stdout


@pytest.fixture(scope="module", autouse=True)
def formal_tree_guard():
    before = tree_bytes(OUTPUT_DIR)
    status_before = formal_tree_status()
    yield
    assert tree_bytes(OUTPUT_DIR) == before
    assert formal_tree_status() == status_before


def test_legacy_summary_writer_is_retired_before_it_can_read_or_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_source = inspect.getsource(generate_notes.main)
    assert "raise SystemExit" in main_source
    assert "write_text" not in main_source
    assert "rmtree" not in main_source
    assert "gooaye-youtube-notes" not in inspect.getsource(generate_notes)
    monkeypatch.setattr(sys, "argv", ["generate_notes.py"])

    with pytest.raises(SystemExit, match="retired"):
        generate_notes.main()


def test_grounded_entry_point_requires_an_explicit_preview_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MustNotConstructSynthesizer:
        def __init__(self) -> None:
            raise AssertionError("missing Preview destination reached synthesizer")

    monkeypatch.setattr(generate_grounded_notes, "EpisodeNoteSynthesizer", MustNotConstructSynthesizer)
    monkeypatch.setattr(sys, "argv", ["generate_grounded_notes.py"])

    with pytest.raises(SystemExit) as error:
        generate_grounded_notes.main()

    assert error.value.code == 2


def test_grounded_entry_point_rejects_the_formal_publication_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MustNotConstructSynthesizer:
        def __init__(self) -> None:
            raise AssertionError("formal destination reached synthesizer")

    monkeypatch.setattr(generate_grounded_notes, "EpisodeNoteSynthesizer", MustNotConstructSynthesizer)
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate_grounded_notes.py", "--output-dir", str(OUTPUT_DIR)],
    )

    with pytest.raises(SystemExit) as error:
        generate_grounded_notes.main()

    assert error.value.code == 2


@pytest.mark.parametrize("destination", [None, OUTPUT_DIR])
def test_synthesize_all_rejects_implicit_or_formal_destinations(destination: Path | None) -> None:
    with pytest.raises(ValueError, match="Preview output directory"):
        EpisodeNoteSynthesizer.synthesize_all(object(), output_dir=destination)
