from __future__ import annotations

import io
import os
import subprocess
from pathlib import Path


def extract_text_from_document(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext in (".txt", ".md", ".csv", ".json"):
        try:
            return data.decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            return data.decode(errors="ignore")

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("PDF extraction requires `pypdf` (see backend/requirements.txt optional deps).") from e
        reader = PdfReader(io.BytesIO(data))
        text_parts: list[str] = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                text_parts.append(t.strip())
        text = "\n\n".join(text_parts).strip()
        if not text:
            raise RuntimeError("No text extracted from PDF (it may be scanned; try the image endpoint/OCR).")
        return text

    if ext == ".docx":
        try:
            import docx  # python-docx
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("DOCX extraction requires `python-docx` (see backend/requirements.txt optional deps).") from e
        doc = docx.Document(io.BytesIO(data))
        text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()]).strip()
        if not text:
            raise RuntimeError("No text extracted from DOCX.")
        return text

    raise RuntimeError(f"Unsupported document type: {ext or '(no extension)'}")


def extract_text_from_image(filename: str, data: bytes) -> str:
    _ = filename
    try:
        from PIL import Image
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("Image OCR requires `pillow` (see backend/requirements.txt optional deps).") from e
    try:
        import pytesseract
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("Image OCR requires `pytesseract` (see backend/requirements.txt optional deps).") from e

    # Ensure tesseract is actually installed (Windows usually needs it separately).
    if not _has_tesseract():
        raise RuntimeError("Tesseract OCR binary not found on PATH. Install Tesseract and retry.")

    img = Image.open(io.BytesIO(data))
    text = (pytesseract.image_to_string(img) or "").strip()
    if not text:
        raise RuntimeError("OCR returned empty text.")
    return text


def _has_tesseract() -> bool:
    try:
        # `where` is built-in on Windows; but use subprocess for portability.
        p = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=5)
        return p.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def extract_text_from_audio(filename: str, data: bytes) -> str:
    _ = filename
    # Use faster-whisper if installed; otherwise fail with a clear message.
    try:
        from faster_whisper import WhisperModel
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "Audio transcription requires `faster-whisper` (+ `soundfile`). Install optional deps and retry."
        ) from e

    # Write to a temp file because the library expects a path.
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(data)
        tmp_path = f.name
    try:
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(tmp_path)
        text = " ".join((s.text or "").strip() for s in segments).strip()
        if not text:
            raise RuntimeError("Transcription returned empty text.")
        return text
    finally:
        try:
            os.remove(tmp_path)
        except Exception:  # noqa: BLE001
            pass
