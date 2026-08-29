"""Safety contracts for retired and Preview-only publication entry points."""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

import generate_grounded_notes
import generate_notes
import episode_synthesizer
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


@pytest.mark.parametrize(
    "relative_path",
    ["missing", "empty", "nested/deep", "nested/..", "nested/../normalized"],
)
def test_preview_validator_rejects_every_descendant_of_the_formal_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_path: str,
) -> None:
    formal_root = tmp_path / "formal-publication"
    formal_root.mkdir()
    destination = formal_root / relative_path
    if relative_path == "empty":
        destination.mkdir()
    monkeypatch.setattr(episode_synthesizer, "OUTPUT_DIR", formal_root)

    with pytest.raises(ValueError, match="formal publication root"):
        episode_synthesizer.validate_preview_output_directory(destination)


def test_preview_validator_rejects_a_symlink_parent_resolving_into_the_formal_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    formal_root = tmp_path / "formal-publication"
    formal_root.mkdir()
    alias = tmp_path / "formal-alias"
    alias.symlink_to(formal_root, target_is_directory=True)
    monkeypatch.setattr(episode_synthesizer, "OUTPUT_DIR", formal_root)

    with pytest.raises(ValueError, match="formal publication root"):
        episode_synthesizer.validate_preview_output_directory(alias / "missing")


def test_preview_validator_allows_a_component_distinct_common_prefix_sibling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    formal_root = tmp_path / "formal-publication"
    formal_root.mkdir()
    sibling = tmp_path / "formal-publication-preview"
    monkeypatch.setattr(episode_synthesizer, "OUTPUT_DIR", formal_root)

    assert episode_synthesizer.validate_preview_output_directory(sibling) == sibling


def test_contained_destinations_do_not_construct_cli_or_grounded_collaborators(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    formal_root = tmp_path / "formal-publication"
    formal_root.mkdir()
    destination = formal_root / "missing"
    monkeypatch.setattr(episode_synthesizer, "OUTPUT_DIR", formal_root)

    class MustNotConstructSynthesizer:
        def __init__(self) -> None:
            raise AssertionError("contained Preview destination reached synthesizer")

    monkeypatch.setattr(__import__("cli"), "EpisodeNoteSynthesizer", MustNotConstructSynthesizer)
    with pytest.raises(ValueError, match="formal publication root"):
        __import__("cli").cmd_synthesize(
            type(
                "Args",
                (),
                {
                    "output_dir": destination,
                    "out_dir": None,
                    "resolver": "composite",
                    "workers": 1,
                    "dry_run": False,
                    "episode": 1,
                    "episodes": None,
                },
            )()
        )
    with pytest.raises(ValueError, match="formal publication root"):
        __import__("cli").cmd_topics(
            type(
                "Args",
                (),
                {
                    "generate": True,
                    "list": False,
                    "topic": None,
                    "output_dir": destination,
                    "out_dir": None,
                    "audit": False,
                },
            )()
        )

    monkeypatch.setattr(generate_grounded_notes, "EpisodeNoteSynthesizer", MustNotConstructSynthesizer)
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate_grounded_notes.py", "--output-dir", str(destination)],
    )
    with pytest.raises(SystemExit) as error:
        generate_grounded_notes.main()
    assert error.value.code == 2
