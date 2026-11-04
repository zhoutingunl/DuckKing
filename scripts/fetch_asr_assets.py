"""Fetch the pinned upstream SenseVoiceSmall INT8 conversion, never a moving model."""

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{NAME}.tar.bz2"
SHA256 = "7d1efa2138a65b0b488df37f8b89e3d91a60676e416f515b952358d83dfd347e"
# Files are verified on every build/install, not just the first download.
CHECKSUMS = {
    "model.int8.onnx": "c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51",
    "tokens.txt": "f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc",
    "README.md": "763991a00edaea534ab36bf1b7cf89e61e911666dcfabbba71f91f9f7c593a63",
    "LICENSE": "221c6df10b0931a5629adad671ea48fb7747e034c414b6d2bfa275bc3dd4ea17",
}
ROOT = Path(__file__).resolve().parents[1]


def valid(folder):
    return bool(CHECKSUMS) and all(
        (folder / name).is_file()
        and hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
        for name, digest in CHECKSUMS.items()
    )


def fetch(folder):
    if valid(folder):
        return
    folder.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="duckking-asr-", dir=folder.parent) as temporary:
        temp = Path(temporary)
        archive = temp / "model.tar.bz2"
        with urllib.request.urlopen(URL, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
            raise ValueError("Offline ASR archive checksum mismatch")
        with tarfile.open(archive) as bundle:
            bundle.extractall(temp, filter="data")
        source = temp / NAME
        if not valid(source):
            raise ValueError("Offline ASR file checksum mismatch")
        folder.mkdir(exist_ok=True)
        for name in CHECKSUMS:
            shutil.copyfile(source / name, folder / name)
        shutil.copyfile(
            ROOT / "docs/licenses/SenseVoice-MODEL_LICENSE.txt", folder / "MODEL_LICENSE"
        )
        (folder / "source.json").write_text(
            json.dumps(
                {
                    "model": "SenseVoiceSmall INT8",
                    "author": "FunAudioLLM / Alibaba Group",
                    "conversion": "k2-fsa/sherpa-onnx",
                    "archive": URL,
                    "sha256": SHA256,
                },
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    fetch(Path(os.getenv("DUCKKING_ASR_MODEL_DIR", str(ROOT / "external/asr"))))
    print("Pinned offline ASR assets verified")
