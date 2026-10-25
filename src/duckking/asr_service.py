"""Loopback-only offline ASR worker, isolated from the physics event loop and quota."""

import argparse
import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

ENGINE = "sherpa-onnx/SenseVoiceSmall-INT8"
MAX_BYTES = 16000 * 2 * 15


class Recognizer:
    def __init__(self, folder):
        import sherpa_onnx

        self.model = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(folder / "model.int8.onnx"), tokens=str(folder / "tokens.txt"),
            num_threads=1, language="zh", use_itn=True, provider="cpu",
        )

    def __call__(self, pcm):
        import numpy as np

        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        rms = float(np.sqrt(np.mean(samples * samples)))
        if rms < 0.002:
            return {"text": "", "speech": False}
        stream = self.model.create_stream()
        stream.accept_waveform(16000, samples)
        self.model.decode_stream(stream)
        # SenseVoice does not expose a calibrated confidence probability here.
        return {"text": stream.result.text[:2000], "speech": True}


def create_asr_app(folder: Path | None = None, recognize=None):
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="offline-asr")
    pending = 0

    @asynccontextmanager
    async def lifespan(app):
        nonlocal recognize
        if recognize is None:
            recognize = await asyncio.to_thread(Recognizer, folder)
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health():
        return {"ready": recognize is not None, "engine": ENGINE, "pending": pending}

    @app.post("/recognize")
    async def decode(request: Request):
        nonlocal pending
        if request.headers.get("content-type", "").split(";")[0] != "application/octet-stream":
            raise HTTPException(415, "Expected PCM16 audio")
        pcm = bytearray()
        async for chunk in request.stream():
            if len(pcm) + len(chunk) > MAX_BYTES:
                raise HTTPException(413, "Audio exceeds 15 seconds")
            pcm.extend(chunk)
        if not pcm or len(pcm) % 1920:
            raise HTTPException(400, "Expected complete 16 kHz mono PCM16 60 ms frames")
        if recognize is None or pending >= 2:
            raise HTTPException(503, "Offline recognizer is busy or unavailable")
        pending += 1
        start = time.monotonic()
        future = asyncio.get_running_loop().run_in_executor(executor, recognize, bytes(pcm))

        def release(_):
            nonlocal pending
            pending -= 1

        future.add_done_callback(release)
        try:
            # A disconnected caller cannot release admission while native inference
            # still runs, or create an unbounded backlog of abandoned work.
            result = await asyncio.wait_for(asyncio.shield(future), 8)
        except TimeoutError:
            raise HTTPException(504, "Offline recognition timed out") from None
        except Exception:
            raise HTTPException(503, "Offline recognition failed") from None
        return {**result, "engine": ENGINE, "asr_ms": round((time.monotonic() - start) * 1000)}

    return app


def main():
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--model-dir", type=Path, default=Path(
        os.getenv("DUCKKING_ASR_MODEL_DIR", "external/asr")
    ))
    args = parser.parse_args()
    uvicorn.run(create_asr_app(args.model_dir), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
