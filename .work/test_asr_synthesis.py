from dataclasses import replace
from unittest.mock import Mock

import pytest

from episode_synthesizer import EpisodeNoteSynthesizer
from test_cold_transcript_exporter import make_sample_metadata


def make_synthesizer(transcription):
    metadata = replace(make_sample_metadata(), summary="", transcription=transcription)
    lines = ["# EP1", "本集節目由保健品贊助", "保健品促銷介紹內容"]
    lines.extend(f"第{n}段市場分析指出資金管理需要耐心觀察產業變化避免短期波動影響投資策略" for n in range(100))
    text = "\n".join(lines)
    repository = Mock()
    repository.get_metadata.return_value = metadata
    repository.load_transcript.return_value = text
    return EpisodeNoteSynthesizer(source_repository=repository), text


def test_asr_evidence_covers_unpunctuated_content_and_excludes_explicit_ad_block():
    synthesizer, original = make_synthesizer({"model": "whisper", "content_start_line": "4"})
    evidence = synthesizer.extract_evidence(1)
    excerpts = " ".join(e for chapter in evidence for e in chapter.excerpts)
    assert len(evidence) >= 6
    assert "第9" in excerpts
    assert "保健品" not in excerpts
    assert synthesizer.load_transcript(1) == original


def test_legacy_input_is_passed_to_extraction_unchanged():
    synthesizer, original = make_synthesizer({})
    synthesizer.evidence_extractor = Mock()
    synthesizer.extract_evidence(1)
    synthesizer.evidence_extractor.extract.assert_called_once_with(original, summary="")


@pytest.mark.parametrize("start", ["0", "999", "bad", "-1"])
def test_asr_invalid_explicit_boundary_fails_loudly(start):
    synthesizer, _ = make_synthesizer({"model": "whisper", "content_start_line": start})
    with pytest.raises(ValueError, match="content_start_line"):
        synthesizer.extract_evidence(1)


def test_asr_preparation_preserves_words_and_explicit_sponsor_separator():
    import re
    from transcript_processor import TranscriptSanitizer

    metadata = replace(make_sample_metadata(), transcription={"model": "whisper"})
    content = "\n".join("市場資金輪動應觀察產業需求及庫存變化再決定投資配置" for _ in range(10))
    raw = "# EP1\n本集節目由保健品牌贊助\n保健產品介紹\n---\n" + content
    prepared = EpisodeNoteSynthesizer._prepare_asr_transcript(raw, metadata)
    cleaned = TranscriptSanitizer.clean(prepared)
    assert "保健" not in cleaned
    assert re.sub(r"[\s。]", "", cleaned) == re.sub(r"\s", "", content)
