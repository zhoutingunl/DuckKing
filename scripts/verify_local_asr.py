"""Real offline inference against disclosed synthetic regression recordings."""

import json
import time
import wave
from pathlib import Path

from duckking.asr_service import Recognizer
from duckking.local_commands import parse_commands

ROOT = Path(__file__).resolve().parents[1]


def verify(folder=None):
    start = time.monotonic()
    recognize = Recognizer(folder or ROOT / 'external/asr')
    loaded_ms = round((time.monotonic() - start) * 1000)
    rows = []
    for name, expected in [('local-command', ['walk', 'turn_left', 'turn_right']),
                           ('negated-command', [])]:
        with wave.open(str(ROOT / f'tests/audio/{name}.wav')) as audio:
            assert audio.getframerate() == 16000
            assert audio.getnchannels() == 1 and audio.getsampwidth() == 2
            pcm = audio.readframes(audio.getnframes())
        start = time.monotonic()
        result = recognize(pcm)
        actions = [a.name for a in parse_commands(result['text'], physical=False).actions]
        row = dict(fixture=name, text=result['text'], actions=actions,
                   asr_ms=round((time.monotonic() - start) * 1000))
        rows.append(row)
        assert actions == expected, row
    assert recognize(bytes(1920)) == {'text': '', 'speech': False}
    return dict(engine='sherpa-onnx/SenseVoiceSmall-INT8', synthetic_fixtures=True,
                load_ms=loaded_ms, results=rows)


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False))
