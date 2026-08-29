# Transactional Knowledge Base Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `publish` the only operation that can replace the formal Gooaye knowledge-base tree, with full-corpus synthesis, Manifest verification, fail-fast locking, same-filesystem staging, and rollback.

**Architecture:** `KnowledgeBasePublisher` is the deep lifecycle owner. It consumes one in-memory `SynthesisSummary`, derives Topic Guides from the same `EpisodeNote` objects, renders one complete sibling staging tree, writes and verifies a SHA-256 Manifest, then swaps that tree into place; CLI commands are thin publish/verify/Preview adapters. Episode and Topic synthesizers retain content decisions but no longer own formal-root replacement or formal Markdown re-parsing.

**Tech Stack:** Python 3.12 standard library (`dataclasses`, `enum`, `hashlib`, `json`, `os`, `pathlib`, `shutil`, `tempfile`, `time`), pytest/unittest, Markdown/JSON artifacts.

## Global Constraints

- The public lifecycle seam is exactly `KnowledgeBasePublisher.publish(request) -> PublicationManifest` and `KnowledgeBasePublisher.verify(root) -> PublicationVerification`; stage/render/hash/swap/cleanup remain private.
- Only the complete current source set may become a formal Publication. No episode or topic subset parameter exists on `PublicationRequest`.
- A Preview may write only to an explicit new or empty isolated directory, or stdout for the existing single-episode dry run. It never writes the managed formal root or emits full-corpus claims for a subset.
- One publication uses the same in-memory `EpisodeNote` tuple for Topic Guide synthesis, Episode rendering, Topic grounding, root index, root README, statistics, and Manifest source episodes.
- `publication-manifest.json` schema version is `1`; it records sorted source episodes, sorted Topic slugs, publication statistics, and every non-Manifest artifact's POSIX path, byte size, and SHA-256.
- The formal root after success contains only root `README.md`, `_index.md`, `episodes/`, `topics/`, and `publication-manifest.json`; every source episode has one slim and one full note, and every catalog Topic has one guide.
- Destination ownership accepts only a missing/empty directory, a valid Manifest-managed Publication, or a strictly recognizable legacy Publication. Unknown non-empty directories are rejected without `--force`.
- Staging, backup, and lock are siblings of the destination on the same filesystem. The destination lock is fail-fast; a second publisher never waits or overwrites.
- Any synthesis, render, Manifest, verify, or commit failure preserves the prior root. Failed staging is removed by default and retained only when `keep_failed_staging=True`.
- Destination normalization rejects filesystem root, the current user's home, the repository workspace root, and a symlink destination. No new network, credential, database, remote storage, daemon, or dependency is introduced.
- The `/mnt/c` rename/lock/rollback contract must pass before the CLI caller is switched or the formal `gooaye-youtube-notes/` root is published.
- Current expected source coverage is 690 synthesis-ready episodes (EP1–EP691 except EP232), four Topic Guides, and unchanged progressive-retrieval filenames.

---

### Task 1: In-memory Episode Synthesis and Explicit Topic Catalog

**Files:**
- Create: `.work/topic_catalog.py`
- Modify: `.work/episode_synthesizer.py`
- Modify: `.work/topic_synthesizer.py`
- Modify: `.work/markdown_renderer.py`
- Modify: `.work/test_episode_synthesizer.py`
- Modify: `.work/test_markdown_renderer.py`
- Modify: `.work/test_topic_synthesizer.py`

**Interfaces:**
- Produces: `EpisodeNoteSynthesizer.synthesize_notes(resolver=None, takeaway_resolver=None, max_workers=1, episode_numbers=None) -> SynthesisSummary`.
- Produces: `DEFAULT_TOPICS: tuple[TopicDefinition, ...]` from `topic_catalog.py`.
- Produces: `MarkdownRenderer.render_index(notes, summary, topics) -> str` with no hard-coded Topic rows.
- Preserves temporarily: `synthesize_all(...)` delegates to `synthesize_notes(...)` and keeps the old writer behavior until Task 6 migrates the caller.

- [ ] **Step 1: Write the RED in-memory seam test**

```python
def test_synthesize_notes_returns_complete_summary_without_writing(tmp_path):
    synthesizer = make_fixture_synthesizer(tmp_path, episode_numbers=(1, 2))

    summary = synthesizer.synthesize_notes(max_workers=1)

    assert [note.metadata.number for note in summary.notes] == [1, 2]
    assert summary.total_episodes == 2
    assert summary.total_chapters == sum(len(note.chapters) for note in summary.notes)
    assert list(tmp_path.rglob("*.md")) == []
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python3 -m pytest .work/test_episode_synthesizer.py -q -k synthesize_notes_returns`

Expected: fail because `EpisodeNoteSynthesizer` has no `synthesize_notes` method.

- [ ] **Step 3: Extract synthesis from writing**

Implement `synthesize_notes()` by moving the current target-number selection, parallel `synthesize_episode()` calls, and `SynthesisSummary` calculation out of `synthesize_all()`. Keep each worker pure: it returns an `EpisodeNote` and performs no filesystem write. Make `synthesize_all()` call `synthesize_notes()` and then write the legacy preview files so existing callers remain green during this migration stage.

- [ ] **Step 4: Run the Episode tests and verify GREEN**

Run: `python3 -m pytest .work/test_episode_synthesizer.py -q`

Expected: all Episode tests pass and the new test observes zero files.

- [ ] **Step 5: Write the RED explicit-catalog renderer test**

```python
def test_index_renders_only_the_supplied_topic_catalog(sample_notes, sample_summary):
    topic = TopicDefinition(
        slug="only-topic",
        title="Only Topic",
        description="One explicit catalog entry.",
        category="test",
    )

    rendered = MarkdownRenderer.render_index(
        sample_notes,
        sample_summary,
        topics=(topic,),
    )

    assert "topics/only-topic.md" in rendered
    assert "topics/ai-hardware-and-semiconductor.md" not in rendered
```

- [ ] **Step 6: Run the renderer test and verify RED**

Run: `python3 -m pytest .work/test_markdown_renderer.py -q -k supplied_topic_catalog`

Expected: fail because `render_index()` does not accept `topics` and the catalog rows are hard-coded.

- [ ] **Step 7: Move `DEFAULT_TOPICS` and render catalog data**

Move the complete four-definition tuple unchanged from `topic_synthesizer.py` to `topic_catalog.py`. Import it from the Topic synthesizer and CLI. Add `topics: Sequence[TopicDefinition] = ()` to `render_index()` and generate rows from `slug`, `title`, `category`, and `description`. During compatibility, `synthesize_all()` explicitly passes `DEFAULT_TOPICS`; no renderer default imports the catalog.

- [ ] **Step 8: Run focused baseline tests**

Run: `python3 -m pytest .work/test_episode_synthesizer.py .work/test_topic_synthesizer.py .work/test_markdown_renderer.py -q`

Expected: all pass; Topic scoring and rendered Episode content remain unchanged.

- [ ] **Step 9: Commit Task 1**

```bash
git add -- .work/topic_catalog.py .work/episode_synthesizer.py .work/topic_synthesizer.py .work/markdown_renderer.py .work/test_episode_synthesizer.py .work/test_topic_synthesizer.py .work/test_markdown_renderer.py
git commit -m "refactor(publication): add in-memory synthesis seam"
```

---

### Task 2: Managed Publication Manifest and Read-only Verification

**Files:**
- Create: `.work/knowledge_base_publisher.py`
- Create: `.work/test_knowledge_base_publisher.py`

**Interfaces:**
- Produces: immutable `PublicationArtifact`, `PublicationManifest`, `PublicationDefect`, `PublicationVerification`, and `PublicationMode`.
- Produces: `KnowledgeBasePublisher.verify(root: Path) -> PublicationVerification`.
- Uses: `publication-manifest.json` and public artifact paths only; verification performs no writes.

- [ ] **Step 1: Write the RED managed-fixture verification test**

```python
def test_verify_accepts_a_complete_manifest_managed_publication(tmp_path):
    root = build_managed_fixture(
        tmp_path / "publication",
        episodes=(1, 2),
        topics=("only-topic",),
    )
    before = snapshot_bytes(root)

    report = KnowledgeBasePublisher().verify(root)

    assert report.is_valid
    assert report.mode is PublicationMode.MANAGED
    assert report.episode_count == 2
    assert report.topic_count == 1
    assert snapshot_bytes(root) == before
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python3 -m pytest .work/test_knowledge_base_publisher.py -q -k complete_manifest_managed`

Expected: collection fails because `knowledge_base_publisher` does not exist.

- [ ] **Step 3: Define stable immutable result types**

```python
MANIFEST_FILENAME = "publication-manifest.json"
PUBLICATION_SCHEMA_VERSION = 1

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
```

Implement strict JSON decoding with type checks. Artifact paths must be normalized relative POSIX paths without `..`, absolute roots, duplicate entries, backslashes, or the Manifest itself.

- [ ] **Step 4: Implement managed verification**

For a managed root, compare the Manifest artifact set with every regular file below the root except `publication-manifest.json`; report `missing`, `stale`, `size`, or `digest` defects. Require `README.md`, `_index.md`, `topics/README.md`, both `episodes/EPxxxx.md` and `episodes/EPxxxx.full.md` for every source episode, and `topics/{slug}.md` for every catalog slug. Reject symlink artifacts and links that resolve outside the root.

- [ ] **Step 5: Run the happy-path test and verify GREEN**

Run: `python3 -m pytest .work/test_knowledge_base_publisher.py -q -k complete_manifest_managed`

Expected: pass without changing fixture bytes.

- [ ] **Step 6: Add RED tamper and graph tests one vertical slice at a time**

Add tests that mutate one fixture at a time and call only `verify(root)`:

```python
@pytest.mark.parametrize(
    ("mutation", "category"),
    [
        (delete_episode_full, "missing"),
        (tamper_topic_guide, "digest"),
        (add_stale_file, "stale"),
        (break_internal_link, "broken_link"),
        (escape_with_symlink, "unsafe_path"),
    ],
)
def test_verify_reports_managed_publication_defects(tmp_path, mutation, category):
    root = build_managed_fixture(tmp_path / "publication", episodes=(1,), topics=("only-topic",))
    mutation(root)

    report = KnowledgeBasePublisher().verify(root)

    assert not report.is_valid
    assert category in {defect.category for defect in report.defects}
```

Run each newly added case before implementation and observe RED, then add only the required completeness, digest, Markdown-link, or symlink rule.

- [ ] **Step 7: Add unknown-root ownership behavior**

```python
def test_verify_rejects_an_unknown_non_empty_directory(tmp_path):
    root = tmp_path / "unknown"
    root.mkdir()
    (root / "personal.txt").write_text("do not own", encoding="utf-8")

    report = KnowledgeBasePublisher().verify(root)

    assert report.mode is PublicationMode.UNKNOWN
    assert {d.category for d in report.defects} == {"ownership"}
```

Implement missing/empty roots as recognizable empty destinations and arbitrary non-empty roots as `UNKNOWN` ownership defects. Do not add a force flag.

- [ ] **Step 8: Run Task 2 tests**

Run: `python3 -m pytest .work/test_knowledge_base_publisher.py -q`

Expected: all managed/unknown verification tests pass with no writes.

- [ ] **Step 9: Commit Task 2**

```bash
git add -- .work/knowledge_base_publisher.py .work/test_knowledge_base_publisher.py
git commit -m "feat(publication): verify managed manifests"
```

---

### Task 3: Full-tree Rendering and Successful Transactional Publish

**Files:**
- Modify: `.work/knowledge_base_publisher.py`
- Modify: `.work/test_knowledge_base_publisher.py`

**Interfaces:**
- Produces: `PublicationRequest(destination: Path, resolver=None, takeaway_resolver=None, max_workers=1, keep_failed_staging=False)`.
- Produces: `KnowledgeBasePublisher.publish(request: PublicationRequest) -> PublicationManifest`.
- Consumes: `EpisodeNoteSynthesizer.synthesize_notes()`, `TopicGuideSynthesizer.synthesize_all_topics()`, `MarkdownRenderer`, `TopicGuideRenderer`, and explicit `DEFAULT_TOPICS`.

- [ ] **Step 1: Write the RED full fixture publish test**

```python
def test_publish_builds_and_verifies_one_complete_tree(tmp_path):
    publisher = make_fixture_publisher(episode_numbers=(1, 2), topic_slugs=("only-topic",))
    destination = tmp_path / "publication"

    manifest = publisher.publish(PublicationRequest(destination=destination))
    report = publisher.verify(destination)

    assert report.is_valid
    assert manifest.source_episodes == (1, 2)
    assert manifest.topic_catalog == ("only-topic",)
    assert sorted(path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()) == [
        "README.md",
        "_index.md",
        "episodes/EP0001.full.md",
        "episodes/EP0001.md",
        "episodes/EP0002.full.md",
        "episodes/EP0002.md",
        "publication-manifest.json",
        "topics/README.md",
        "topics/only-topic.md",
    ]
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python3 -m pytest .work/test_knowledge_base_publisher.py -q -k publish_builds_and_verifies`

Expected: fail because `PublicationRequest` and `publish()` do not exist.

- [ ] **Step 3: Implement request validation and rendering**

Reject non-positive workers and dangerous destinations before any write. In one sibling staging directory, call `synthesize_notes()` without episode filters, derive every Topic Guide from `summary.notes`, and render:

```text
README.md
_index.md
episodes/EPxxxx.md
episodes/EPxxxx.full.md
topics/README.md
topics/{catalog-slug}.md
```

Build sorted `PublicationArtifact` records from the staged bytes, write `publication-manifest.json`, call the same public `verify(stage)`, and install the verified stage at a missing/empty destination with `os.replace()`.

- [ ] **Step 4: Run the happy path and verify GREEN**

Run: `python3 -m pytest .work/test_knowledge_base_publisher.py -q -k publish_builds_and_verifies`

Expected: pass; Manifest covers every non-Manifest file and `verify()` reports zero defects.

- [ ] **Step 5: Prove one in-memory source batch**

Add a fixture synthesizer whose `synthesize_notes()` raises on a second call and whose notes contain values later visible in Topic Guide links, dates, headings, and takeaways. Assert `publish()` succeeds and the fixture's call count is exactly one. This is a public outcome test for the no-reparse/no-second-synthesis invariant.

- [ ] **Step 6: Prove idempotency and stale removal**

Publish version A, add no files manually, publish version B with a changed Topic catalog, and assert the destination contains only version B's Manifest artifacts. Repeating version B must remain valid and must not accumulate backups or staging directories.

- [ ] **Step 7: Run Task 3 tests**

Run: `python3 -m pytest .work/test_knowledge_base_publisher.py .work/test_episode_synthesizer.py .work/test_topic_synthesizer.py .work/test_markdown_renderer.py -q`

Expected: all pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add -- .work/knowledge_base_publisher.py .work/test_knowledge_base_publisher.py
git commit -m "feat(publication): render complete staged trees"
```

---

### Task 4: Lock, Failure Policy, Rollback, and Destination Safety

**Files:**
- Modify: `.work/knowledge_base_publisher.py`
- Modify: `.work/test_knowledge_base_publisher.py`

**Interfaces:**
- Produces: `PublicationPhase` and `PublicationError(phase, message, defects=(), staging_path=None)`.
- Preserves: prior complete root byte-for-byte for synthesis, render, Manifest, verify, or commit failure.
- Owns privately: sibling lock, staging, backup, rollback, cleanup, and conservative stale-lock recovery.

- [ ] **Step 1: Write the RED fail-fast lock test**

```python
def test_second_publisher_fails_fast_while_destination_is_locked(tmp_path):
    destination = tmp_path / "publication"
    publisher = make_fixture_publisher(block_during_synthesis=True)

    with publisher_held_in_background(publisher, PublicationRequest(destination)):
        started = time.monotonic()
        with pytest.raises(PublicationError) as raised:
            publisher.publish(PublicationRequest(destination))

    assert raised.value.phase is PublicationPhase.LOCK
    assert time.monotonic() - started < 1.0
```

- [ ] **Step 2: Run the lock test and verify RED**

Run: `python3 -m pytest .work/test_knowledge_base_publisher.py -q -k second_publisher_fails_fast`

Expected: fail because no destination lock exists.

- [ ] **Step 3: Implement the sibling lock**

Create `.<destination-name>.publication.lock` with `os.open(..., O_CREAT | O_EXCL | O_WRONLY)`. Store schema, normalized destination, PID, hostname, and UTC creation time. Always release a lock owned by the current invocation. Recover only a same-host lock older than 24 hours whose PID is definitively absent; malformed, young, foreign-host, permission-ambiguous, or live locks remain locked and return `PublicationPhase.LOCK`.

- [ ] **Step 4: Add phase failure tests**

Through `publish()` only, inject observable failures using a raising fixture synthesizer, raising renderer, Manifest `Path.write_text` failure, a renderer that creates a broken staged link, and an `os.replace` install failure. For every case:

```python
before = snapshot_bytes(existing_root)
with pytest.raises(PublicationError) as raised:
    failing_publisher.publish(PublicationRequest(existing_root))
assert raised.value.phase is expected_phase
assert snapshot_bytes(existing_root) == before
assert no_sibling_staging_or_backup(existing_root)
```

Run each case RED before adding its `PublicationPhase` mapping and cleanup path.

- [ ] **Step 5: Implement replace and rollback**

For an existing managed/legacy root, rename it to a unique sibling backup, rename the verified stage to the destination, verify the installed destination, and only then remove the backup. If install or installed verification fails, restore the backup. Normalize filesystem failures to `PublicationError(COMMIT, ...)`; if rollback also fails, report both failures and retain the recoverable backup path.

- [ ] **Step 6: Test failed-stage retention**

With `keep_failed_staging=False`, assert the error carries no existing staging directory. With `True`, assert `error.staging_path` exists, is outside the formal root, and the old root remains byte-identical. Successful calls always remove staging and backup siblings.

- [ ] **Step 7: Test destination safety**

Parametrize filesystem root, `Path.home()`, repository root, a symlink destination, and an unknown non-empty directory. Assert `publish()` raises `PublicationError(OWNERSHIP, ...)` before creating a lock/stage and does not change the target. Do not introduce `--force`.

- [ ] **Step 8: Run Task 4 tests**

Run: `python3 -m pytest .work/test_knowledge_base_publisher.py -q`

Expected: all lifecycle, concurrency, cleanup, and rollback tests pass.

- [ ] **Step 9: Commit Task 4**

```bash
git add -- .work/knowledge_base_publisher.py .work/test_knowledge_base_publisher.py
git commit -m "feat(publication): add transactional commit and lock"
```

---

### Task 5: Strict Legacy Recognition and `/mnt/c` Filesystem Contract

**Files:**
- Modify: `.work/knowledge_base_publisher.py`
- Modify: `.work/test_knowledge_base_publisher.py`
- Create: `.work/test_knowledge_base_publication_filesystem_contract.py`

**Interfaces:**
- Extends: `verify(root)` with `PublicationMode.LEGACY`.
- Produces evidence: current legacy formal root is recognizable without writes.
- Produces evidence: sibling lock/rename/rollback works in an explicit safe temporary directory under `/mnt/c/coding/gooaye-agent/.work/`.

- [ ] **Step 1: Write the RED legacy fixture test**

```python
def test_verify_recognizes_a_complete_legacy_tree_without_writing(tmp_path):
    root = build_legacy_fixture(tmp_path / "legacy", episodes=(1, 2), topics=DEFAULT_TOPICS)
    before = snapshot_bytes(root)

    report = KnowledgeBasePublisher().verify(root)

    assert report.is_valid
    assert report.mode is PublicationMode.LEGACY
    assert report.episode_count == 2
    assert report.topic_count == len(DEFAULT_TOPICS)
    assert snapshot_bytes(root) == before
```

- [ ] **Step 2: Run the legacy test and verify RED**

Run: `python3 -m pytest .work/test_knowledge_base_publisher.py -q -k complete_legacy_tree`

Expected: fail because a non-Manifest tree is still unknown.

- [ ] **Step 3: Implement strict legacy recognition**

Recognize legacy only when root README/index exist, slim/full Episode filenames form identical non-empty sets, exactly the explicit Topic catalog guides plus `topics/README.md` exist, every local link resolves, and `TopicQualityAuditor` reports zero grounding defects. Legacy recognition establishes ownership of an older complete tree; it does not claim its episode set equals the latest acquisition set.

- [ ] **Step 4: Add RED rejection variants**

Delete one full note, delete one Topic, break one link, add one unexpected top-level file, and corrupt one Topic reference. Each must return `PublicationMode.UNKNOWN` or an invalid `LEGACY` report with explicit `ownership`, `missing`, `stale`, `broken_link`, or `grounding` defects. The current formal tree must not be changed.

- [ ] **Step 5: Run read-only verification on the real formal root**

Run: `python3 .work/cli.py doctor` before any CLI migration, then invoke `KnowledgeBasePublisher().verify(Path("gooaye-youtube-notes"))` from a read-only Python command.

Expected: mode `legacy`, zero defects, 689 slim/full pairs, four Topic Guides, and no changed files in `git status --short gooaye-youtube-notes`.

- [ ] **Step 6: Add and run the `/mnt/c` contract**

The contract uses `TemporaryDirectory(prefix="knowledge-base-publication-contract-", dir=REPO_ROOT / ".work")`. It publishes version A, holds/rejects a second lock, publishes version B, injects second-rename failure, proves version B remains complete, verifies it, and asserts no lock/staging/backup remains. It removes only the directory it created.

Run: `python3 -m pytest .work/test_knowledge_base_publication_filesystem_contract.py -q`

Expected: pass on `/mnt/c`.

- [ ] **Step 7: Commit Task 5**

```bash
git add -- .work/knowledge_base_publisher.py .work/test_knowledge_base_publisher.py .work/test_knowledge_base_publication_filesystem_contract.py
git commit -m "test(publication): prove legacy and mnt-c contracts"
```

---

### Task 6: Publish/Verify CLI and Isolated Preview Migration

**Files:**
- Modify: `.work/cli.py`
- Create: `.work/test_cli_publication.py`
- Modify: `.work/episode_synthesizer.py`
- Modify: `.work/test_episode_synthesizer.py`
- Modify: `.work/test_topic_synthesizer.py`

**Interfaces:**
- Produces: `publish --output-dir PATH [--resolver ...] [--workers N] [--keep-failed-staging]`.
- Produces: `verify --output-dir PATH`.
- Changes: non-dry `synthesize` and `topics --generate` require an explicit new/empty Preview output directory and reject the managed formal root.
- Removes: formal publication's dependency on `load_all_notes_from_dir()` and the old two-command ordering.

- [ ] **Step 1: Write RED CLI shape tests**

```python
def test_publish_has_no_subset_flags():
    result = run_cli(["publish", "--help"])
    assert result.returncode == 0
    assert "--output-dir" in result.stdout
    assert "--resolver" in result.stdout
    assert "--workers" in result.stdout
    assert "--episode" not in result.stdout
    assert "--topic" not in result.stdout

def test_preview_requires_an_explicit_isolated_destination():
    result = run_cli(["synthesize", "--episode", "1"])
    assert result.returncode != 0
    assert "Preview output directory" in result.stderr
```

- [ ] **Step 2: Run CLI tests and verify RED**

Run: `python3 -m pytest .work/test_cli_publication.py -q`

Expected: `publish`/`verify` are unknown and synthesize still defaults to the formal root.

- [ ] **Step 3: Implement thin publish and verify adapters**

Construct the selected Heading resolver exactly once, pass it in `PublicationRequest`, and call the publisher. Success output includes phase durations, commit result, artifact/episode/topic counts, root, and verification OK. `PublicationError` prints phase, defects, and retained staging path to stderr and exits non-zero. `verify` prints mode/counts/defects and never writes.

- [ ] **Step 4: Make Preview destinations explicit and safe**

Set synthesize/topic output defaults to `None`. Keep single-episode `--dry-run` on stdout. Every non-dry Preview requires an explicit path that is missing or empty, differs from `OUTPUT_DIR`, and is not a symlink/broad destination. Preview writes no Manifest, no full-corpus root README/index for a subset, and never deletes a pre-existing non-empty directory.

- [ ] **Step 5: Add hermetic CLI integration tests**

Use an isolated work/data root and fixture publisher collaborators to verify successful publish/verify output, lock/ownership errors, and Preview rejection. Assert no test writes `gooaye-youtube-notes/`. Keep implementation errors uncaught.

- [ ] **Step 6: Remove formal Markdown re-parsing**

The `publish` path must not call `load_all_notes_from_dir()`. Keep that parser only for legacy audit or explicit Preview compatibility if still used; remove silent `except Exception: continue` from any formal path. Update tests to assert formal Topics derive from the same `summary.notes` tuple.

- [ ] **Step 7: Run CLI and focused content tests**

Run: `python3 -m pytest .work/test_cli_publication.py .work/test_cli_download.py .work/test_episode_synthesizer.py .work/test_topic_synthesizer.py .work/test_markdown_renderer.py -q`

Expected: all pass; download behavior remains unchanged.

- [ ] **Step 8: Commit Task 6**

```bash
git add -- .work/cli.py .work/test_cli_publication.py .work/episode_synthesizer.py .work/test_episode_synthesizer.py .work/test_topic_synthesizer.py
git commit -m "feat(publication): route formal writes through publisher"
```

---

### Task 7: Formal Migration, Documentation, and End-state Verification

**Files:**
- Modify: `README.md`
- Modify: `CONTEXT.md`
- Existing: `docs/adr/0004-transactional-knowledge-base-publication.md`
- Modify through `publish`: `gooaye-youtube-notes/`

**Interfaces:**
- Produces: one Manifest-managed formal Publication containing all 690 current source episodes and four Topic Guides.
- Documents: Publication/Preview commands, failure policy, two-times-space requirement, and rollback.
- Deletes: obsolete formal writer/order assumptions and hard-coded catalog logic proven unused.

- [ ] **Step 1: Update domain and operator documentation**

Add `KnowledgeBasePublisher` to the deep-module section, make Preview a standalone glossary term, document `publish` and `verify`, and distinguish 690 current source/publication episodes from the previous 689-video release. State that Preview is isolated and `download` still does not publish.

- [ ] **Step 2: Run the complete offline suite before formal mutation**

Run: `python3 -m pytest .work -q`

Expected: all tests pass; the opt-in acquisition live contract remains the only default skip.

- [ ] **Step 3: Verify legacy root and available space**

Run: `python3 .work/cli.py verify --output-dir gooaye-youtube-notes`

Expected: valid legacy mode, 689 episode pairs, four Topics.

Run: `df -Pk gooaye-youtube-notes .`

Expected: available bytes exceed twice `du -sk gooaye-youtube-notes` plus 100 MiB safety margin. If not, stop before publication and report the blocker.

- [ ] **Step 4: Publish the formal tree through the new seam**

Run: `python3 .work/cli.py publish --output-dir gooaye-youtube-notes --resolver composite --workers 8`

Expected: managed publication installed only after successful staging verification; 690 Episode pairs (EP1–EP691 except EP232), four Topic Guides, and one `publication-manifest.json`.

- [ ] **Step 5: Prove managed verification and retrieval paths**

Run: `python3 .work/cli.py verify --output-dir gooaye-youtube-notes`

Run: `python3 .work/cli.py doctor`

Expected: managed mode, zero defects, every Manifest digest valid, and doctor healthy. Confirm `gooaye-youtube-notes/episodes/EP0691.md`, `.full.md`, `_index.md`, all four Topic links, and the Gooaye skill Stage 1/1.5/2 paths exist.

- [ ] **Step 6: Prove repeat publication and Preview isolation**

Run the same `publish` command again and verify no stale staging/backup/lock siblings remain. Run a single-episode dry run and one explicit temp Preview; assert neither changes any tracked formal Publication byte.

- [ ] **Step 7: Run final checks and review**

Run: `git diff --check`

Run: `python3 -m pytest .work -q`

Run: `python3 .work/cli.py verify --output-dir gooaye-youtube-notes`

Review every changed file against ADR 0004. Confirm no formal writer remains outside `KnowledgeBasePublisher`, no hard-coded Topic catalog remains in `MarkdownRenderer`, no formal path re-parses newly written Markdown, no unknown non-empty directory can be forced, and no acquisition/source artifact was modified.

- [ ] **Step 8: Commit Task 7**

```bash
git add -- README.md CONTEXT.md gooaye-youtube-notes
git commit -m "feat(publication): migrate formal knowledge base"
```
