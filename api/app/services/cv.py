"""Read an uploaded CV (PDF, DOCX, or plain text) and suggest profile details from it.

Everything here is local and free: no AI and no network. Suggestions are only
prefilled values the user reviews and edits during onboarding.
"""

from __future__ import annotations

import html
import io
import re
import zipfile
from dataclasses import dataclass, field

MAX_TEXT_CHARS = 60_000
MAX_PDF_PAGES = 12
MAX_DOCX_XML_BYTES = 15_000_000

PDF_TYPE = "application/pdf"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT_TYPE = "text/plain; charset=utf-8"


class CvError(ValueError):
    """The file is not a CV we can read. The message is safe to show to the user."""


def detect_kind(data: bytes) -> str:
    """Identify the file from its content, not its name or declared type."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        return "docx"
    if b"\x00" not in data[:4096]:
        return "text"
    raise CvError("Upload a PDF, a Word (.docx) file, or a plain text file.")


def content_type_for(kind: str) -> str:
    return {"pdf": PDF_TYPE, "docx": DOCX_TYPE, "text": TEXT_TYPE}[kind]


def extract_text(kind: str, data: bytes) -> str:
    if kind == "pdf":
        text = _pdf_text(data)
    elif kind == "docx":
        text = _docx_text(data)
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:MAX_TEXT_CHARS]


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader  # imported lazily so other code never pays for it
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise CvError("This PDF is password protected. Remove the password and upload it again.")
        pages = reader.pages[:MAX_PDF_PAGES]
        return "\n".join((page.extract_text() or "") for page in pages)
    except CvError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, OSError, RecursionError) as error:
        raise CvError("Could not read this PDF. Try exporting it again or upload a .docx.") from error


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise CvError("This Word file is too large to read.")
            xml = archive.read(info).decode("utf-8", errors="replace")
    except KeyError as error:
        raise CvError("This does not look like a Word (.docx) document.") from error
    except zipfile.BadZipFile as error:
        raise CvError("Could not read this Word file.") from error
    xml = re.sub(r"</w:p>|<w:br\s*/>", "\n", xml)
    xml = re.sub(r"<w:tab\s*/>", "\t", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


# ---- suggestions ----

_SKILLS = (
    "Python JavaScript TypeScript Java Kotlin Swift Go Golang Rust Ruby PHP Scala Elixir Dart Perl Lua Haskell "
    "C++ C# .NET Bash PowerShell SQL NoSQL GraphQL HTML CSS Sass "
    "React Next.js Vue Nuxt Angular Svelte Redux Tailwind Bootstrap jQuery "
    "Node.js Express NestJS Django Flask FastAPI Spring Laravel Rails Symfony ASP.NET "
    "React-Native Flutter Android iOS SwiftUI Jetpack "
    "PostgreSQL MySQL SQLite MongoDB Redis Cassandra DynamoDB Elasticsearch Kafka RabbitMQ Snowflake BigQuery Redshift "
    "AWS Azure GCP Docker Kubernetes Terraform Ansible Jenkins GitHub-Actions GitLab-CI CI/CD Linux Nginx Prometheus Grafana "
    "Pandas NumPy SciPy Scikit-learn TensorFlow PyTorch Keras OpenCV MediaPipe Spark Hadoop Airflow dbt Tableau Power-BI "
    "Machine-Learning Deep-Learning NLP LLM Computer-Vision MLOps "
    "Git REST gRPC WebSockets OAuth JWT Microservices Agile Scrum Jira Figma Selenium Cypress Playwright Jest Pytest "
    "Unity Unreal Godot GDScript Blender OpenGL Vulkan Arduino Raspberry-Pi Embedded FPGA Solidity"
).split()


def _skill_label(token: str) -> str:
    return token.replace("-", " ")


def _skill_pattern(label: str) -> re.Pattern[str]:
    escaped = re.escape(label).replace(r"\ ", r"[\s-]+")
    return re.compile(rf"(?<![\w+#]){escaped}(?![\w+#])", re.IGNORECASE)


_SKILL_PATTERNS = [(_skill_label(token), _skill_pattern(_skill_label(token))) for token in _SKILLS]
_NOT_NAMES = {"curriculum vitae", "resume", "résumé", "cv", "profile", "summary", "contact"}
_NAME_RE = re.compile(r"[A-Z][A-Za-z'’.-]+(?: [A-Z][A-Za-z'’.-]+){1,3}")


@dataclass
class CvSuggestions:
    full_name: str | None = None
    skills: list[str] = field(default_factory=list)


def suggest_profile(text: str) -> CvSuggestions:
    skills = [label for label, pattern in _SKILL_PATTERNS if pattern.search(text)]
    return CvSuggestions(full_name=_guess_name(text), skills=skills)


def _guess_name(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()][:6]
    for line in lines:
        candidate = line.title() if line.isupper() else line
        if (
            _NAME_RE.fullmatch(candidate)
            and candidate.casefold() not in _NOT_NAMES
            and not any(character.isdigit() for character in candidate)
        ):
            return candidate
    return None


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")


def redact_contact_details(text: str) -> str:
    """Remove emails and phone numbers before text is sent to any outside service."""
    return _PHONE_RE.sub("[phone]", _EMAIL_RE.sub("[email]", text))
