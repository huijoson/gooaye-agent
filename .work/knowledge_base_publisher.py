"""Read-only verification result types for Knowledge Base Publications."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


MANIFEST_FILENAME = "publication-manifest.json"
PUBLICATION_SCHEMA_VERSION = 1
_MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]*]\(([^)]+)\)")


class PublicationMode(str, Enum):
    MANAGED = "managed"
    LEGACY = "legacy"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PublicationArtifact:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class PublicationManifest:
    schema_version: int
    created_at: str
    source_episodes: tuple[int, ...]
    topic_catalog: tuple[str, ...]
    total_chapters: int
    total_seconds: int
    artifacts: tuple[PublicationArtifact, ...]


@dataclass(frozen=True)
class PublicationDefect:
    category: str
    message: str
    path: str = ""


@dataclass(frozen=True)
class PublicationVerification:
    mode: PublicationMode
    defects: tuple[PublicationDefect, ...]
    artifact_count: int = 0
    episode_count: int = 0
    topic_count: int = 0

    @property
    def is_valid(self) -> bool:
        return not self.defects


class _InvalidManifest(ValueError):
    pass


class KnowledgeBasePublisher:
    """Own the public, non-mutating publication verification seam."""

    def verify(self, root: Path) -> PublicationVerification:
        """Read a Manifest-managed publication without changing its bytes."""
        root = Path(root)
        if not root.exists():
            return PublicationVerification(PublicationMode.UNKNOWN, ())
        if root.is_symlink() or not root.is_dir():
            return PublicationVerification(
                PublicationMode.UNKNOWN,
                (
                    PublicationDefect(
                        "ownership", "Publication root is not an owned directory.", str(root)
                    ),
                ),
            )
        manifest_path = root / MANIFEST_FILENAME
        if not manifest_path.exists():
            if not any(root.iterdir()):
                return PublicationVerification(PublicationMode.UNKNOWN, ())
            return PublicationVerification(
                PublicationMode.UNKNOWN,
                (
                    PublicationDefect(
                        "ownership", "Non-empty root has no publication Manifest.", str(root)
                    ),
                ),
            )
        try:
            manifest = self._read_manifest(manifest_path)
        except _InvalidManifest as exc:
            return PublicationVerification(
                PublicationMode.MANAGED,
                (PublicationDefect("manifest", str(exc), MANIFEST_FILENAME),),
            )
        defects: list[PublicationDefect] = []
        actual_paths = _regular_paths(Path(root))
        manifest_paths = {artifact.path for artifact in manifest.artifacts}
        for path in sorted(_symlink_paths(Path(root))):
            defects.append(PublicationDefect("unsafe_path", "Publication must not contain symlinks.", path))
        for path in sorted(actual_paths - manifest_paths):
            defects.append(PublicationDefect("stale", "File is not recorded by the Manifest.", path))
        for path in sorted(_required_paths(manifest) - actual_paths.intersection(manifest_paths)):
            defects.append(PublicationDefect("missing", "Required publication artifact is missing.", path))
        for artifact in manifest.artifacts:
            artifact_path = Path(root) / artifact.path
            if not artifact_path.is_file():
                defects.append(PublicationDefect("missing", "Manifest artifact is missing.", artifact.path))
                continue
            if artifact_path.stat().st_size != artifact.size_bytes:
                defects.append(PublicationDefect("size", "Artifact byte size differs from Manifest.", artifact.path))
            if _sha256(artifact_path) != artifact.sha256:
                defects.append(
                    PublicationDefect("digest", "Artifact SHA-256 differs from Manifest.", artifact.path)
                )
        defects.extend(_broken_markdown_links(Path(root), actual_paths))
        return PublicationVerification(
            PublicationMode.MANAGED,
            tuple(defects),
            artifact_count=len(manifest.artifacts),
            episode_count=len(manifest.source_episodes),
            topic_count=len(manifest.topic_catalog),
        )

    @staticmethod
    def _read_manifest(path: Path) -> PublicationManifest:
        try:
            decoded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _InvalidManifest(f"Manifest cannot be decoded: {exc}") from exc
        if not isinstance(decoded, dict):
            raise _InvalidManifest("Manifest must be a JSON object.")
        required = {
            "schema_version",
            "created_at",
            "source_episodes",
            "topic_catalog",
            "total_chapters",
            "total_seconds",
            "artifacts",
        }
        if set(decoded) != required:
            raise _InvalidManifest("Manifest fields do not match schema version 1.")
        schema_version = _required_int(decoded, "schema_version")
        if schema_version != PUBLICATION_SCHEMA_VERSION:
            raise _InvalidManifest(f"Unsupported Manifest schema version: {schema_version}.")
        raw_artifacts = decoded.get("artifacts")
        if not isinstance(raw_artifacts, list):
            raise _InvalidManifest("Manifest artifacts must be an array.")
        artifacts = tuple(_decode_artifact(value) for value in raw_artifacts)
        if len({artifact.path for artifact in artifacts}) != len(artifacts):
            raise _InvalidManifest("Manifest artifact paths must be unique.")
        return PublicationManifest(
            schema_version=schema_version,
            created_at=_required_string(decoded, "created_at"),
            source_episodes=_positive_int_tuple(decoded, "source_episodes"),
            topic_catalog=_nonempty_string_tuple(decoded, "topic_catalog"),
            total_chapters=_nonnegative_int(decoded, "total_chapters"),
            total_seconds=_nonnegative_int(decoded, "total_seconds"),
            artifacts=artifacts,
        )


def _required_int(value: dict[str, object], name: str) -> int:
    candidate = value.get(name)
    if isinstance(candidate, bool) or not isinstance(candidate, int):
        raise _InvalidManifest(f"Manifest {name} must be an integer.")
    return candidate


def _nonnegative_int(value: dict[str, object], name: str) -> int:
    candidate = _required_int(value, name)
    if candidate < 0:
        raise _InvalidManifest(f"Manifest {name} must be non-negative.")
    return candidate


def _required_string(value: dict[str, object], name: str) -> str:
    candidate = value.get(name)
    if not isinstance(candidate, str) or not candidate:
        raise _InvalidManifest(f"Manifest {name} must be a non-empty string.")
    return candidate


def _positive_int_tuple(value: dict[str, object], name: str) -> tuple[int, ...]:
    candidate = value.get(name)
    if not isinstance(candidate, list) or any(
        isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in candidate
    ):
        raise _InvalidManifest(f"Manifest {name} must be an array of positive integers.")
    if len(set(candidate)) != len(candidate):
        raise _InvalidManifest(f"Manifest {name} must not contain duplicates.")
    if candidate != sorted(candidate):
        raise _InvalidManifest(f"Manifest {name} must be sorted.")
    return tuple(candidate)


def _nonempty_string_tuple(value: dict[str, object], name: str) -> tuple[str, ...]:
    candidate = value.get(name)
    if not isinstance(candidate, list) or any(
        not isinstance(item, str) or not item for item in candidate
    ):
        raise _InvalidManifest(f"Manifest {name} must be an array of non-empty strings.")
    if len(set(candidate)) != len(candidate):
        raise _InvalidManifest(f"Manifest {name} must not contain duplicates.")
    if candidate != sorted(candidate):
        raise _InvalidManifest(f"Manifest {name} must be sorted.")
    return tuple(candidate)


def _decode_artifact(value: object) -> PublicationArtifact:
    if not isinstance(value, dict) or set(value) != {"path", "size_bytes", "sha256"}:
        raise _InvalidManifest("Each Manifest artifact must have path, size_bytes, and sha256.")
    path = value.get("path")
    size_bytes = value.get("size_bytes")
    sha256 = value.get("sha256")
    if not isinstance(path, str) or not _is_normalized_artifact_path(path):
        raise _InvalidManifest("Manifest artifact path is not a normalized relative POSIX path.")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
        raise _InvalidManifest("Manifest artifact size_bytes must be a non-negative integer.")
    if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise _InvalidManifest("Manifest artifact sha256 must be a lowercase SHA-256 digest.")
    return PublicationArtifact(path=path, size_bytes=size_bytes, sha256=sha256)


def _is_normalized_artifact_path(path: str) -> bool:
    candidate = Path(path)
    return (
        path != MANIFEST_FILENAME
        and "\\" not in path
        and not candidate.is_absolute()
        and bool(candidate.parts)
        and path == Path(*candidate.parts).as_posix()
        and all(part not in {"", ".", ".."} for part in candidate.parts)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for block in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    for directory, _, names in os.walk(root, followlinks=False):
        current = Path(directory)
        for name in names:
            path = current / name
            relative = path.relative_to(root).as_posix()
            if relative != MANIFEST_FILENAME and path.is_file() and not path.is_symlink():
                paths.add(relative)
    return paths


def _symlink_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    for directory, directories, names in os.walk(root, followlinks=False):
        current = Path(directory)
        for name in directories[:]:
            path = current / name
            if path.is_symlink():
                paths.add(path.relative_to(root).as_posix())
                directories.remove(name)
        for name in names:
            path = current / name
            if path.is_symlink():
                paths.add(path.relative_to(root).as_posix())
    return paths


def _required_paths(manifest: PublicationManifest) -> set[str]:
    paths = {"README.md", "_index.md", "topics/README.md"}
    for number in manifest.source_episodes:
        stem = f"episodes/EP{number:04d}"
        paths.update((f"{stem}.md", f"{stem}.full.md"))
    paths.update(f"topics/{slug}.md" for slug in manifest.topic_catalog)
    return paths


def _broken_markdown_links(root: Path, paths: set[str]) -> list[PublicationDefect]:
    defects: list[PublicationDefect] = []
    root_resolved = root.resolve()
    for relative_path in sorted(path for path in paths if path.endswith(".md")):
        source = root / relative_path
        for target in _markdown_targets(source.read_text(encoding="utf-8")):
            resolved = (source.parent / target).resolve()
            try:
                resolved.relative_to(root_resolved)
            except ValueError:
                defects.append(
                    PublicationDefect(
                        "unsafe_path", "Markdown link resolves outside publication root.", relative_path
                    )
                )
            else:
                if not resolved.exists():
                    defects.append(
                        PublicationDefect(
                            "broken_link", f"Markdown link target is missing: {target}", relative_path
                        )
                    )
    return defects


def _markdown_targets(text: str) -> tuple[str, ...]:
    targets: list[str] = []
    for match in _MARKDOWN_LINK.finditer(text):
        target = match.group(1).split(maxsplit=1)[0]
        if target and not target.startswith(("#", "http://", "https://", "mailto:")):
            targets.append(target.split("#", maxsplit=1)[0])
    return tuple(target for target in targets if target)
