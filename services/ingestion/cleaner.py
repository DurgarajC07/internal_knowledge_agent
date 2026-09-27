"""Strips boilerplate/whitespace noise before chunking (Plan.md SS1.2)."""

from __future__ import annotations

import re

_MULTI_BLANK_LINES = re.compile(r"\n{3,}")
_TRAILING_WHITESPACE = re.compile(r"[ \t]+\n")
_FORM_FEED_AND_CR = re.compile(r"[\f\r]")


def clean_text(text: str) -> str:
    text = _FORM_FEED_AND_CR.sub("", text)
    text = _TRAILING_WHITESPACE.sub("\n", text)
    text = _MULTI_BLANK_LINES.sub("\n\n", text)
    return text.strip()
