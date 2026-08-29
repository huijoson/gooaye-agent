"""Real `/mnt/c` filesystem contract for transactional knowledge-base publication."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from knowledge_base_publisher import (
    KnowledgeBasePublisher,
    PublicationError,
    PublicationPhase,
    PublicationRequest,
    _PublicationLock,
)
from test_knowledge_base_publisher import make_fixture_publisher, no_sibling_publication_debris


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_mnt_c_publication_lock_rename_rollback_and_cleanup_contract(monkeypatch):
    work_dir = REPO_ROOT / ".work"
    temporary_root: Path

    with tempfile.TemporaryDirectory(
        prefix="knowledge-base-publication-contract-",
        dir=work_dir,
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        destination = temporary_root / "publication"

        publisher_a = make_fixture_publisher(episode_numbers=(1,), topic_slugs=("topic-a",))
        publisher_a.publish(PublicationRequest(destination))
        assert publisher_a.verify(destination).is_valid

        held_lock = _PublicationLock(destination)
        held_lock.acquire()
        try:
            with pytest.raises(PublicationError) as locked:
                make_fixture_publisher().publish(PublicationRequest(destination))
        finally:
            held_lock.release()
        assert locked.value.phase is PublicationPhase.LOCK

        publisher_b = make_fixture_publisher(
            episode_numbers=(1, 2),
            topic_slugs=("topic-b",),
        )
        publisher_b.publish(PublicationRequest(destination))
        version_b = publisher_b.verify(destination)
        assert version_b.is_valid
        assert version_b.episode_count == 2

        replace = os.replace

        def fail_second_rename(source, target):
            if Path(source).name.startswith(".publication.staging-"):
                raise OSError("contract second rename failure")
            return replace(source, target)

        monkeypatch.setattr(os, "replace", fail_second_rename)
        with pytest.raises(PublicationError) as failed:
            make_fixture_publisher(
                episode_numbers=(1, 2, 3), topic_slugs=("topic-c",)
            ).publish(PublicationRequest(destination))

        assert failed.value.phase is PublicationPhase.COMMIT
        restored = KnowledgeBasePublisher().verify(destination)
        assert restored.is_valid
        assert restored.episode_count == 2
        assert no_sibling_publication_debris(destination)

    assert not temporary_root.exists()
