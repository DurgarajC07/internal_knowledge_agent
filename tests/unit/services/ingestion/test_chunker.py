from services.ingestion.chunker import chunk_text


def test_chunk_text_empty_returns_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_short_text_single_chunk() -> None:
    text = "hello world " * 10
    chunks = chunk_text(text, chunk_size_tokens=650)
    assert len(chunks) == 1
    assert chunks[0].split() == text.split()


def test_chunk_text_splits_long_text_with_overlap() -> None:
    words = [f"word{i}" for i in range(2000)]
    text = " ".join(words)

    chunks = chunk_text(text, chunk_size_tokens=100, overlap_ratio=0.1)

    assert len(chunks) > 1
    # every chunk after the first shares its opening words with the previous
    # chunk's tail -- that's the overlap.
    first_words = chunks[0].split()
    second_words = chunks[1].split()
    overlap = set(first_words[-5:]) & set(second_words[:5])
    assert overlap, "expected overlapping words between consecutive chunks"


def test_chunk_text_covers_all_words_without_loss() -> None:
    words = [f"tok{i}" for i in range(500)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_size_tokens=50, overlap_ratio=0.1)

    seen: set[str] = set()
    for chunk in chunks:
        seen.update(chunk.split())
    assert seen == set(words)
