# Test Fixtures

Committed binary files used by `tests/test_pdf_connector.py`. These are pre-generated, not created at test time -- no extra dependency needed to run the tests, only to regenerate them if you need to.

- `corrupted.pdf` — garbage bytes, not a valid PDF. Exercises `CorruptedPdfError`.
- `zero_byte.pdf` — a genuinely empty (0-byte) file. Also exercises `CorruptedPdfError`.
- `blank_no_text.pdf` — a valid, parseable PDF with a blank page and no text content. Simulates a scanned document (parses fine, nothing to extract). Exercises `UnextractablePdfError`.
- `valid_with_text.pdf` — a valid PDF with real extractable text. Positive control, confirms normal ingestion still works.

To regenerate (requires `pypdf` + `reportlab`, not otherwise a project dependency):

```python
from pypdf import PdfWriter
from reportlab.pdfgen import canvas
import io

with open("corrupted.pdf", "wb") as f:
    f.write(b"this is not a real PDF file, just garbage bytes %%%***")

open("zero_byte.pdf", "wb").close()

writer = PdfWriter()
writer.add_blank_page(width=200, height=200)
with open("blank_no_text.pdf", "wb") as f:
    writer.write(f)

buf = io.BytesIO()
c = canvas.Canvas(buf, pagesize=(200, 200))
c.drawString(20, 100, "This is a real sentence for ingestion testing.")
c.save()
with open("valid_with_text.pdf", "wb") as f:
    f.write(buf.getvalue())
```
