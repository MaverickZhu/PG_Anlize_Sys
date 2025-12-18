"""
Batch extract text from PDFs under KN/ into KN/_text/.

Usage (PowerShell):
  python scripts/extract_kn_pdfs.py
  python scripts/extract_kn_pdfs.py --kn-dir KN --out-dir KN/_text --overwrite
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None


@dataclass(frozen=True)
class ExtractResult:
    pdf: str
    txt: str
    pages: int
    extracted_chars: int
    empty_pages: int
    error: str | None = None


def _safe_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", errors="replace")


def extract_pdf_to_text(pdf_path: Path) -> tuple[str, int, int]:
    """
    Returns: (text, extracted_chars, empty_pages)
    """
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    extracted_chars = 0
    empty_pages = 0

    for i, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        page_text = page_text.replace("\x00", "")
        if not page_text.strip():
            empty_pages += 1

        extracted_chars += len(page_text)
        parts.append(f"\n\n===== PAGE {i} =====\n\n{page_text}")

    header = f"PDF: {pdf_path.name}\nExtractedAt: {datetime.now().isoformat(timespec='seconds')}\n"
    return header + "".join(parts), extracted_chars, empty_pages


def extract_pdf_to_text_pymupdf(pdf_path: Path) -> tuple[str, int, int]:
    """
    Fallback extractor for PDFs where pypdf returns empty text.
    Returns: (text, extracted_chars, empty_pages)
    """
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is not available. Install pymupdf.")

    doc = fitz.open(str(pdf_path))
    parts: list[str] = []
    extracted_chars = 0
    empty_pages = 0

    for i in range(doc.page_count):
        page = doc.load_page(i)
        page_text = page.get_text("text") or ""
        page_text = page_text.replace("\x00", "")
        if not page_text.strip():
            empty_pages += 1

        extracted_chars += len(page_text)
        parts.append(f"\n\n===== PAGE {i + 1} =====\n\n{page_text}")

    header = f"PDF: {pdf_path.name}\nExtractedAt: {datetime.now().isoformat(timespec='seconds')}\nExtractor: pymupdf\n"
    return header + "".join(parts), extracted_chars, empty_pages


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract KN PDFs to text files.")
    parser.add_argument("--kn-dir", default="KN", help="Directory containing PDF files (default: KN)")
    parser.add_argument("--out-dir", default="KN/_text", help="Output directory for extracted .txt (default: KN/_text)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing .txt files")
    args = parser.parse_args()

    kn_dir = Path(args.kn_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(kn_dir.glob("*.pdf"))
    index: dict[str, object] = {
        "kn_dir": str(kn_dir),
        "out_dir": str(out_dir),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(pdfs),
        "items": [],
    }

    for pdf in pdfs:
        txt_path = out_dir / f"{pdf.stem}.txt"
        if txt_path.exists() and not args.overwrite:
            try:
                reader = PdfReader(str(pdf))
                pages = len(reader.pages)
            except Exception:
                pages = -1
            item = ExtractResult(
                pdf=str(pdf),
                txt=str(txt_path),
                pages=pages,
                extracted_chars=0,
                empty_pages=0,
                error=None,
            )
            index["items"].append(asdict(item) | {"skipped": True})
            continue

        try:
            reader = PdfReader(str(pdf))
            pages = len(reader.pages)
            text, extracted_chars, empty_pages = extract_pdf_to_text(pdf)
            if extracted_chars == 0 and pages > 0:
                # fallback for image-like / complex PDFs
                text, extracted_chars, empty_pages = extract_pdf_to_text_pymupdf(pdf)
            _safe_write_text(txt_path, text)
            item = ExtractResult(
                pdf=str(pdf),
                txt=str(txt_path),
                pages=pages,
                extracted_chars=extracted_chars,
                empty_pages=empty_pages,
                error=None,
            )
            index["items"].append(asdict(item) | {"skipped": False})
        except Exception as e:
            item = ExtractResult(
                pdf=str(pdf),
                txt=str(txt_path),
                pages=-1,
                extracted_chars=0,
                empty_pages=0,
                error=f"{type(e).__name__}: {e}",
            )
            index["items"].append(asdict(item) | {"skipped": False})

    (out_dir / "_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
        errors="replace",
    )
    print(f"Done. Extracted index: {out_dir / '_index.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


