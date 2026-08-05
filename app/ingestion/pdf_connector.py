"""
PDF ingestion connector. v1 handles digital (text-layer) PDFs only --
OCR is explicitly deferred (architecture doc, Section 3 / non-goals).

Two distinct failure modes, deliberately different exceptions so the
caller (and the audit trail) can tell them apart:

- CorruptedPdfError: the file couldn't be parsed as a PDF at all
  (truncated, zero-byte, not actually a PDF).
- UnextractablePdfError: it parsed fine, but has no text layer --
  almost always a scanned document. OCR would fix this; it's just not
  in scope yet.

Both are HTTP 422 at the API layer (see app/api/ingestion.py), never a
raw 500 -- these are expected, recoverable-by-the-user failure modes,
not bugs.
"""
from pypdf import PdfReader


class PdfIngestionError(Exception):
    """Base class for expected PDF ingestion failures -- always mapped to HTTP 422."""


class CorruptedPdfError(PdfIngestionError):
    """The file could not be parsed as a valid PDF at all."""


class UnextractablePdfError(PdfIngestionError):
    """Parsed fine, but no text layer -- likely scanned; OCR not in v1 scope."""


def extract_pdf_text(file_path: str) -> str:
    try:
        reader = PdfReader(file_path)
        num_pages = len(reader.pages)
    except Exception as e:
        raise CorruptedPdfError(f"Could not parse {file_path} as a PDF: {e}") from e

    if num_pages == 0:
        raise UnextractablePdfError(
            f"{file_path} has zero pages -- nothing to extract."
        )

    pages_text = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            # One malformed page shouldn't fail the whole document --
            # skip it and keep going with whatever pages do extract.
            text = ""
        pages_text.append(text)

    full_text = "\n".join(pages_text).strip()
    if not full_text:
        raise UnextractablePdfError(
            f"No extractable text in {file_path} -- likely scanned; OCR is not in v1 scope."
        )
    return full_text
