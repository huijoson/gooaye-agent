#!/usr/bin/env python3
"""Transcribe local episode audio with MLX Whisper; retain timed ASR evidence.

Requires optional mlx-whisper and ffmpeg. Does not publish or import snapshots.
"""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio', type=Path, nargs='+')
    parser.add_argument('--model', default='mlx-community/whisper-large-v3-turbo')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    import mlx_whisper
    from huggingface_hub import snapshot_download
    model_path = snapshot_download(args.model, local_files_only=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for audio in args.audio:
        destination = args.output_dir / (audio.stem + '.json')
        digest = hashlib.sha256(audio.read_bytes()).hexdigest()
        if destination.exists():
            prior = json.loads(destination.read_text())
            if prior['audio_sha256'] != digest or prior['model'] != args.model:
                raise ValueError(f'Existing ASR evidence conflicts: {destination}')
            print(f'{audio.stem}: verified existing ASR result', flush=True)
            continue
        duration = float(subprocess.check_output([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(audio),
        ]))
        print(f'{audio.stem}: transcribing {duration:.1f} seconds', flush=True)
        result = mlx_whisper.transcribe(
            str(audio), path_or_hf_repo=model_path, language='zh', task='transcribe',
            verbose=None, temperature=0.0, condition_on_previous_text=False,
            initial_prompt='以下是台灣 Podcast 股癌的繁體中文逐字稿，包含投資與生活話題。',
        )
        if not result['segments'] or len(result['text'].encode()) < 1000:
            raise ValueError(f'Incomplete ASR output: {audio}')
        result.update(engine='mlx-whisper', model=args.model,
                      model_revision=Path(model_path).name, audio_sha256=digest,
                      audio_duration_seconds=duration,
                      transcribed_at=datetime.now(timezone.utc).isoformat(),
                      review_status='machine_transcribed_not_manually_verified')
        temporary = destination.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        temporary.rename(destination)
        print(f'{audio.stem}: saved {len(result["segments"])} segments to {destination}', flush=True)


if __name__ == '__main__':
    main()
