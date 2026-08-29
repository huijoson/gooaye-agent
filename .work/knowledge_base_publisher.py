"""Read-only verification result types for Knowledge Base Publications."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Sequence
from urllib.parse import unquote, urlsplit

from domain import TopicDefinition
from episode_synthesizer import EpisodeNoteSynthesizer
from markdown_renderer import MarkdownRenderer
from topic_catalog import DEFAULT_TOPICS
from topic_synthesizer import TopicGuideRenderer, TopicGuideSynthesizer


MANIFEST_FILENAME = "publication-manifest.json"
PUBLICATION_SCHEMA_VERSION = 1
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


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
class PublicationRequest:
    destination: Path
    resolver: object | None = None
    takeaway_resolver: object | None = None
    max_workers: int = 1
    keep_failed_staging: bool = False


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
    """Own complete Knowledge Base Publication rendering and verification."""

    def __init__(
        self,
        episode_synthesizer: EpisodeNoteSynthesizer | None = None,
        topic_synthesizer: TopicGuideSynthesizer | None = None,
        markdown_renderer: MarkdownRenderer | None = None,
        topic_renderer: TopicGuideRenderer | None = None,
        topic_catalog: Sequence[TopicDefinition] = DEFAULT_TOPICS,
    ) -> None:
        self.episode_synthesizer = episode_synthesizer or EpisodeNoteSynthesizer()
        self.topic_synthesizer = topic_synthesizer or TopicGuideSynthesizer()
        self.markdown_renderer = markdown_renderer or MarkdownRenderer()
        self.topic_renderer = topic_renderer or TopicGuideRenderer()
        self.topic_catalog = tuple(topic_catalog)

    def publish(self, request: PublicationRequest) -> PublicationManifest:
        """Build, verify, and install one complete publication tree."""
        destination = self._validated_destination(request)
        catalog_slugs = self._validated_catalog_slugs()
        summary = self.episode_synthesizer.synthesize_notes(
            resolver=request.resolver,
            takeaway_resolver=request.takeaway_resolver,
            max_workers=request.max_workers,
        )
        guides = self.topic_synthesizer.synthesize_all_topics(
            summary.notes,
            self.topic_catalog,
        )
        self._validated_guide_slugs(guides, catalog_slugs)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{destination.name}.staging-",
                dir=destination.parent,
            )
        )
        installed = False
        try:
            self._render_tree(staging, summary, guides)
            manifest = self._build_manifest(staging, summary)
            self._write_manifest(staging, manifest)
            verification = self.verify(staging)
            if not verification.is_valid:
                details = "; ".join(
                    f"{defect.category}: {defect.path or defect.message}"
                    for defect in verification.defects
                )
                raise ValueError(f"Staged publication failed verification: {details}")
            self._install(staging, destination)
            installed = True
            return manifest
        finally:
            if not installed and not request.keep_failed_staging and staging.exists():
                shutil.rmtree(staging)

    def _validated_destination(self, request: PublicationRequest) -> Path:
        if isinstance(request.max_workers, bool) or request.max_workers < 1:
            raise ValueError("Publication max_workers must be a positive integer.")
        destination = Path(request.destination)
        if destination.is_symlink():
            raise ValueError("Publication destination must not be a symlink.")
        resolved = destination.resolve(strict=False)
        dangerous = {
            Path(resolved.anchor),
            Path.home().resolve(),
            WORKSPACE_ROOT,
        }
        if resolved in dangerous:
            raise ValueError("Publication destination is a protected directory.")
        if destination.exists() and not destination.is_dir():
            raise ValueError("Publication destination must be a directory.")
        if destination.exists() and any(destination.iterdir()):
            report = self.verify(destination)
            if report.mode is not PublicationMode.MANAGED or not report.is_valid:
                raise ValueError("Non-empty publication destination is not a valid managed tree.")
        return destination

    def _validated_catalog_slugs(self) -> tuple[str, ...]:
        slugs = tuple(topic.slug for topic in self.topic_catalog)
        for slug in slugs:
            self._validate_topic_slug(slug, source="Topic catalog")
        if len(set(slugs)) != len(slugs):
            raise ValueError("Topic catalog slugs must be unique.")
        return slugs

    @staticmethod
    def _validated_guide_slugs(guides, catalog_slugs: tuple[str, ...]) -> tuple[str, ...]:
        slugs = tuple(guide.slug for guide in guides)
        for slug in slugs:
            KnowledgeBasePublisher._validate_topic_slug(slug, source="Topic Guide")
        if sorted(slugs) != sorted(catalog_slugs):
            raise ValueError("Topic Guide slugs must exactly match the Topic catalog.")
        return slugs

    @staticmethod
    def _validate_topic_slug(slug: object, *, source: str) -> None:
        if (
            not isinstance(slug, str)
            or not slug
            or slug in {".", ".."}
            or "\0" in slug
            or PurePosixPath(slug).parts != (slug,)
            or PureWindowsPath(slug).parts != (slug,)
            or bool(PureWindowsPath(slug).drive)
        ):
            raise ValueError(
                f"{source} slug must be a single normalized filename component."
            )

    def _render_tree(self, stage, summary, guides) -> None:
        episodes_dir = stage / "episodes"
        topics_dir = stage / "topics"
        episodes_dir.mkdir()
        topics_dir.mkdir()
        for note in summary.notes:
            stem = f"EP{note.metadata.number:04d}"
            (episodes_dir / f"{stem}.md").write_text(
                self.markdown_renderer.render_episode(note, mode="slim"),
                encoding="utf-8",
            )
            (episodes_dir / f"{stem}.full.md").write_text(
                self.markdown_renderer.render_episode(note, mode="full"),
                encoding="utf-8",
            )
        (stage / "README.md").write_text(
            self.markdown_renderer.render_readme(summary.notes, summary),
            encoding="utf-8",
        )
        (stage / "_index.md").write_text(
            self.markdown_renderer.render_index(
                summary.notes,
                summary,
                topics=self.topic_catalog,
            ),
            encoding="utf-8",
        )
        for guide in guides:
            (topics_dir / f"{guide.slug}.md").write_text(
                self.topic_renderer.render(guide),
                encoding="utf-8",
            )
        (topics_dir / "README.md").write_text(
            self.topic_renderer.render_topics_readme(guides),
            encoding="utf-8",
        )

    def _build_manifest(self, stage, summary) -> PublicationManifest:
        artifacts = tuple(
            PublicationArtifact(
                path=path.relative_to(stage).as_posix(),
                size_bytes=path.stat().st_size,
                sha256=_sha256(path),
            )
            for path in sorted(stage.rglob("*"))
            if path.is_file()
        )
        return PublicationManifest(
            schema_version=PUBLICATION_SCHEMA_VERSION,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source_episodes=tuple(sorted(note.metadata.number for note in summary.notes)),
            topic_catalog=tuple(sorted(topic.slug for topic in self.topic_catalog)),
            total_chapters=summary.total_chapters,
            total_seconds=summary.total_seconds,
            artifacts=artifacts,
        )

    @staticmethod
    def _write_manifest(stage: Path, manifest: PublicationManifest) -> None:
        (stage / MANIFEST_FILENAME).write_text(
            json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _install(stage: Path, destination: Path) -> None:
        backup: Path | None = None
        if destination.exists() and any(destination.iterdir()):
            backup = Path(
                tempfile.mkdtemp(
                    prefix=f".{destination.name}.backup-",
                    dir=destination.parent,
                )
            )
            backup.rmdir()
            os.replace(destination, backup)
        elif destination.exists():
            destination.rmdir()
        os.replace(stage, destination)
        if backup is not None:
            shutil.rmtree(backup)

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
        try:
            entries = _all_entries(root)
        except OSError as exc:
            return PublicationVerification(
                PublicationMode.UNKNOWN,
                (PublicationDefect("unreadable", f"Publication tree cannot be read: {exc}", str(root)),),
            )
        manifest_kind = entries.get(MANIFEST_FILENAME)
        if manifest_kind is None:
            if not entries:
                return PublicationVerification(PublicationMode.UNKNOWN, ())
            return PublicationVerification(
                PublicationMode.UNKNOWN,
                (
                    PublicationDefect(
                        "ownership", "Non-empty root has no publication Manifest.", str(root)
                    ),
                ),
            )
        if manifest_kind != "file":
            return PublicationVerification(
                PublicationMode.MANAGED,
                (PublicationDefect("unsafe_path", "Manifest must be a regular file.", MANIFEST_FILENAME),),
            )
        try:
            manifest = self._read_manifest(manifest_path)
        except _InvalidManifest as exc:
            return PublicationVerification(
                PublicationMode.MANAGED,
                (PublicationDefect("manifest", str(exc), MANIFEST_FILENAME),),
            )
        defects: list[PublicationDefect] = []
        actual_paths = {
            path for path, kind in entries.items() if kind == "file" and path != MANIFEST_FILENAME
        }
        manifest_paths = {artifact.path for artifact in manifest.artifacts}
        required_paths = _required_paths(manifest)
        allowed_directories = {"episodes", "topics"}
        for path, kind in sorted(entries.items()):
            if path == MANIFEST_FILENAME:
                continue
            if kind == "symlink":
                defects.append(PublicationDefect("unsafe_path", "Publication must not contain symlinks.", path))
            elif (kind == "file" and path in required_paths) or (
                kind == "directory" and path in allowed_directories
            ):
                continue
            else:
                defects.append(PublicationDefect("stale", "Entry is outside the public publication tree.", path))
        for path in sorted(manifest_paths - required_paths):
            defects.append(PublicationDefect("stale", "Manifest artifact is outside the public tree.", path))
        for path in sorted(actual_paths - manifest_paths):
            defects.append(PublicationDefect("stale", "File is not recorded by the Manifest.", path))
        for path in sorted(required_paths - actual_paths.intersection(manifest_paths)):
            defects.append(PublicationDefect("missing", "Required publication artifact is missing.", path))
        for artifact in manifest.artifacts:
            artifact_path = Path(root) / artifact.path
            try:
                if _has_symlink_ancestor(root, artifact.path):
                    continue
                metadata = artifact_path.stat()
                if not stat.S_ISREG(metadata.st_mode):
                    defects.append(PublicationDefect("missing", "Manifest artifact is missing.", artifact.path))
                    continue
                if metadata.st_size != artifact.size_bytes:
                    defects.append(PublicationDefect("size", "Artifact byte size differs from Manifest.", artifact.path))
                if _sha256(artifact_path) != artifact.sha256:
                    defects.append(
                        PublicationDefect("digest", "Artifact SHA-256 differs from Manifest.", artifact.path)
                    )
            except OSError as exc:
                defects.append(PublicationDefect("unreadable", f"Artifact cannot be read: {exc}", artifact.path))
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


def _has_symlink_ancestor(root: Path, relative_path: str) -> bool:
    path = root
    for part in Path(relative_path).parts:
        path /= part
        if path.is_symlink():
            return True
    return False


def _all_entries(root: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as children:
            for child in children:
                path = Path(child.path)
                relative = path.relative_to(root).as_posix()
                if child.is_symlink():
                    entries[relative] = "symlink"
                elif child.is_dir(follow_symlinks=False):
                    entries[relative] = "directory"
                    pending.append(path)
                elif child.is_file(follow_symlinks=False):
                    entries[relative] = "file"
                else:
                    entries[relative] = "special"
    return entries


def _required_paths(manifest: PublicationManifest) -> set[str]:
    paths = {"README.md", "_index.md", "topics/README.md"}
    for number in manifest.source_episodes:
        stem = f"episodes/EP{number:04d}"
        paths.update((f"{stem}.md", f"{stem}.full.md"))
    paths.update(f"topics/{slug}.md" for slug in manifest.topic_catalog)
    return paths


def _broken_markdown_links(root: Path, paths: set[str]) -> list[PublicationDefect]:
    defects: list[PublicationDefect] = []
    try:
        root_resolved = root.resolve()
    except OSError as exc:
        return [PublicationDefect("unreadable", f"Publication root cannot be resolved: {exc}", str(root))]
    for relative_path in sorted(path for path in paths if path.endswith(".md")):
        source = root / relative_path
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            defects.append(PublicationDefect("unreadable", f"Markdown cannot be read: {exc}", relative_path))
            continue
        try:
            targets = _markdown_targets(text)
        except ValueError as exc:
            defects.append(PublicationDefect("malformed_link", f"Markdown link is malformed: {exc}", relative_path))
            continue
        for target in targets:
            try:
                resolved = (source.parent / target).resolve()
            except OSError as exc:
                defects.append(PublicationDefect("unreadable", f"Link target cannot be read: {exc}", relative_path))
                continue
            try:
                resolved.relative_to(root_resolved)
            except ValueError:
                defects.append(
                    PublicationDefect(
                        "unsafe_path", "Markdown link resolves outside publication root.", relative_path
                    )
                )
            else:
                try:
                    exists = resolved.exists()
                except OSError as exc:
                    defects.append(
                        PublicationDefect("unreadable", f"Link target cannot be read: {exc}", relative_path)
                    )
                    continue
                if not exists:
                    defects.append(
                        PublicationDefect(
                            "broken_link", f"Markdown link target is missing: {target}", relative_path
                        )
                    )
    return defects


def _markdown_targets(text: str) -> tuple[str, ...]:
    definitions = _reference_definitions(text)
    destinations: list[str] = []
    references: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "[" or _is_escaped(text, index):
            index += 1
            continue
        label, after_label = _bracketed(text, index)
        if label is None:
            index += 1
            continue
        if after_label < len(text) and text[after_label] == "(":
            destination, end = _inline_destination(text, after_label)
            if destination is not None:
                destinations.append(destination)
                index = end
                continue
        elif after_label < len(text) and text[after_label] == "[":
            reference, end = _bracketed(text, after_label)
            if reference is not None:
                references.append(_reference_key(reference or label))
                index = end
                continue
        elif after_label >= len(text) or text[after_label] != ":":
            references.append(_reference_key(label))
        index = after_label

    destinations.extend(
        definitions[reference]
        for reference in references
        if reference in definitions
    )
    return tuple(
        target
        for destination in destinations
        if (target := _local_destination(destination)) is not None
    )


def _reference_definitions(text: str) -> dict[str, str]:
    definitions: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r" {0,3}\[([^]]+)]:\s*(.*)$", line)
        if match is None:
            continue
        destination = _definition_destination(match.group(2))
        if destination is not None:
            definitions[_reference_key(match.group(1))] = destination
    return definitions


def _definition_destination(text: str) -> str | None:
    start = len(text) - len(text.lstrip())
    if start == len(text):
        return None
    if text[start] == "<":
        destination, _ = _angle_destination(text, start)
        return destination
    end = start
    depth = 0
    while end < len(text):
        character = text[end]
        if character == "\\" and end + 1 < len(text):
            end += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        elif character.isspace() and depth == 0:
            break
        end += 1
    return text[start:end] or None


def _bracketed(text: str, start: int) -> tuple[str | None, int]:
    index = start + 1
    while index < len(text):
        if text[index] == "\\" and index + 1 < len(text):
            index += 2
            continue
        if text[index] == "]":
            return text[start + 1:index], index + 1
        index += 1
    return None, start + 1


def _inline_destination(text: str, opening: int) -> tuple[str | None, int]:
    index = opening + 1
    while index < len(text) and text[index].isspace():
        index += 1
    if index < len(text) and text[index] == "<":
        return _angle_destination(text, index)

    start = index
    depth = 0
    while index < len(text):
        character = text[index]
        if character == "\\" and index + 1 < len(text):
            index += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                return text[start:index], index + 1
            depth -= 1
        elif character.isspace() and depth == 0:
            return text[start:index], index
        index += 1
    return None, opening + 1


def _angle_destination(text: str, opening: int) -> tuple[str | None, int]:
    index = opening + 1
    while index < len(text):
        if text[index] == "\\" and index + 1 < len(text):
            index += 2
            continue
        if text[index] == ">":
            return text[opening + 1:index], index + 1
        index += 1
    return None, opening + 1


def _reference_key(label: str) -> str:
    return " ".join(_unescape_markdown(label).split()).casefold()


def _local_destination(destination: str) -> str | None:
    path = unquote(_unescape_markdown(_without_fragment(destination)))
    if not path:
        return None
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc:
        return None
    return parsed.path or None


def _without_fragment(text: str) -> str:
    index = 0
    while index < len(text):
        if text[index] == "\\" and index + 1 < len(text):
            index += 2
            continue
        if text[index] == "#":
            return text[:index]
        index += 1
    return text


def _unescape_markdown(text: str) -> str:
    characters: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == "\\" and index + 1 < len(text):
            index += 1
        characters.append(text[index])
        index += 1
    return "".join(characters)


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1
