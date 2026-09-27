import io

import pytest
from pypdf import PdfWriter

from packages.core.exceptions import IngestionError
from services.ingestion.parsers.pdf_parser import PdfParser


def _make_pdf_bytes(page_count: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_parse_returns_a_string_for_a_valid_pdf() -> None:
    parser = PdfParser()
    text = parser.parse(_make_pdf_bytes(page_count=2), "sample.pdf")
    assert isinstance(text, str)


def test_parse_raises_ingestion_error_for_corrupt_bytes() -> None:
    parser = PdfParser()
    with pytest.raises(IngestionError):
        parser.parse(b"this is not a pdf", "corrupt.pdf")
