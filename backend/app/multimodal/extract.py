from __future__ import annotations

import base64
import io
import mimetypes
import os
import subprocess
from pathlib import Path

import httpx


def _openai_api_key() -> str | None:
    return os.getenv("MEDRAG_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")


def _openai_base_url() -> str:
    return (os.getenv("MEDRAG_OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")


def _openai_mm_model() -> str:
    return os.getenv("MEDRAG_OPENAI_MULTIMODAL_MODEL") or "gpt-4.1-mini"


def _openai_audio_model() -> str:
    return os.getenv("MEDRAG_OPENAI_AUDIO_MODEL") or "gpt-4o-mini-transcribe"


def _extract_text_with_openai_file(filename: str, data: bytes) -> str:
    key = _openai_api_key()
    if not key:
        raise RuntimeError("OpenAI API key not configured for multimodal fallback.")
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    b64 = base64.b64encode(data).decode("ascii")
    payload = {
        "model": _openai_mm_model(),
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Extract readable text from this document. "
                            "Return plain text only and preserve section structure when possible."
                        ),
                    },
                    {
                        "type": "input_file",
                        "filename": filename or "upload.bin",
                        "file_data": f"data:{mime};base64,{b64}",
                    },
                ],
            }
        ],
    }
    timeout = httpx.Timeout(connect=30.0, read=300.0, write=300.0, pool=30.0)
    with httpx.Client(base_url=_openai_base_url(), timeout=timeout, headers={"Authorization": f"Bearer {key}"}) as client:
        r = client.post("/responses", json=payload)
        r.raise_for_status()
        j = r.json()
    text = (j.get("output_text") or "").strip()
    if not text:
        text = _extract_text_from_response_json(j)
    if not text:
        raise RuntimeError("OpenAI document extraction returned empty text.")
    return text


def _extract_text_from_response_json(payload: dict) -> str:
    out: list[str] = []
    for item in payload.get("output") or []:
        for c in item.get("content") or []:
            t = c.get("text")
            if isinstance(t, str) and t.strip():
                out.append(t.strip())
    return "\n".join(out).strip()


def _extract_text_from_openai_image(filename: str, data: bytes) -> str:
    key = _openai_api_key()
    if not key:
        raise RuntimeError("OpenAI API key not configured for image fallback.")
    mime = mimetypes.guess_type(filename)[0] or "image/png"
    b64 = base64.b64encode(data).decode("ascii")
    payload = {
        "model": _openai_mm_model(),
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Extract all readable text from this image or screenshot. "
                            "Return plain text only."
                        ),
                    },
                    {"type": "input_image", "image_url": f"data:{mime};base64,{b64}"},
                ],
            }
        ],
    }
    timeout = httpx.Timeout(connect=30.0, read=300.0, write=300.0, pool=30.0)
    with httpx.Client(base_url=_openai_base_url(), timeout=timeout, headers={"Authorization": f"Bearer {key}"}) as client:
        r = client.post("/responses", json=payload)
        r.raise_for_status()
        j = r.json()
    text = (j.get("output_text") or "").strip()
    if not text:
        text = _extract_text_from_response_json(j)
    if not text:
        raise RuntimeError("OpenAI image extraction returned empty text.")
    return text


def _extract_text_from_openai_audio(filename: str, data: bytes) -> str:
    key = _openai_api_key()
    if not key:
        raise RuntimeError("OpenAI API key not configured for audio fallback.")
    mime = mimetypes.guess_type(filename)[0] or "audio/wav"
    timeout = httpx.Timeout(connect=30.0, read=600.0, write=600.0, pool=30.0)
    with httpx.Client(base_url=_openai_base_url(), timeout=timeout, headers={"Authorization": f"Bearer {key}"}) as client:
        r = client.post(
            "/audio/transcriptions",
            data={"model": _openai_audio_model(), "response_format": "text"},
            files={"file": (filename or "audio.wav", data, mime)},
        )
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        if "application/json" in ctype:
            j = r.json()
            text = (j.get("text") or "").strip()
        else:
            text = (r.text or "").strip()
    if not text:
        raise RuntimeError("OpenAI audio transcription returned empty text.")
    return text


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
            # Fallback to OpenAI document extraction when local parser is unavailable.
            if _openai_api_key():
                return _extract_text_with_openai_file(filename, data)
            raise RuntimeError(
                "PDF extraction requires `pypdf`, or configure OpenAI key for multimodal fallback."
            ) from e
        reader = PdfReader(io.BytesIO(data))
        text_parts: list[str] = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                text_parts.append(t.strip())
        text = "\n\n".join(text_parts).strip()
        if not text:
            if _openai_api_key():
                return _extract_text_with_openai_file(filename, data)
            raise RuntimeError("No text extracted from PDF (it may be scanned; try image OCR or OpenAI fallback).")
        return text

    if ext == ".docx":
        try:
            import docx  # python-docx
        except Exception as e:  # noqa: BLE001
            if _openai_api_key():
                return _extract_text_with_openai_file(filename, data)
            raise RuntimeError(
                "DOCX extraction requires `python-docx`, or configure OpenAI key for multimodal fallback."
            ) from e
        doc = docx.Document(io.BytesIO(data))
        text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()]).strip()
        if not text:
            if _openai_api_key():
                return _extract_text_with_openai_file(filename, data)
            raise RuntimeError("No text extracted from DOCX.")
        return text

    # Fallback for other document types (e.g. scanned PDFs, unsupported office formats)
    if _openai_api_key():
        return _extract_text_with_openai_file(filename, data)

    raise RuntimeError(
        f"Unsupported document type: {ext or '(no extension)'}. Configure OpenAI key for multimodal fallback."
    )


def extract_text_from_image(filename: str, data: bytes) -> str:
    # Try local OCR first.
    try:
        from PIL import Image
        import pytesseract
        if _has_tesseract():
            img = Image.open(io.BytesIO(data))
            text = (pytesseract.image_to_string(img) or "").strip()
            if text:
                return text
    except Exception:
        pass

    # Fallback to OpenAI vision OCR model.
    if _openai_api_key():
        return _extract_text_from_openai_image(filename, data)

    raise RuntimeError(
        "Image OCR unavailable. Install pillow+pytesseract+tesseract, or configure OpenAI key for multimodal fallback."
    )


def _has_tesseract() -> bool:
    try:
        # `where` is built-in on Windows; but use subprocess for portability.
        p = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=5)
        return p.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def extract_text_from_audio(filename: str, data: bytes) -> str:
    # Use local faster-whisper first.
    try:
        from faster_whisper import WhisperModel
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            f.write(data)
            tmp_path = f.name
        try:
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _info = model.transcribe(tmp_path)
            text = " ".join((s.text or "").strip() for s in segments).strip()
            if text:
                return text
        finally:
            try:
                os.remove(tmp_path)
            except Exception:  # noqa: BLE001
                pass
    except Exception:
        pass

    # Fallback to OpenAI audio transcription model.
    if _openai_api_key():
        return _extract_text_from_openai_audio(filename, data)

    raise RuntimeError(
        "Audio transcription unavailable. Install faster-whisper (+soundfile), or configure OpenAI key for multimodal fallback."
    )
