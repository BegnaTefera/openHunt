from __future__ import annotations

import io
import zipfile

import pytest

from app.services.cv import (
    CvError,
    detect_kind,
    extract_text,
    redact_contact_details,
    suggest_profile,
)

CV_TEXT = """JANE EXAMPLE
Backend engineer
jane@example.com | +1 (555) 123-4567

Skills: Python, FastAPI, PostgreSQL, Docker, React, C++, Node.js and Kubernetes.
Built a Next.js dashboard and a Rust CLI. Worked with AWS and Terraform.
"""


def make_docx(text: str) -> bytes:
    paragraphs = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines())
    document = f'<w:document xmlns:w="x"><w:body>{paragraphs}</w:body></w:document>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def make_pdf(text: str) -> bytes:
    lines = [line for line in text.splitlines() if line.strip()]
    stream = "BT /F1 11 Tf 40 780 Td 14 TL " + " ".join(f"({line.replace('(', '[').replace(')', ']')}) Tj T*" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = "%PDF-1.4\n"
    offsets = []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n{content}\nendobj\n"
    xref = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    body += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    body += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    return body.encode("latin-1")


def test_file_kind_comes_from_content_not_the_name() -> None:
    assert detect_kind(b"%PDF-1.7 ...") == "pdf"
    assert detect_kind(make_docx("hello")) == "docx"
    assert detect_kind(b"plain words") == "text"
    with pytest.raises(CvError):
        detect_kind(b"\x89PNG\r\n\x1a\n\x00\x00binary")


def test_text_files_are_decoded() -> None:
    assert extract_text("text", "Résumé of Jane".encode("utf-8")) == "Résumé of Jane"


def test_docx_text_is_extracted_with_line_breaks() -> None:
    text = extract_text("docx", make_docx(CV_TEXT))

    assert "Backend engineer" in text and "Kubernetes" in text
    assert "<w:" not in text


def test_broken_docx_files_give_a_clear_error() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("other.txt", "x")
    with pytest.raises(CvError, match="Word"):
        extract_text("docx", buffer.getvalue())
    with pytest.raises(CvError):
        extract_text("docx", b"PK\x03\x04 not really a zip")


def test_pdf_text_is_extracted() -> None:
    text = extract_text("pdf", make_pdf(CV_TEXT))

    assert "Backend engineer" in text
    assert "FastAPI" in text


def test_garbage_pdfs_give_a_clear_error() -> None:
    with pytest.raises(CvError):
        extract_text("pdf", b"%PDF-1.4 this is not a real pdf at all")


def test_suggestions_find_name_and_skills() -> None:
    suggestions = suggest_profile(CV_TEXT)

    assert suggestions.full_name == "Jane Example"
    for skill in ("Python", "FastAPI", "PostgreSQL", "Docker", "React", "C++", "Node.js", "Kubernetes", "Next.js", "Rust", "AWS", "Terraform"):
        assert skill in suggestions.skills, skill
    assert "Java" not in suggestions.skills  # no partial match inside JavaScript-free text
    assert "Go" not in suggestions.skills


def test_name_guess_ignores_headings_and_lines_with_numbers() -> None:
    assert suggest_profile("Curriculum Vitae\nAda Lovelace\nEngineer").full_name == "Ada Lovelace"
    assert suggest_profile("RESUME\n2020-2024 Experience\nsome text").full_name is None


def test_contact_details_are_redacted_before_sharing() -> None:
    redacted = redact_contact_details(CV_TEXT)

    assert "jane@example.com" not in redacted and "555" not in redacted
    assert "[email]" in redacted and "[phone]" in redacted
    assert "FastAPI" in redacted
