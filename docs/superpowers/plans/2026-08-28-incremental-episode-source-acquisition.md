# Incremental Episode Source Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a test-driven `download --episode N | --latest` workflow that commits one verified Episode Source Snapshot and use it to acquire EP691.

**Architecture:** `EpisodeAcquirer` translates three upstream formats into one in-memory snapshot. `EpisodeSourceRepository` owns legacy/new lookup, validation, idempotency, conflict handling, and staged per-episode directory replacement; `EpisodeNoteSynthesizer` consumes only that repository seam. The CLI is a thin adapter and acquisition never synthesizes or publishes notes.

**Tech Stack:** Python 3.12 standard library (`urllib`, `xml.etree.ElementTree`, `json`, `hashlib`, `pathlib`, `tempfile`), pytest/unittest, Markdown/JSON source artifacts.

## Global Constraints

- Default tests perform no network calls; fixtures mirror complete live YouTube RSS, SoundOn RSS, archive JSON, and transcript responses.
- No `yt-dlp` dependency. Unknown episodes outside the official feed window fail explicitly.
- A snapshot contains official metadata, curated archive metadata, transcript, hashes, provenance URLs, and fetch time.
- `--latest` targets the newest official YouTube episode and reports `archive pending` when the remaining sources are not ready.
- Identical content is a no-op; changed content requires `--force`; Git owns revision history.
- New snapshots live under `.work/episode-sources/EPxxxx/`; legacy source files remain readable and unmodified.
- Acquisition never writes `gooaye-youtube-notes/`, heading caches, indexes, topics, or a Publication.
- No commits are created during this execution unless the user separately authorizes them.

---

### Task 1: Episode Source Repository

**Files:**
- Create: `.work/episode_source_repository.py`
- Create: `.work/test_episode_source_repository.py`
- Modify: `.work/domain.py`

**Interfaces:**
- Produces: `EpisodeSourceSnapshot`, `EpisodeSourceVerification`, `EpisodeSourceRepository`.
- Produces: `commit(snapshot, force=False) -> Literal["created", "unchanged", "updated"]`.
- Produces: `verify(number) -> EpisodeSourceVerification`, `get_metadata(number) -> EpisodeMetadata`, `load_transcript(number) -> str`, and `episode_numbers -> list[int]`.

- [ ] **Step 1: Write failing snapshot validation tests**

```python
def test_commit_creates_a_verified_self_contained_snapshot(tmp_path):
    repository = make_repository(tmp_path)
    result = repository.commit(make_snapshot(691))
    assert result == "created"
    assert repository.verify(691).is_valid
    assert (tmp_path / "episode-sources/EP0691/snapshot.json").is_file()
    assert (tmp_path / "episode-sources/EP0691/transcript.md").is_file()

def test_verify_rejects_a_tampered_transcript(tmp_path):
    repository = make_repository(tmp_path)
    repository.commit(make_snapshot(691))
    (tmp_path / "episode-sources/EP0691/transcript.md").write_text("tampered", encoding="utf-8")
    assert "sha256" in repository.verify(691).defects
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python3 -m pytest .work/test_episode_source_repository.py -q`

Expected: collection fails because `episode_source_repository` does not exist.

- [ ] **Step 3: Implement immutable snapshot types and validation**

```python
@dataclass(frozen=True)
class EpisodeSourceSnapshot:
    number: int
    youtube_id: str
    youtube_title: str
    published_at: str
    duration_seconds: int
    archive_filename: str
    display_title: str
    archive_date: str
    summary: str
    transcript: str
    source_urls: Mapping[str, str]
    fetched_at: str
```

Validation must reject non-positive episode numbers, mismatched transcript headings, invalid YouTube IDs, empty titles/summaries, non-positive duration, malformed dates, HTML/error bodies, path traversal in remote filenames, and transcript bodies smaller than 1,000 UTF-8 bytes.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `python3 -m pytest .work/test_episode_source_repository.py -q`

Expected: all repository validation tests pass.

- [ ] **Step 5: Add RED tests for idempotency, force, rollback, and legacy overlay**

```python
def test_changed_snapshot_requires_force(tmp_path):
    repository = make_repository(tmp_path)
    repository.commit(make_snapshot(691, transcript="# EP691\n" + "甲" * 1000))
    with pytest.raises(SnapshotConflictError):
        repository.commit(make_snapshot(691, transcript="# EP691\n" + "乙" * 1000))

def test_force_replaces_the_complete_directory(tmp_path):
    repository = make_repository(tmp_path)
    repository.commit(make_snapshot(691, transcript="# EP691\n" + "甲" * 1000))
    assert repository.commit(make_snapshot(691, transcript="# EP691\n" + "乙" * 1000), force=True) == "updated"
    assert "乙" in repository.load_transcript(691)
    assert repository.verify(691).is_valid
```

Also test same-hash no-op, an injected second-rename failure restores the prior directory, an invalid snapshot never creates the target, snapshot data overrides legacy data for the same number, and legacy-only EP1 still loads unchanged.

- [ ] **Step 6: Implement staged directory commit and legacy/new reads**

Write `snapshot.json` and `transcript.md` in a sibling staging directory, verify that directory, then rename it across the commit boundary. For forced replacement, rename the old target to a sibling backup, install staging, restore backup on failure, and remove the backup only after the installed target verifies.

- [ ] **Step 7: Run focused and baseline tests**

Run: `python3 -m pytest .work/test_episode_source_repository.py .work/test_domain.py .work/test_episode_synthesizer.py -q`

Expected: all pass with no warnings.

---

### Task 2: Upstream Source Adapters and Acquisition Orchestration

**Files:**
- Create: `.work/episode_acquirer.py`
- Create: `.work/test_episode_acquirer.py`

**Interfaces:**
- Consumes: `EpisodeSourceSnapshot`, `EpisodeSourceRepository.commit()`.
- Produces: `EpisodeAcquirer.acquire(number, force=False) -> AcquisitionResult`.
- Produces: `EpisodeAcquirer.acquire_latest(force=False) -> AcquisitionResult`.
- Produces: `UrlLibHttpClient.get(url, accept) -> HttpResponse`.

- [ ] **Step 1: Write RED parser tests with complete source fixtures**

```python
def test_acquire_builds_ep691_from_all_authorities(tmp_path):
    client = FixtureHttpClient(ep691_responses())
    acquirer = EpisodeAcquirer(repository=make_repository(tmp_path), http_client=client, clock=fixed_clock)
    result = acquirer.acquire(691)
    assert result.number == 691
    assert result.status == "created"
    assert result.youtube_id == "J-e9oxqLzpc"
    assert result.duration_seconds == 2995
```

Fixtures must include all real fields used by the upstream formats, namespaces, content types, filenames, CJK text, and the one-second duration variance observed between official surfaces.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python3 -m pytest .work/test_episode_acquirer.py -q`

Expected: collection fails because `episode_acquirer` does not exist.

- [ ] **Step 3: Implement standard-library adapters**

Parse YouTube Atom with its `yt` namespace, SoundOn RSS with the `itunes` namespace, archive JSON as UTF-8, and transcript Markdown as bytes before decoding. Match episode numbers exactly and URL-encode the archive filename as one path segment.

- [ ] **Step 4: Run the happy-path test and verify GREEN**

Run: `python3 -m pytest .work/test_episode_acquirer.py::test_acquire_builds_ep691_from_all_authorities -q`

Expected: pass.

- [ ] **Step 5: Add RED failure-policy tests**

```python
def test_latest_reports_archive_pending_instead_of_falling_back(tmp_path):
    client = FixtureHttpClient(responses_with_youtube_692_but_archive_through_691())
    acquirer = EpisodeAcquirer(repository=make_repository(tmp_path), http_client=client)
    with pytest.raises(ArchivePendingError, match="EP692"):
        acquirer.acquire_latest()
```

Also test unknown-outside-feed, mismatched episode IDs, SoundOn absence, date mismatch, malformed XML/JSON, HTML returned as transcript, 404 transcript, timeout, incomplete body, and legacy official metadata fallback for an existing old episode.

- [ ] **Step 6: Implement typed errors and source cross-checks**

Errors must distinguish `EpisodeNotInOfficialFeedError`, `ArchivePendingError`, `SourceFormatError`, `SourceMismatchError`, `SourceNetworkError`, `SnapshotConflictError`, and filesystem commit errors. Fetch and validate every source before calling `repository.commit()`.

- [ ] **Step 7: Run the complete acquisition tests**

Run: `python3 -m pytest .work/test_episode_acquirer.py .work/test_episode_source_repository.py -q`

Expected: all pass offline.

---

### Task 3: CLI and Synthesizer Integration

**Files:**
- Modify: `.work/cli.py`
- Modify: `.work/episode_synthesizer.py`
- Modify: `.work/test_episode_synthesizer.py`
- Create: `.work/test_cli_download.py`

**Interfaces:**
- Consumes: `EpisodeAcquirer`, `EpisodeSourceRepository`.
- Produces: `download --episode N | --latest [--force]`.
- Preserves: existing `EpisodeNoteSynthesizer` public methods and legacy corpus behavior.

- [ ] **Step 1: Write RED CLI contract tests**

```python
def test_download_requires_exactly_one_selector():
    result = run_cli(["download"])
    assert result.returncode != 0
    assert "--episode" in result.stderr
    assert "--latest" in result.stderr
```

Run a hermetic local HTTP server or inject fixture endpoints through task-specific environment variables; assert a successful command creates only `.work/episode-sources/EP0691/` under an isolated root and prints episode, status, verification, and path.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python3 -m pytest .work/test_cli_download.py -q`

Expected: argparse rejects the unknown `download` command.

- [ ] **Step 3: Add the thin CLI adapter**

```python
selector = p_download.add_mutually_exclusive_group(required=True)
selector.add_argument("--episode", type=positive_episode_number)
selector.add_argument("--latest", action="store_true")
p_download.add_argument("--force", action="store_true")
```

Map typed acquisition failures to concise stderr messages and non-zero exit codes. Do not catch unexpected programmer errors.

- [ ] **Step 4: Run CLI tests and verify GREEN**

Run: `python3 -m pytest .work/test_cli_download.py -q`

Expected: all pass.

- [ ] **Step 5: Add a RED synthesizer overlay test**

```python
def test_synthesizer_reads_new_snapshot_without_rewriting_legacy_sources(tmp_path):
    repository = make_repository_with_legacy_ep1_and_snapshot_ep691(tmp_path)
    synthesizer = EpisodeNoteSynthesizer(source_repository=repository)
    assert synthesizer.get_metadata(691).youtube_id == "J-e9oxqLzpc"
    assert synthesizer.load_transcript(691).startswith("# EP691")
    assert 1 in synthesizer.episode_numbers
    assert 691 in synthesizer.episode_numbers
```

- [ ] **Step 6: Replace synthesizer source-layout knowledge with the repository seam**

Keep constructor compatibility for existing custom paths by constructing `EpisodeSourceRepository` when no repository is injected. Update `doctor` to report repository statistics instead of private synthesizer dictionaries.

- [ ] **Step 7: Run all offline tests**

Run: `python3 -m pytest .work -q`

Expected: the original 60 tests and every new test pass without network access.

---

### Task 4: Filesystem Contract and EP691 Live Acquisition

**Files:**
- Create: `.work/test_episode_source_filesystem_contract.py`
- Create on successful live acquisition: `.work/episode-sources/EP0691/snapshot.json`
- Create on successful live acquisition: `.work/episode-sources/EP0691/transcript.md`

**Interfaces:**
- Consumes: final repository, acquirer, and CLI.
- Produces: verified EP691 source snapshot.

- [ ] **Step 1: Write and run the `/mnt/c` filesystem contract**

The test creates an explicit safe temporary directory under the repository filesystem, commits version A, verifies idempotency, forces version B, injects commit failure, and proves version B remains complete. It removes only the temporary directory it created.

Run: `python3 -m pytest .work/test_episode_source_filesystem_contract.py -q`

Expected: pass on `/mnt/c`; no staging or backup directories remain.

- [ ] **Step 2: Run the opt-in live upstream contract without repository writes**

Run: `GOOAYE_LIVE_CONTRACT=1 python3 -m pytest .work/test_episode_acquirer.py -k live_ep691 -q`

Expected: YouTube/SoundOn/archive agree on EP691 and the transcript validates.

- [ ] **Step 3: Acquire EP691 through the user-facing CLI**

Run: `python3 .work/cli.py download --episode 691`

Expected: status `created`, verification `OK`, YouTube ID `J-e9oxqLzpc`, duration `2995`, and a verified `.work/episode-sources/EP0691/` directory.

- [ ] **Step 4: Prove idempotency and synthesizer visibility**

Run: `python3 .work/cli.py download --episode 691`

Expected: status `unchanged` and no file content changes.

Run: `python3 .work/cli.py synthesize --episode 691 --dry-run --resolver deterministic`

Expected: slim and full Markdown print to stdout; `gooaye-youtube-notes/` remains unchanged.

---

### Task 5: Documentation, Agent Retrieval, and Final Verification

**Files:**
- Modify: `CONTEXT.md`
- Modify: `README.md`
- Modify: `.agents/skills/gooaye/SKILL.md`
- Existing: `docs/adr/0003-incremental-episode-source-acquisition.md`

**Interfaces:**
- Documents: acquisition command, source/publication count distinction, and the new Stage 3 transcript path.

- [ ] **Step 1: Update domain and human documentation**

Record that source acquisition reaches EP691 while the formal Publication remains unchanged. Document the exact CLI selectors, force behavior, feed-window limitation, and the fact that acquisition does not synthesize or publish.

- [ ] **Step 2: Update the Gooaye skill retrieval branch**

Stage 3 must search both legacy `.work/full-transcripts/EPxxxx.md` and normalized `.work/episode-sources/EPxxxx/transcript.md`, preferring the normalized snapshot when both exist. Keep the pointer compact and avoid duplicating CLI documentation in the skill.

- [ ] **Step 3: Run self-review and verification**

Run: `git diff --check`

Run: `python3 -m pytest .work -q`

Run: `python3 .work/cli.py doctor`

Run: `python3 .work/cli.py download --episode 691`

Expected: clean diff check, all tests pass, doctor reports EP691 as a valid normalized source, and the final download is unchanged.

- [ ] **Step 4: Review every changed file against ADR 0003**

Confirm there is no `yt-dlp` dependency, no audio file, no write to the formal knowledge-base Publication, no silent fallback to an older episode, no unverified snapshot accepted by the repository, and no unrelated user change overwritten.
