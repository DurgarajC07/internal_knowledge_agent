from __future__ import annotations


class TextParser:
    def parse(self, raw_bytes: bytes, filename: str) -> str:
        return raw_bytes.decode("utf-8", errors="replace")
