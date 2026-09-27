from services.ingestion.cleaner import clean_text


def test_clean_text_collapses_multiple_blank_lines() -> None:
    assert clean_text("a\n\n\n\n\nb") == "a\n\nb"


def test_clean_text_strips_trailing_whitespace_per_line() -> None:
    assert clean_text("a   \nb\t\n") == "a\nb"


def test_clean_text_strips_leading_and_trailing_overall_whitespace() -> None:
    assert clean_text("  \n hello \n  ") == "hello"
