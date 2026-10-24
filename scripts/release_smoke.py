"""Check an actual release, its browser assets, and live local protocols. No cloud calls."""

import argparse
import asyncio
import json
import re
from urllib.parse import urljoin, urlsplit

import httpx
import websockets


async def verify(base, commit):
    base = base.rstrip("/") + "/"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(urljoin(base, "api/health"))
        response.raise_for_status()
        assert response.json()["release"]["commit"] == commit, "Wrong running release"
        for page in ["", "scenarios.html", "statistics.html", "deploys.html"]:
            response = await client.get(urljoin(base, page))
            response.raise_for_status()
            assert "DuckKing" in response.text and "<html" in response.text
            for asset in re.findall(r'(?:src|href)="([^\"]+\.(?:js|css))"', response.text):
                url = urljoin(urljoin(base, page), asset)
                assert url.startswith(base), "An asset escaped the deployment prefix"
                (await client.get(url)).raise_for_status()
        (await client.get(urljoin(base, "capture-worklet.js"))).raise_for_status()
        for endpoint in ["ws", "scene-ws", "voice"]:
            url = urlsplit(urljoin(base, endpoint))
            scheme = "wss" if url.scheme == "https" else "ws"
            async with websockets.connect(
                url._replace(scheme=scheme).geturl(),
                origin=f"{url.scheme}://{url.netloc}",
                open_timeout=15,
            ) as socket:
                message = json.loads(await asyncio.wait_for(socket.recv(), timeout=15))
                assert message["type"] in {"state", "not_started", "voice_status"}
                if endpoint == "scene-ws":
                    await socket.send("next")
                    await asyncio.wait_for(socket.recv(), timeout=5)
        action = (await client.post(urljoin(base, "api/actions"), json={"name": "stop"})).json()
        for _ in range(30):
            result = (await client.get(urljoin(base, "api/actions/" + action["id"]))).json()
            if result["status"] != "running":
                break
            await asyncio.sleep(0.1)
        assert result["status"] == "completed"
    print(
        "Release, prefixed assets, state/voice handshakes and bounded stop verified; "
        "cloud voice not tested."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    asyncio.run(verify(args.url, args.commit))
