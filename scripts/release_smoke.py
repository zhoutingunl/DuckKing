"""Check an actual release, its browser assets, and live local protocols. No cloud calls."""

import argparse
import asyncio
import json
import re
import struct
from contextlib import asynccontextmanager
from urllib.parse import urljoin, urlsplit

import httpx
import websockets


class HTTPSChannel:
    def __init__(self, client, url):
        self.client, self.url = client, url
        self.sequence, self.pending = 0, []

    async def recv(self):
        while not self.pending:
            response = await self.client.get(self.url)
            response.raise_for_status()
            packet = response.json()
            self.pending.extend(packet['frames'])
            assert self.pending or not packet['closed'], 'Channel closed'
        frame = self.pending.pop(0)
        assert not frame['binary'], 'Expected a JSON status'
        return frame['data']

    async def send(self, data):
        response = await self.client.post(self.url, json={
            'sequence': self.sequence, 'frames': [{'binary': False, 'data': data}]})
        response.raise_for_status()
        self.sequence += 1
        assert response.json()['sequence'] == self.sequence


@asynccontextmanager
async def connection(client, base, endpoint, transport):
    if transport == 'https-poll':
        response = await client.post(
            urljoin(base, '_gateway/channels'), json={'endpoint': endpoint})
        response.raise_for_status()
        channel = HTTPSChannel(client, urljoin(base, '_gateway/channels/' + response.json()['id']))
        try:
            yield channel
        finally:
            response = await client.delete(channel.url)
            # A terminal status (e.g. scene voice before loading a scene) may
            # already have drained and removed the gateway channel on GET.
            if response.status_code != 410:
                response.raise_for_status()
    else:
        url = urlsplit(urljoin(base, endpoint))
        scheme = 'wss' if url.scheme == 'https' else 'ws'
        async with websockets.connect(url._replace(scheme=scheme).geturl(),
                origin=f'{url.scheme}://{url.netloc}', open_timeout=15) as socket:
            yield socket


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
        manifest = await client.get(urljoin(base, "api/models/microduck/manifest"), timeout=60)
        manifest.raise_for_status()
        info = manifest.json()
        assert re.fullmatch(r"[a-f0-9]{64}", info["version"])
        model = await client.get(
            urljoin(base, f"api/models/microduck/assets/{info['version']}.dkm.gz"), timeout=60
        )
        model.raise_for_status()
        assert model.headers["content-encoding"] == "gzip"
        assert model.content[:4] == b"DKM1" and len(model.content) == info["decoded_bytes"]
        size = struct.unpack_from("<I", model.content, 4)[0]
        metadata = json.loads(model.content[8:8 + size])
        assert metadata["source"] == "official_microduck_visuals"
        assert metadata["physics"] is False
        assert metadata["meshes"], "Missing official visual meshes"
        capabilities = await client.get(urljoin(base, '_gateway/capabilities'))
        transport = 'websocket'
        if capabilities.status_code != 404:
            capabilities.raise_for_status()
            transport = capabilities.json()['transport']
            assert transport in {'https-poll', 'websocket'}
        for endpoint in ["ws", "scene-ws", "voice", "scene-voice"]:
            async with connection(client, base, endpoint, transport) as socket:
                await socket.send(json.dumps({"type": "join_room", "room": "1"}))
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
        f"Release, prefixed assets, {transport} state/voice handshakes and bounded stop verified; "
        "cloud voice not tested."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    asyncio.run(verify(args.url, args.commit))
