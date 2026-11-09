from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
import pytesseract
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..receipt_ocr import extract_receipt_data
from ..security import get_current_user

router = APIRouter(prefix="/receipts", tags=["receipts"])
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


@router.post("/scan")
async def scan_receipt(
    file: UploadFile = File(...),
    _db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Extract editable expense suggestions from a receipt; never saves a transaction."""
    del user  # Authentication is required; receipt images are processed in memory only.
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a JPG, PNG or WebP image")

    raw = await file.read(MAX_IMAGE_BYTES + 1)
    await file.close()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded image is empty")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image must be 5 MB or smaller")

    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Unsupported image format")
            if source.width * source.height > 20_000_000:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image dimensions are too large")
            source.load()
            image = source.convert("RGB")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is not a valid image")

    try:
        result = extract_receipt_data(image)
    except pytesseract.pytesseract.TesseractNotFoundError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Receipt scanning is not configured. Install the Tesseract OCR engine on the server.",
        )
    except pytesseract.TesseractError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Could not read this receipt. Try a clearer image.")

    if not result.get("extracted_text", "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No readable text found. Try a clearer image.")
    return result
