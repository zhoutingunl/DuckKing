"""Fixed loopback worker client; no URL, model, or device identity from a browser."""

import time

import httpx

ASR_URL = "http://127.0.0.1:8767"


async def availability():
    try:
        async with httpx.AsyncClient(timeout=0.6, trust_env=False) as client:
            response = await client.get(ASR_URL + "/health")
            response.raise_for_status()
            value = response.json()
            return {"available": isinstance(value, dict) and value.get("ready") is True,
                    "engine": "sherpa-onnx/SenseVoiceSmall-INT8"}
    except (httpx.HTTPError, ValueError):
        return {"available": False, "engine": "sherpa-onnx/SenseVoiceSmall-INT8"}


async def recognize(pcm):
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
        response = await client.post(
            ASR_URL + "/recognize", content=pcm,
            headers={"Content-Type": "application/octet-stream"},
        )
        response.raise_for_status()
        result = response.json()
    if (not isinstance(result, dict) or not isinstance(result.get("text"), str)
            or len(result["text"]) > 2000 or not isinstance(result.get("speech"), bool)):
        raise ValueError("Invalid offline recognition result")
    return {"text": result["text"], "speech": result.get("speech") is True,
            "asr_ms": round((time.monotonic() - started) * 1000)}
