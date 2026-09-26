#!/usr/bin/env python3
"""Import reviewed ASR output structure with official metadata and original audio.

Does not assert human transcription accuracy or publish the knowledge base.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '.work'))
from asr_importer import build_asr_snapshot
from cold_transcript_exporter import sync_cold_transcript
from episode_acquirer import SOUNDON_FEED_URL, YOUTUBE_FEED_URL, parse_duration, parse_episode_number
from episode_synthesizer import EpisodeNoteSynthesizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--episodes', type=int, nargs='+', required=True)
    parser.add_argument('--audio-dir', type=Path, required=True)
    parser.add_argument('--asr-dir', type=Path, required=True)
    parser.add_argument('--force', action='store_true', help='Replace changed snapshots explicitly')
    args = parser.parse_args()
    from opencc import OpenCC
    converter = OpenCC('s2twp')
    metadata = {row['number']: row for row in json.loads(args.metadata.read_text())}
    repository = EpisodeNoteSynthesizer().source_repository
    for number in args.episodes:
        official = metadata[number]
        path = args.asr_dir / f'EP{number:04d}.json'
        result = json.loads(path.read_text())
        audio = args.audio_dir / f'EP{number:04d}.mp3'
        with audio.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != result['audio_sha256']:
            raise ValueError(f'EP{number}: audio differs from ASR input')
        date = datetime.fromisoformat(official['published_at'].replace('Z', '+00:00')).date()
        if (parse_episode_number(official['youtube_title']) != number
                or parse_episode_number(official['soundon_title']) != number
                or parsedate_to_datetime(official['soundon_date']).date() != date):
            raise ValueError(f'EP{number}: official identity/date mismatch')
        duration = parse_duration(official['duration'])
        if abs(duration - result['audio_duration_seconds']) > 2:
            raise ValueError(f'EP{number}: audio duration differs from official metadata')
        segments = result['segments']
        if not segments or segments[0]['start'] > 30 or duration - segments[-1]['end'] > 30:
            raise ValueError(f'EP{number}: ASR does not cover opening/ending')
        previous = 0
        for segment in segments:
            start, end = segment['start'], segment['end']
            if start < previous - 0.1 or end < start or end > duration + 2:
                raise ValueError(f'EP{number}: invalid segment timestamps')
            previous = end
        # Original ASR wording is preserved; line breaks retain recognizer segments.
        transcript_path = args.asr_dir / f'EP{number:04d}.md'
        text = f'# EP{number}｜{official["youtube_title"]}\n\n'
        text += '\n'.join(converter.convert(segment['text'].strip()) for segment in segments) + '\n'
        transcript_path.write_text(text)
        snapshot = build_asr_snapshot(
            number=number, youtube_id=official['youtube_id'],
            youtube_title=official['youtube_title'], published_at=official['published_at'],
            duration_seconds=duration, transcript_path=transcript_path,
            audio_path=audio, audio_url=official['audio_url'],
            youtube_metadata_url=YOUTUBE_FEED_URL, duration_metadata_url=SOUNDON_FEED_URL,
            engine=result['engine'], model=result['model'],
            fetched_at=datetime.now(timezone.utc).isoformat(),
            summary='官方節目音訊自動語音辨識；主題與引述依完整轉錄文字抽取。',
            extra_provenance={
                'model_revision': result['model_revision'],
                'transcribed_at': result['transcribed_at'],
                'review_status': result['review_status'],
                'asr_result_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'asr_result_path': str(path.resolve().relative_to(ROOT)),
                'normalization': 'opencc-python-reimplemented 0.1.7 s2twp; original text retained in ASR JSON',
                'content_start_line': str(official['content_start_segment'] + 3),
            },
        )
        status = repository.commit(snapshot, force=args.force)
        verification = repository.verify(number)
        if not verification.is_valid:
            raise ValueError(verification.defects)
        sync_cold_transcript(number, repository, ROOT / 'transcripts')
        print(f'EP{number}: {status}; {len(segments)} segments; source and cold archive verified', flush=True)


if __name__ == '__main__':
    main()
