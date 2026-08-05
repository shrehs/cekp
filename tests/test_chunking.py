from app.services.chunking import chunk_text


def test_short_text_returns_single_chunk():
    text = "This is a short piece of text."
    result = chunk_text(text)
    assert len(result) == 1
    assert result[0] == text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_long_text_splits_into_multiple_overlapping_chunks():
    words = ["word"] * 1000
    text = " ".join(words)
    result = chunk_text(text)
    assert len(result) > 1
    # every chunk should be non-empty
    assert all(c.strip() for c in result)
