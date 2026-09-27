from __future__ import annotations

from pathlib import PurePosixPath

from packages.core.exceptions import UnsupportedDocumentTypeError
from services.ingestion.parsers.base import DocumentParser
from services.ingestion.parsers.pdf_parser import PdfParser
from services.ingestion.parsers.text_parser import TextParser

_PARSERS_BY_EXTENSION: dict[str, DocumentParser] = {
    ".pdf": PdfParser(),
    ".txt": TextParser(),
    ".md": TextParser(),
}


def get_parser_for(filename: str) -> DocumentParser:
    extension = PurePosixPath(filename).suffix.lower()
    parser = _PARSERS_BY_EXTENSION.get(extension)
    if parser is None:
        raise UnsupportedDocumentTypeError(f"No parser registered for extension '{extension}'")
    return parser
