"""
Chunking service. Simple, dependency-light token-window chunker for v1.
Structure-aware chunking (respecting headers/code blocks) is a natural
upgrade once Month 1 basics are proven out -- not needed to ship v1.
"""
from app.core.config import settings


def _approx_tokenize(text: str) -> list[str]:
    # Whitespace tokenization is a rough but adequate proxy for token count in v1.
    return text.split()


def chunk_text(text: str, source_ref: str = "") -> list[str]:
    tokens = _approx_tokenize(text)
    size = settings.chunk_size_tokens
    overlap = settings.chunk_overlap_tokens

    if len(tokens) <= size:
        return [text.strip()] if text.strip() else []

    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + size, len(tokens))
        chunk = " ".join(tokens[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end == len(tokens):
            break
        start = end - overlap  # slide with overlap

    return chunks
