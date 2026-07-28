from __future__ import annotations

import base64
import mimetypes
import re
from collections.abc import Callable

_SRC_RE = re.compile(r'(?P<prefix>src=["\'])(?P<filename>[^"\']+)(?P<suffix>["\'])', re.IGNORECASE)


def embed_anki_media(html: str, retrieve: Callable[[str], bytes | None]) -> str:
    """Replace Anki-local image references with self-contained data URLs."""
    def replace(match: re.Match[str]) -> str:
        filename = match.group("filename")
        if filename.startswith(("data:", "http://", "https://")):
            return match.group(0)
        content = retrieve(filename)
        if content is None:
            return match.group(0)
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        encoded = base64.b64encode(content).decode("ascii")
        return f'{match.group("prefix")}data:{mime};base64,{encoded}{match.group("suffix")}'

    return _SRC_RE.sub(replace, html or "")
