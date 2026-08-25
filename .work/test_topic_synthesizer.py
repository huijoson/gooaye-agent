"""Unit tests for Topic Domain Model, Synthesizer, and Renderer (Issue #13)."""

import pytest
from domain import (
    Chapter,
    EpisodeMetadata,
    EpisodeNote,
    ThematicChapterRef,
    ThematicMilestone,
    TopicDefinition,
    TopicGuide,
)
from topic_synthesizer import TopicGuideRenderer, TopicGuideSynthesizer


def make_sample_episode_note(
    number: int,
    date: str,
    title: str,
    chapters_data: list[tuple[str, str, list[str]]],
) -> EpisodeNote:
    metadata = EpisodeMetadata(
        number=number,
        youtube_id=f"yt_{number}",
        youtube_url=f"https://youtu.be/yt_{number}",
        youtube_title=f"Gooaye EP{number} {title}",
        display_title=title,
        date=date,
        date_source="archive",
        duration_str="45:00",
        duration_seconds=2700,
        archive_url=f"https://example.com/ep/{number}",
        summary="測試摘要",
    )
    chapters = tuple(
        Chapter(
            index=i + 1,
            heading=h,
            takeaway=t,
            excerpts=tuple(e),
            position=i * 500,
        )
        for i, (h, t, e) in enumerate(chapters_data)
    )
    return EpisodeNote(metadata=metadata, chapters=chapters)


@pytest.fixture
def sample_episodes() -> list[EpisodeNote]:
    return [
        make_sample_episode_note(
            number=100,
            date="2021-03-15",
            title="散熱與晶圓代工早期評估",
            chapters_data=[
                (
                    "傳統伺服器氣冷散熱極限探討",
                    "氣冷散熱在瓦數突破極限時將面臨物理瓶頸，後續需關注水冷滲透率。",
                    ["傳統伺服器氣冷差不多到頂了", "後面瓦數再上去就要看水冷怎麼切"],
                ),
                (
                    "航運股行情與心態檢視",
                    "航運股屬於典型循環股，追高者需設好停損防範回吐。",
                    ["航運這波就是景氣循環", "不要抱上去又抱下來"],
                ),
            ],
        ),
        make_sample_episode_note(
            number=450,
            date="2024-05-20",
            title="GB200水冷架構與ASIC供應鏈",
            chapters_data=[
                (
                    "GB200伺服器水冷散熱與CDU供應鏈",
                    "GB200機櫃全面導入水冷與CDU散熱，台廠散熱供應鏈迎來實質規格升級與產值倍增。",
                    ["GB200整個水冷架構大幅改變", "CDU跟快接頭是這波關鍵零組件"],
                ),
                (
                    "Google與CSP自研ASIC晶片趨勢",
                    "CSP大廠為降低算力成本擴大自研ASIC晶片投片，帶動客製化設計服務商機。",
                    ["Google的TPU跟各大CSP都在做自研ASIC", "台灣的IP跟ASIC設計服務直接受惠"],
                ),
            ],
        ),
        make_sample_episode_note(
            number=690,
            date="2026-08-22",
            title="黑皮諾平替記與Google的COT轉向",
            chapters_data=[
                (
                    "Google自研晶片COT商業模式轉向",
                    "Google在自研晶片架構轉向COT模式，客製化設計服務與先進封裝供應鏈重新洗牌。",
                    ["Google在COT這塊有新的策略調整", "先進封裝跟CoWoS產能依然是兵家必爭之地"],
                ),
            ],
        ),
    ]


@pytest.fixture
def sample_topic_def() -> TopicDefinition:
    return TopicDefinition(
        slug="ai-hardware-and-semiconductor",
        title="AI 硬體、散熱、電力與 ASIC 自研晶片演進",
        description="追蹤 2021 至 2026 年主委對 AI 伺服器散熱（氣冷/水冷/CDU）、800V 電力與 CSP 自研 ASIC 晶片之論述脈絡。",
        category="產業與硬體架構",
        keywords=(
            "ASIC", "自研晶片", "散熱", "水冷", "氣冷", "CDU", "GB200", "COT",
            "CoWoS", "TPU", "先進封裝", "伺服器",
        ),
        core_concepts=("水冷散熱升級", "CSP 自研 ASIC", "先進封裝與代工"),
    )


def test_topic_domain_entities(sample_topic_def):
    ref = ThematicChapterRef(
        episode_number=450,
        episode_title="GB200水冷架構與ASIC供應鏈",
        published_at="2024-05-20",
        chapter_index=1,
        heading="GB200伺服器水冷散熱與CDU供應鏈",
        takeaway="GB200機櫃全面導入水冷與CDU散熱，台廠散熱供應鏈迎來實質規格升級與產值倍增。",
        relevance_score=15.0,
        matched_keywords=("GB200", "水冷", "散熱", "CDU"),
    )
    milestone = ThematicMilestone(
        period="2024: GB200與水冷全面爆發",
        summary="GB200架構確認水冷成為主流規格，散熱零件單價與毛利顯著提升。",
        key_episodes=(450,),
    )
    guide = TopicGuide(
        definition=sample_topic_def,
        time_span=("2021-03-15", "2026-08-22"),
        summary_takeaways=("散熱水冷升級帶動台廠供應鏈產值擴張。",),
        milestones=(milestone,),
        chapters=(ref,),
    )

    assert guide.slug == "ai-hardware-and-semiconductor"
    assert guide.title == "AI 硬體、散熱、電力與 ASIC 自研晶片演進"
    assert len(guide.chapters) == 1
    assert guide.chapters[0].episode_number == 450
    assert guide.time_span == ("2021-03-15", "2026-08-22")


def test_synthesizer_matches_and_scores_chapters(sample_topic_def, sample_episodes):
    synthesizer = TopicGuideSynthesizer()
    guide = synthesizer.synthesize_topic(sample_topic_def, sample_episodes)

    assert guide.slug == "ai-hardware-and-semiconductor"
    # Should match EP100 Ch1, EP450 Ch1, EP450 Ch2, EP690 Ch1 (4 chapters)
    # Should NOT match EP100 Ch2 (航運股)
    matched_episodes = {ch.episode_number for ch in guide.chapters}
    assert 100 in matched_episodes
    assert 450 in matched_episodes
    assert 690 in matched_episodes
    assert len(guide.chapters) == 4

    # Verify chronological ordering
    dates = [ch.published_at for ch in guide.chapters]
    assert dates == sorted(dates)
    assert guide.time_span == ("2021-03-15", "2026-08-22")

    # Verify takeaways were extracted
    assert len(guide.summary_takeaways) > 0


def test_renderer_outputs_valid_markdown(sample_topic_def, sample_episodes):
    synthesizer = TopicGuideSynthesizer()
    guide = synthesizer.synthesize_topic(sample_topic_def, sample_episodes)
    renderer = TopicGuideRenderer()
    md = renderer.render(guide)

    # Verify frontmatter
    assert "slug: \"ai-hardware-and-semiconductor\"" in md
    assert "title: \"AI 硬體、散熱、電力與 ASIC 自研晶片演進\"" in md
    assert "category: \"產業與硬體架構\"" in md
    assert "content_method: \"thematic_synthesis\"" in md

    # Verify document structure
    assert "# AI 硬體、散熱、電力與 ASIC 自研晶片演進" in md
    assert "## 🎯 核心結論速覽" in md
    assert "## ⏳ 觀點時序演進與重要里程碑" in md
    assert "## 📚 歷年深度觀點與章節精華" in md
    assert "## 🔗 相關集數索引與引用列表" in md

    # Verify relative markdown links to episodes
    assert "[EP100｜散熱與晶圓代工早期評估](../episodes/EP0100.md)" in md
    assert "[EP450｜GB200水冷架構與ASIC供應鏈](../episodes/EP0450.md)" in md
    assert "[EP690｜黑皮諾平替記與Google的COT轉向](../episodes/EP0690.md)" in md


def test_default_topics_catalog():
    from topic_synthesizer import DEFAULT_TOPICS
    assert len(DEFAULT_TOPICS) == 4
    slugs = {t.slug for t in DEFAULT_TOPICS}
    assert "ai-hardware-and-semiconductor" in slugs
    assert "investment-mindset-and-risk-control" in slugs
    assert "macro-cycle-and-asset-allocation" in slugs
    assert "apple-and-consumer-electronics" in slugs


def test_synthesize_all_topics_and_render_readme(sample_episodes, tmp_path):
    from topic_synthesizer import DEFAULT_TOPICS, TopicGuideSynthesizer

    synthesizer = TopicGuideSynthesizer()
    guides = synthesizer.synthesize_all_topics(sample_episodes, DEFAULT_TOPICS)
    assert len(guides) == 4

    out_files = synthesizer.synthesize_and_save_all(sample_episodes, tmp_path, DEFAULT_TOPICS)
    assert len(out_files) == 5  # 4 topic guides + 1 README.md

    readme_path = tmp_path / "README.md"
    assert readme_path.exists()
    readme_content = readme_path.read_text(encoding="utf-8")
    assert "# Gooaye 股癌 跨集數主題式深度知識庫指南" in readme_content
    assert "[AI 伺服器、散熱、電力與 ASIC 自研晶片演進](ai-hardware-and-semiconductor.md)" in readme_content


def test_load_note_from_markdown(tmp_path):
    from topic_synthesizer import load_note_from_markdown

    md_content = """---
episode: 1
title: "歐洲疫情與股市崩跌"
youtube_title: "EP1 | 國外反亞情緒 股市崩盤"
youtube_id: "xLS-2whm8Aw"
youtube_url: "https://www.youtube.com/watch?v=xLS-2whm8Aw"
episode_date: "2020-02-27"
episode_date_source: "transcript_archive"
duration: "23:43"
content_method: "hybrid_extractive_distilled"
---

# EP1｜歐洲疫情與股市崩跌

## 章節觀念

### 1. 歐洲疫情蔓延與排斥亞洲人

- **核心觀點：** 歐洲當地媒體渲染造成恐慌，排斥亞洲人氣氛濃厚。
- 去看醫生前其實是非常糾結的
- 整個歐洲的口罩都被掃光了

### 2. 股市崩跌與長下影線迷思

- **核心觀點：** 長下影線不必然代表反彈，破線仍需設好停損。
- 多的是長下影線之後繼續崩跌
- 散戶贖回基金迫使機構賣股
"""
    note_file = tmp_path / "EP0001.md"
    note_file.write_text(md_content, encoding="utf-8")

    note = load_note_from_markdown(note_file)
    assert note.metadata.number == 1
    assert note.metadata.display_title == "歐洲疫情與股市崩跌"
    assert note.metadata.date == "2020-02-27"
    assert len(note.chapters) == 2
    assert note.chapters[0].index == 1
    assert note.chapters[0].heading == "歐洲疫情蔓延與排斥亞洲人"
    assert note.chapters[0].takeaway == "歐洲當地媒體渲染造成恐慌，排斥亞洲人氣氛濃厚。"
    assert len(note.chapters[0].excerpts) == 2


def test_topic_quality_auditor(sample_episodes, tmp_path):
    from topic_synthesizer import DEFAULT_TOPICS, TopicGuideSynthesizer, TopicQualityAuditor

    episodes_dir = tmp_path / "episodes"
    topics_dir = tmp_path / "topics"
    episodes_dir.mkdir()
    topics_dir.mkdir()

    # Save mock episodes
    for ep in sample_episodes:
        ep_file = episodes_dir / f"EP{ep.metadata.number:04d}.md"
        ep_file.write_text(ep.render_markdown(mode="slim"), encoding="utf-8")

    synthesizer = TopicGuideSynthesizer()
    synthesizer.synthesize_and_save_all(sample_episodes, topics_dir, DEFAULT_TOPICS)

    auditor = TopicQualityAuditor()
    report = auditor.audit_all_topics(topics_dir=topics_dir, episodes_dir=episodes_dir)

    assert report["total_topics"] == 4
    assert report["defect_count"] == 0
    assert len(report["defects"]) == 0


def test_topic_quality_auditor_detects_defect(sample_episodes, tmp_path):
    from topic_synthesizer import TopicQualityAuditor

    episodes_dir = tmp_path / "episodes"
    topics_dir = tmp_path / "topics"
    episodes_dir.mkdir()
    topics_dir.mkdir()

    # Create a corrupted topic guide with broken link
    bad_md = """---
slug: "broken-topic"
title: "壞掉的專題"
category: "測試"
episodes_count: 1
chapters_count: 1
time_span: "2020-01-01 ~ 2020-01-02"
content_method: "thematic_synthesis"
---

# 壞掉的專題

## 4. 🔗 相關集數索引與引用列表

| [EP9999](../episodes/EP9999.md) | 2020-01-01 | 第 1 章 | 虛構標題 | 虛構觀點 |
"""
    (topics_dir / "broken-topic.md").write_text(bad_md, encoding="utf-8")

    auditor = TopicQualityAuditor()
    report = auditor.audit_all_topics(topics_dir=topics_dir, episodes_dir=episodes_dir)
    assert report["defect_count"] > 0
    assert any("EP9999" in str(d) for d in report["defects"])


def test_cli_topics_subcommand():
    import subprocess
    import sys
    from pathlib import Path

    # Test cli.py topics --list
    res_list = subprocess.run(
        [sys.executable, ".work/cli.py", "topics", "--list"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    assert res_list.returncode == 0
    assert "Gooaye 股癌 跨集數主題專題庫清單" in res_list.stdout
    assert "ai-hardware-and-semiconductor" in res_list.stdout

    # Test cli.py topics --audit
    res_audit = subprocess.run(
        [sys.executable, ".work/cli.py", "topics", "--audit"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    assert res_audit.returncode == 0
    assert "Audit completed" in res_audit.stdout
    assert "100%" in res_audit.stdout or "0" in res_audit.stdout




