"""Bounded streaming for private channel attachments."""
MAX_BYTES = 20 * 1024 * 1024


class TooLarge(ValueError):
    pass


async def download(client, url, *, headers=None, max_bytes=MAX_BYTES):
    async with client.stream("GET", url, headers=headers) as response:
        if response.status_code != 200:
            return None, None
        declared = response.headers.get("content-length")
        if declared:
            try:
                if int(declared) < 0 or int(declared) > max_bytes:
                    raise TooLarge("Attachment exceeds allowed size")
            except ValueError as exc:
                if isinstance(exc, TooLarge):
                    raise
                raise ValueError("Invalid content length") from exc
        result = bytearray()
        async for chunk in response.aiter_bytes():
            if len(result) + len(chunk) > max_bytes:
                raise TooLarge("Attachment exceeds allowed size")
            result.extend(chunk)
        return bytes(result), response.headers.get("content-type") or "application/octet-stream"
