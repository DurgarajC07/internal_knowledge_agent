from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from packages.core.exceptions import IngestionError

_MAX_PAGES = 2000  # defensive cap — malicious/corrupt PDFs must not hang ingestion


class PdfParser:
    def parse(self, raw_bytes: bytes, filename: str) -> str:
        try:
            reader = PdfReader(io.BytesIO(raw_bytes))
        except PdfReadError as exc:
            raise IngestionError(f"Failed to open PDF '{filename}': {exc}") from exc

        if len(reader.pages) > _MAX_PAGES:
            raise IngestionError(f"PDF '{filename}' exceeds the {_MAX_PAGES}-page safety cap")

        pages_text: list[str] = []
        for page in reader.pages:
            try:
                pages_text.append(page.extract_text() or "")
            except PdfReadError:
                continue
        return "\n".join(pages_text)
