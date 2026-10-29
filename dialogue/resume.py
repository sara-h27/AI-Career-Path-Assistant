"""In-memory resume text extraction for the Streamlit intake boundary."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree


MAX_RESUME_BYTES = 5_000_000
MAX_RESUME_CHARS = 8_000


class ResumeError(ValueError):
    """A safe, user-facing resume extraction failure."""


@dataclass(frozen=True)
class ResumeDocument:
    text: str
    file_type: str
    truncated: bool = False


def _clean_text(value: str) -> str:
    value = value.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _docx_text(content: bytes) -> str:
    try:
        with ZipFile(BytesIO(content)) as archive:
            try:
                info = archive.getinfo("word/document.xml")
            except KeyError as exc:
                raise ResumeError("فایل DOCX معتبر نیست.") from exc
            if info.file_size > 10_000_000:
                raise ResumeError("ساختار داخلی فایل DOCX بیش از حد بزرگ است.")
            root = ElementTree.fromstring(archive.read(info))
    except (BadZipFile, ElementTree.ParseError) as exc:
        raise ResumeError("فایل DOCX خوانده نشد.") from exc

    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if text.strip():
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is installed from requirements.txt
        raise ResumeError("برای خواندن PDF، وابستگی pypdf نصب نشده است.") from exc
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise ResumeError("PDF رمزگذاری‌شده پشتیبانی نمی‌شود.")
        return "\n".join((page.extract_text() or "") for page in reader.pages[:30])
    except ResumeError:
        raise
    except Exception as exc:
        raise ResumeError("متن PDF خوانده نشد؛ فایل سالم یا متن‌محور دیگری بارگذاری کن.") from exc


def extract_resume_text(filename: str, content: bytes, *, max_chars: int = MAX_RESUME_CHARS) -> ResumeDocument:
    """Extract bounded text without writing the uploaded resume to disk."""
    if not isinstance(content, bytes) or not content:
        raise ResumeError("فایل رزومه خالی است.")
    if len(content) > MAX_RESUME_BYTES:
        raise ResumeError("حجم رزومه باید حداکثر ۵ مگابایت باشد.")
    if not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError("max_chars must be a positive integer")

    suffix = Path(filename or "").suffix.lower()
    if suffix == ".pdf":
        raw = _pdf_text(content)
        file_type = "PDF"
    elif suffix == ".docx":
        raw = _docx_text(content)
        file_type = "DOCX"
    elif suffix == ".txt":
        try:
            raw = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ResumeError("فایل متنی باید با UTF-8 ذخیره شده باشد.") from exc
        file_type = "TXT"
    else:
        raise ResumeError("فرمت رزومه باید PDF، DOCX یا TXT باشد.")

    text = _clean_text(raw)
    if not text:
        raise ResumeError("متنی از رزومه استخراج نشد؛ احتمالاً فایل اسکن‌شده است.")
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars].rsplit("\n", 1)[0].strip() or text[:max_chars].strip()
    return ResumeDocument(text=text, file_type=file_type, truncated=truncated)
