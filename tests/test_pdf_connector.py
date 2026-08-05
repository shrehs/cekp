"""
Tests for the PDF ingestion connector, using real fixture files (see
tests/fixtures/) rather than mocks -- pypdf is a real dependency and
its actual error behavior on malformed input is exactly what we need
to verify, not what we assume it does.
"""
import os

import pytest

from app.ingestion.pdf_connector import (
    CorruptedPdfError,
    UnextractablePdfError,
    extract_pdf_text,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_corrupted_pdf_raises_corrupted_error_not_a_raw_exception():
    with pytest.raises(CorruptedPdfError):
        extract_pdf_text(os.path.join(FIXTURES, "corrupted.pdf"))


def test_zero_byte_file_raises_corrupted_error():
    with pytest.raises(CorruptedPdfError):
        extract_pdf_text(os.path.join(FIXTURES, "zero_byte.pdf"))


def test_valid_pdf_with_no_text_raises_unextractable_error():
    """Simulates a scanned document: parses fine, but no text layer."""
    with pytest.raises(UnextractablePdfError):
        extract_pdf_text(os.path.join(FIXTURES, "blank_no_text.pdf"))


def test_valid_pdf_with_real_text_extracts_successfully():
    text = extract_pdf_text(os.path.join(FIXTURES, "valid_with_text.pdf"))
    assert "real sentence for ingestion testing" in text


def test_both_error_types_share_a_common_base_for_the_api_layer():
    """
    app/api/ingestion.py catches PdfIngestionError once to map both
    failure modes to HTTP 422 -- confirm both actually subclass it.
    """
    from app.ingestion.pdf_connector import PdfIngestionError

    assert issubclass(CorruptedPdfError, PdfIngestionError)
    assert issubclass(UnextractablePdfError, PdfIngestionError)
