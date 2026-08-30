"""Read-only verification result types for Knowledge Base Publications."""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import socket
import stat
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Sequence
from urllib.parse import unquote, urlsplit

from domain import TopicDefinition
from episode_synthesizer import EpisodeNoteSynthesizer
from markdown_renderer import MarkdownRenderer
from topic_catalog import DEFAULT_TOPICS
from topic_synthesizer import TopicGuideRenderer, TopicGuideSynthesizer, TopicQualityAuditor


MANIFEST_FILENAME = "publication-manifest.json"
PUBLICATION_SCHEMA_VERSION = 1
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
LOGGER = logging.getLogger(__name__)


def _get_identity(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
        return (st.st_dev, st.st_ino)
    except OSError:
        return None



class PublicationMode(str, Enum):
    MANAGED = "managed"
    LEGACY = "legacy"
    UNKNOWN = "unknown"


class PublicationPhase(str, Enum):
    """The publication boundary at which an operation failed."""

    OWNERSHIP = "ownership"
    LOCK = "lock"
    SYNTHESIS = "synthesis"
    RENDER = "render"
    MANIFEST = "manifest"
    VERIFY = "verify"
    COMMIT = "commit"


class PublicationError(RuntimeError):
    """A publication failure with its phase and safe diagnostic context."""

    def __init__(
        self,
        phase: PublicationPhase,
        message: str,
        *,
        defects: Sequence[object] = (),
        staging_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.defects = tuple(defects)
        self.staging_path = staging_path


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


class _InstalledVerificationFailure(ValueError):
    def __init__(self, defects: Sequence[PublicationDefect]) -> None:
        self.defects = tuple(defects)
        details = "; ".join(
            f"{defect.category}: {defect.path or defect.message}" for defect in self.defects
        )
        super().__init__(f"Installed publication failed verification: {details}")


class _PublicationLock:
    """A sibling lock held by a descriptor, never removed by a pathname race."""

    _SCHEMA_VERSION = 1
    _STALE_AFTER = timedelta(hours=24)

    def __init__(self, destination: Path) -> None:
        self.destination = destination.resolve(strict=False)
        self.path = destination.parent / f".{destination.name}.publication.lock"
        self._identity: tuple[int, int] | None = None
        self._descriptor: int | None = None

    def acquire(self) -> None:
        try:
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            self._acquire_existing()
            return
        try:
            self._hold(descriptor)
            self._write_state(active=True)
        except BaseException:
            self._close_descriptor(descriptor)
            raise

    def release(self) -> None:
        if self._descriptor is None:
            return
        try:
            self._write_state(active=False)
        finally:
            try:
                self._retire_path()
            finally:
                self._close()

    def _acquire_existing(self) -> None:
        descriptor = os.open(self.path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            self._hold(descriptor)
            payload = self._read_payload()
            if not self._can_reclaim(payload) or not self._path_matches_identity():
                raise FileExistsError(self.path)
            self._write_state(active=True)
        except BaseException:
            self._close_descriptor(descriptor)
            raise

    def _hold(self, descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise FileExistsError(self.path)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise FileExistsError(self.path) from exc
        self._descriptor = descriptor
        self._identity = (metadata.st_dev, metadata.st_ino)

    def _close(self) -> None:
        if self._descriptor is None:
            return
        descriptor = self._descriptor
        self._descriptor = None
        self._identity = None
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def _close_descriptor(self, descriptor: int) -> None:
        if self._descriptor == descriptor:
            self._close()
        else:
            os.close(descriptor)

    def _read_payload(self) -> dict[str, object] | None:
        if self._descriptor is None:
            return None
        size = os.fstat(self._descriptor).st_size
        if size < 1 or size > 16_384:
            return None
        os.lseek(self._descriptor, 0, os.SEEK_SET)
        try:
            payload = json.loads(os.read(self._descriptor, size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _can_reclaim(self, payload: dict[str, object] | None) -> bool:
        if payload is None:
            return False
        expected = {"schema_version", "destination", "pid", "hostname", "created_at"}
        fields = set(payload)
        if fields != expected and fields != expected | {"active"}:
            return False
        if payload["schema_version"] != self._SCHEMA_VERSION:
            return False
        if not isinstance(payload["pid"], int) or isinstance(payload["pid"], bool):
            return False
        if payload["pid"] < 1 or payload["hostname"] != socket.gethostname():
            return False
        if payload["destination"] != str(self.destination) or not isinstance(payload["created_at"], str):
            return False
        if fields == expected | {"active"}:
            if not isinstance(payload["active"], bool):
                return False
            if not payload["active"]:
                return True
        try:
            created_at = datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))
            if created_at.tzinfo is None or datetime.now(timezone.utc) - created_at < self._STALE_AFTER:
                return False
            os.kill(payload["pid"], 0)
        except ProcessLookupError:
            return True
        except (PermissionError, OSError, OverflowError, ValueError, TypeError):
            return False
        return False

    def _path_matches_identity(self) -> bool:
        if self._identity is None:
            return False
        try:
            metadata = self.path.lstat()
        except OSError:
            return False
        return (metadata.st_dev, metadata.st_ino) == self._identity

    def _retire_path(self) -> None:
        """Remove our lock without ever unlinking a replacement pathname."""
        identity = self._identity
        if identity is None:
            return
        descriptor, retired_name = tempfile.mkstemp(
            prefix=f".{self.destination.name}.retired-",
            dir=self.path.parent,
        )
        os.close(descriptor)
        retired = Path(retired_name)
        moved = False
        try:
            os.replace(self.path, retired)
            moved = True
            try:
                metadata = retired.lstat()
            except FileNotFoundError:
                self._close()
                metadata = retired.lstat()
            if (metadata.st_dev, metadata.st_ino) == identity:
                retired.unlink()
                return
            try:
                os.link(retired, self.path, follow_symlinks=False)
            except FileExistsError as exc:
                raise OSError(
                    f"Publication lock was replaced; preserved displaced lock at {retired}."
                ) from exc
            retired.unlink()
        finally:
            if not moved:
                try:
                    retired.unlink()
                except FileNotFoundError:
                    pass

    def _write_state(self, *, active: bool) -> None:
        if self._descriptor is None:
            raise OSError("Publication lock is not held.")
        payload = {
            "schema_version": self._SCHEMA_VERSION,
            "destination": str(self.destination),
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "active": active,
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        os.ftruncate(self._descriptor, 0)
        os.lseek(self._descriptor, 0, os.SEEK_SET)
        view = memoryview(encoded)
        while view:
            view = view[os.write(self._descriptor, view):]


def _copy_tree(src: Path, dst: Path) -> None:
    """Copy directory tree safely without failing on filesystem metadata permissions."""
    dst.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel_root = Path(root).relative_to(src)
        target_dir = dst / rel_root
        for d in dirs:
            (target_dir / d).mkdir(parents=True, exist_ok=True)
        for f in files:
            shutil.copyfile(Path(root) / f, target_dir / f)


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
        try:
            destination = self._validate_destination_path(request)
        except ValueError as exc:
            raise PublicationError(PublicationPhase.OWNERSHIP, str(exc)) from exc
        catalog_slugs = self._validated_catalog_slugs()
        destination.parent.mkdir(parents=True, exist_ok=True)
        lock = _PublicationLock(destination)
        try:
            lock.acquire()
        except OSError as exc:
            raise PublicationError(PublicationPhase.LOCK, f"Publication destination is locked: {exc}") from exc
        installed = False
        try:
            try:
                self._validate_destination_ownership(destination)
            except ValueError as exc:
                raise PublicationError(PublicationPhase.OWNERSHIP, str(exc)) from exc
            try:
                summary = self.episode_synthesizer.synthesize_notes(
                    resolver=request.resolver,
                    takeaway_resolver=request.takeaway_resolver,
                    max_workers=request.max_workers,
                )
                guides = self.topic_synthesizer.synthesize_all_topics(
                    summary.notes,
                    self.topic_catalog,
                )
            except Exception as exc:
                raise PublicationError(PublicationPhase.SYNTHESIS, str(exc)) from exc
            self._validated_guide_slugs(guides, catalog_slugs)
            staging = Path(
                tempfile.mkdtemp(
                    prefix=f".{destination.name}.staging-",
                    dir=destination.parent,
                )
            )
            try:
                try:
                    self._render_tree(staging, summary, guides)
                except Exception as exc:
                    raise PublicationError(PublicationPhase.RENDER, str(exc)) from exc
                try:
                    manifest = self._build_manifest(staging, summary)
                    self._write_manifest(staging, manifest)
                except Exception as exc:
                    raise PublicationError(PublicationPhase.MANIFEST, str(exc)) from exc
                try:
                    verification = self.verify(staging)
                    if not verification.is_valid:
                        details = "; ".join(
                            f"{defect.category}: {defect.path or defect.message}"
                            for defect in verification.defects
                        )
                        raise PublicationError(
                            PublicationPhase.VERIFY,
                            f"Staged publication failed verification: {details}",
                            defects=verification.defects,
                        )
                except PublicationError:
                    raise
                except Exception as exc:
                    raise PublicationError(PublicationPhase.VERIFY, str(exc)) from exc
                self._install(staging, destination, request)
                installed = True
                return manifest
            except PublicationError as error:
                if request.keep_failed_staging:
                    error.staging_path = staging
                raise
            finally:
                if not installed and not request.keep_failed_staging:
                    try:
                        shutil.rmtree(staging)
                    except OSError:
                        pass
        finally:
            primary_error = sys.exception()
            try:
                lock.release()
            except OSError as cleanup_error:
                if primary_error is None:
                    if installed:
                        LOGGER.warning(
                            "Publication committed but lock cleanup failed: %s; "
                            "residual lock path: %s",
                            cleanup_error,
                            lock.path,
                        )
                    else:
                        raise PublicationError(
                            PublicationPhase.LOCK,
                            f"Publication lock cleanup failed: {cleanup_error}",
                        ) from cleanup_error

    def _validate_destination_path(self, request: PublicationRequest) -> Path:
        if isinstance(request.max_workers, bool) or request.max_workers < 1:
            raise ValueError("Publication max_workers must be a positive integer.")
        destination = Path(request.destination)
        if destination.is_symlink():
            raise ValueError("Publication destination must not be a symlink.")
        resolved = destination.resolve(strict=False)
        dangerous = {
            Path(resolved.anchor),
            Path.home().resolve(),
            WORKSPACE_ROOT.resolve(),
        }
        if resolved in dangerous:
            raise ValueError("Publication destination is a protected directory.")
        formal_root = (WORKSPACE_ROOT / "gooaye-youtube-notes").resolve(strict=False)
        try:
            rel = resolved.relative_to(formal_root)
            if rel.parts:
                raise ValueError("Publication destination must not be inside the formal publication root.")
        except ValueError as exc:
            if "must not be inside" in str(exc):
                raise
        for parent in resolved.parents:
            if parent in dangerous or parent == Path(resolved.anchor):
                break
            if parent.exists() and parent.is_dir():
                if (parent / MANIFEST_FILENAME).exists() or ((parent / "episodes").is_dir() and (parent / "topics").is_dir()):
                    report = self.verify(parent)
                    if report.mode in {PublicationMode.MANAGED, PublicationMode.LEGACY} and report.is_valid:
                        raise ValueError(f"Publication destination must not be inside an existing publication: {parent}")
        if destination.exists() and not destination.is_dir():
            raise ValueError("Publication destination must be a directory.")
        return destination

    def _validate_destination_ownership(self, destination: Path) -> None:
        if destination.exists() and any(destination.iterdir()):
            report = self.verify(destination)
            if report.mode not in {PublicationMode.MANAGED, PublicationMode.LEGACY} or not report.is_valid:
                raise ValueError("Non-empty publication destination is not a valid owned tree.")

    def _validated_destination(self, request: PublicationRequest) -> Path:
        destination = self._validate_destination_path(request)
        self._validate_destination_ownership(destination)
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
            self.topic_renderer.render_topics_readme(guides, summary.notes),
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

    def _install(
        self,
        stage: Path,
        destination: Path,
        request: PublicationRequest,
    ) -> None:
        try:
            self._validate_destination_path(request)
            self._validate_destination_ownership(destination)
        except ValueError as exc:
            raise PublicationError(PublicationPhase.OWNERSHIP, str(exc)) from exc
        backup: Path | None = None
        moved_existing = False
        try:
            if destination.exists():
                before_identity = _get_identity(destination)
                backup = Path(
                    tempfile.mkdtemp(
                        prefix=f".{destination.name}.backup-",
                        dir=destination.parent,
                    )
                )
                backup.rmdir()
                os.replace(destination, backup)
                moved_existing = True
                after_identity = _get_identity(backup)
                if before_identity is not None and after_identity != before_identity:
                    try:
                        os.replace(backup, destination)
                    except Exception:
                        pass
                    raise PublicationError(
                        PublicationPhase.OWNERSHIP,
                        "Destination identity changed before commit.",
                    )
                backup_verif = self.verify(backup)
                if (
                    backup_verif.mode not in {PublicationMode.MANAGED, PublicationMode.LEGACY}
                    or not backup_verif.is_valid
                ):
                    try:
                        os.replace(backup, destination)
                    except Exception:
                        pass
                    raise PublicationError(
                        PublicationPhase.OWNERSHIP,
                        "Displaced destination is not an owned publication.",
                    )
            elif destination.exists():
                raise PublicationError(
                    PublicationPhase.OWNERSHIP,
                    "Destination appeared before commit.",
                )
            os.replace(stage, destination)
            verification = self.verify(destination)
            if not verification.is_valid:
                raise _InstalledVerificationFailure(verification.defects)
        except Exception as primary_error:
            rollback_error: Exception | None = None
            if moved_existing and backup is not None:
                try:
                    if destination.exists():
                        os.replace(destination, stage)
                    os.replace(backup, destination)
                except Exception as exc:
                    rollback_error = exc
            if isinstance(primary_error, PublicationError):
                raise
            message = f"Publication commit failed: {primary_error}"
            if rollback_error is not None:
                backup_path = str(backup) if backup is not None else "unknown"
                message += f"; rollback failed: {rollback_error}; recoverable backup: {backup_path}"
            defects = (
                primary_error.defects
                if isinstance(primary_error, _InstalledVerificationFailure)
                else ()
            )
            raise PublicationError(
                PublicationPhase.COMMIT,
                message,
                defects=defects,
            ) from primary_error
        if backup is not None:
            recovery = Path(
                tempfile.mkdtemp(
                    prefix=f".{destination.name}.recovery-",
                    dir=destination.parent,
                )
            )
            recovery.rmdir()
            try:
                _copy_tree(backup, recovery)
            except OSError as exc:
                rollback_error: Exception | None = None
                try:
                    os.replace(destination, stage)
                    os.replace(backup, destination)
                except Exception as rollback_exc:
                    rollback_error = rollback_exc
                message = f"Publication recovery copy failed: {exc}"
                if rollback_error is not None:
                    message += f"; rollback failed: {rollback_error}; recoverable backup: {backup}"
                else:
                    message += "; previous publication was restored"
                raise PublicationError(PublicationPhase.COMMIT, message) from exc
            try:
                shutil.rmtree(backup)
            except OSError as exc:
                rollback_error: Exception | None = None
                try:
                    os.replace(destination, stage)
                    os.replace(recovery, destination)
                except Exception as rollback_exc:
                    rollback_error = rollback_exc
                message = f"Publication backup cleanup failed: {exc}"
                if rollback_error is not None:
                    message += f"; rollback failed: {rollback_error}; recoverable backup: {recovery}"
                else:
                    message += "; previous publication was restored"
                raise PublicationError(
                    PublicationPhase.COMMIT,
                    message,
                ) from exc
            try:
                shutil.rmtree(recovery)
            except OSError as exc:
                LOGGER.warning(
                    "Publication committed but recovery cleanup failed: %s; "
                    "residual recovery path: %s",
                    exc,
                    recovery,
                )

    def verify(self, root: Path) -> PublicationVerification:
        """Read a Manifest-managed or structurally complete legacy publication."""
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
            return self._verify_legacy(root, entries)
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
    def _verify_legacy(root: Path, entries: dict[str, str]) -> PublicationVerification:
        """Recognize only the fixed pre-Manifest publication layout without writing it."""
        required_roots = {"README.md", "_index.md", "episodes", "topics"}
        if not required_roots.issubset(entries):
            return PublicationVerification(
                PublicationMode.UNKNOWN,
                (
                    PublicationDefect(
                        "ownership",
                        "Non-empty root has neither a Manifest nor a complete legacy layout.",
                        str(root),
                    ),
                ),
            )

        defects: list[PublicationDefect] = []
        expected_topic_paths = {"topics/README.md"} | {
            f"topics/{topic.slug}.md" for topic in DEFAULT_TOPICS
        }
        allowed_roots = required_roots
        for path, kind in sorted(entries.items()):
            if path in {"episodes", "topics"}:
                if kind != "directory":
                    defects.append(PublicationDefect("missing", "Required legacy directory is missing.", path))
                continue
            if "/" not in path:
                if path not in allowed_roots:
                    defects.append(PublicationDefect("stale", "Entry is outside the legacy publication tree.", path))
                elif kind != "file":
                    defects.append(PublicationDefect("missing", "Required legacy file is missing.", path))
                continue
            if path.startswith("episodes/"):
                continue
            if path in expected_topic_paths:
                if kind != "file":
                    defects.append(PublicationDefect("missing", "Required Topic Guide is missing.", path))
            else:
                defects.append(PublicationDefect("stale", "Entry is outside the legacy publication tree.", path))

        for path in sorted(expected_topic_paths):
            if entries.get(path) != "file":
                defects.append(PublicationDefect("missing", "Required Topic Guide is missing.", path))

        slim_numbers: set[int] = set()
        full_numbers: set[int] = set()
        for path, kind in sorted(entries.items()):
            if not path.startswith("episodes/"):
                continue
            match = re.fullmatch(r"episodes/EP(\d{4})\.md", path)
            full_match = re.fullmatch(r"episodes/EP(\d{4})\.full\.md", path)
            if kind != "file" or (match is None and full_match is None):
                defects.append(PublicationDefect("stale", "Unexpected legacy episode entry.", path))
                continue
            if match is not None:
                slim_numbers.add(int(match.group(1)))
            else:
                full_numbers.add(int(full_match.group(1)))
        if not slim_numbers or not full_numbers:
            defects.append(PublicationDefect("missing", "Legacy episodes must include slim/full pairs.", "episodes"))
        for number in sorted(slim_numbers - full_numbers):
            defects.append(
                PublicationDefect("missing", "Legacy full Episode Note is missing.", f"episodes/EP{number:04d}.full.md")
            )
        for number in sorted(full_numbers - slim_numbers):
            defects.append(
                PublicationDefect("missing", "Legacy slim Episode Note is missing.", f"episodes/EP{number:04d}.md")
            )

        markdown_paths = {
            path for path, kind in entries.items() if kind == "file" and path.endswith(".md")
        }
        defects.extend(_broken_markdown_links(root, markdown_paths))
        if not defects:
            try:
                audit = TopicQualityAuditor().audit_all_topics(root / "topics", root / "episodes")
            except (OSError, UnicodeDecodeError) as exc:
                defects.append(
                    PublicationDefect(
                        "unreadable",
                        f"Topic Guides cannot be audited: {exc}",
                        "topics",
                    )
                )
            else:
                defects.extend(_topic_audit_defects(audit))
        return PublicationVerification(
            PublicationMode.LEGACY,
            tuple(defects),
            artifact_count=len(markdown_paths),
            episode_count=len(slim_numbers),
            topic_count=len(DEFAULT_TOPICS),
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


def _topic_audit_defects(audit: object) -> list[PublicationDefect]:
    if not isinstance(audit, dict):
        return [
            PublicationDefect(
                "grounding",
                "Topic Guide audit returned a malformed result.",
                "topics",
            )
        ]
    total_topics = audit.get("total_topics")
    defect_count = audit.get("defect_count")
    defects = audit.get("defects")
    publication_defects: list[PublicationDefect] = []
    if (
        isinstance(total_topics, bool)
        or not isinstance(total_topics, int)
        or total_topics != len(DEFAULT_TOPICS)
    ):
        publication_defects.append(
            PublicationDefect(
                "grounding",
                "Topic Guide audit returned an inconsistent total_topics value.",
                "topics",
            )
        )
    if isinstance(defect_count, bool) or not isinstance(defect_count, int):
        publication_defects.append(
            PublicationDefect(
                "grounding",
                "Topic Guide audit returned a malformed defect_count value.",
                "topics",
            )
        )
    if not isinstance(defects, list):
        publication_defects.append(
            PublicationDefect(
                "grounding",
                "Topic Guide audit returned malformed defects.",
                "topics",
            )
        )
        return publication_defects

    if isinstance(defect_count, int) and not isinstance(defect_count, bool) and defect_count != len(defects):
        publication_defects.append(
            PublicationDefect(
                "grounding",
                "Topic Guide audit defect_count does not match its defects.",
                "topics",
            )
        )
    for defect in defects:
        if not isinstance(defect, dict):
            publication_defects.append(
                PublicationDefect(
                    "grounding",
                    "Topic Guide audit returned a malformed defect.",
                    "topics",
                )
            )
            continue
        topic = defect.get("topic")
        message = defect.get("message")
        if not isinstance(topic, str) or not topic or not isinstance(message, str):
            publication_defects.append(
                PublicationDefect(
                    "grounding",
                    "Topic Guide audit returned a malformed defect.",
                    "topics",
                )
            )
            continue
        publication_defects.append(PublicationDefect("grounding", message, f"topics/{topic}"))
    return publication_defects


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
            closing = index
            while closing < len(text):
                if text[closing] == "\\" and closing + 1 < len(text):
                    closing += 2
                    continue
                if text[closing] == ")":
                    return text[start:index], closing + 1
                if text[closing] in "\r\n":
                    return None, opening + 1
                closing += 1
            return None, opening + 1
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
