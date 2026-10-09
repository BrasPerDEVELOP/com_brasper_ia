"""Adversarial stream and channel metadata tests, without external requests."""
import asyncio
from unittest.mock import patch
import httpx
from core import audio_adapter, media_limits, whatsapp


def run():
    class Chunks(httpx.AsyncByteStream):
        def __init__(self): self.read = 0
        async def __aiter__(self):
            for chunk in [b"12", b"34", b"56", b"78"]:
                self.read += 1
                yield chunk

    async def check_streams():
        chunks = Chunks()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, stream=chunks))) as client:
            try: await media_limits.download(client, "https://example.invalid/synthetic", max_bytes=5)
            except media_limits.TooLarge: pass
            else: raise AssertionError("chunked content bypassed limit")
        assert chunks.read == 3, "must stop without reading the remaining attachment"
        for declared in ["999", "-1", "invalid"]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, headers={"Content-Length": declared}, content=b"x"))) as client:
                try: await media_limits.download(client, "https://example.invalid/synthetic", max_bytes=5)
                except ValueError: pass
                else: raise AssertionError("invalid declared length accepted")
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"12345", headers={"Content-Type": "image/png"}))) as client:
            assert await media_limits.download(client, "https://example.invalid/synthetic", max_bytes=5) == (b"12345", "image/png")

    asyncio.run(check_streams())
    with patch.object(audio_adapter, "_transcribe_openai") as provider:
        assert not asyncio.run(audio_adapter.transcribe_bytes({}, b"", "audio/ogg"))["ok"]
        assert not asyncio.run(audio_adapter.transcribe_bytes({}, b"fake html", "text/html"))["ok"]
        assert not asyncio.run(audio_adapter.transcribe_bytes({}, b"x" * (media_limits.MAX_BYTES + 1), "audio/ogg"))["ok"]
        assert not provider.called

    async def metadata(req):
        requests.append(str(req.url))
        return httpx.Response(200, json={"url": "https://attacker.invalid/steal-token", "mime_type": "image/png"})
    requests = []
    factory = httpx.AsyncClient
    with patch.object(whatsapp.httpx, "AsyncClient", side_effect=lambda **kw: factory(transport=httpx.MockTransport(metadata), **kw)):
        assert asyncio.run(whatsapp.download_media("synthetic", connection={"token": "test-only", "phone_number_id": "synthetic"})) == (None, None)
    assert len(requests) == 1 and "attacker" not in requests[0]
