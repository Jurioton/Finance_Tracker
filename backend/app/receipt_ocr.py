"""OCR helpers for extracting basic transaction details from receipt images."""
from datetime import date, datetime
import re

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract


TOTAL_LABELS = ("grand total", "amount due", "total payable", "net amount", "bill total", "total")
CATEGORY_KEYWORDS = {
    "Food": ("restaurant", "cafe", "coffee", "swiggy", "zomato", "food", "dining",
             "paneer", "tikka", "naan", "masala chai", "burger", "pizza"),
    "Transport": ("uber", "ola", "fuel", "petrol", "diesel", "metro", "parking", "taxi"),
    "Shopping": ("amazon", "flipkart", "mall", "store", "retail", "shopping"),
    "Health": ("pharmacy", "medical", "hospital", "clinic", "medicine"),
    "Utilities": ("electricity", "water bill", "internet", "broadband", "mobile recharge"),
}


def _parse_date(text: str) -> date | None:
    patterns = (
        (r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", "%Y-%m-%d"),
        (r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", "%d-%m-%Y"),
    )
    for pattern, fmt in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        raw = match.group(0).replace("/", "-").replace(".", "-")
        try:
            parsed = datetime.strptime(raw, fmt).date()
            if 2000 <= parsed.year <= 2100:
                return parsed
        except ValueError:
            continue
    return None


def _amounts(text: str) -> list[float]:
    pattern = r"(?:₹|\bINR\b|\bRs\.?\s*)?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)"
    values = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        try:
            value = float(match.group(1).replace(",", ""))
            if 0 < value < 100_000_000:
                values.append(value)
        except ValueError:
            pass
    return values


def parse_receipt_text(text: str) -> dict:
    """Convert OCR text into conservative, editable transaction suggestions."""
    lines = [re.sub(r"\s+", " ", line).strip(" :-|") for line in text.splitlines()]
    lines = [line for line in lines if line]
    lower_text = text.lower()

    amount = None
    for label in TOTAL_LABELS:
        candidates = [line for line in lines if label in line.lower()]
        if candidates:
            values = _amounts(candidates[-1])
            if values:
                amount = values[-1]
                break
    if amount is None:
        values = _amounts(text)
        amount = max(values) if values else None

    merchant = None
    ignored = ("receipt", "tax invoice", "invoice", "bill no", "gstin", "date:", "phone:")
    for line in lines[:10]:
        if len(line) >= 2 and not any(word in line.lower() for word in ignored):
            if not re.search(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b", line):
                # Skip address/contact lines; the first plausible header line is usually the merchant.
                if re.search(r"\b(road|street|avenue|phone|market)\b", line.lower()):
                    continue
                merchant = line[:100]
                break

    category = None
    for name, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lower_text for keyword in keywords):
            category = name
            break

    parsed_date = _parse_date(text)
    return {
        "merchant": merchant,
        "amount": amount,
        "date": parsed_date.isoformat() if parsed_date else None,
        "note": merchant or "Receipt expense",
        "suggested_category": category,
        "extracted_text": text[:4000],
    }


def _prepare_for_ocr(image: Image.Image) -> Image.Image:
    """Enlarge and improve receipt text before passing it to Tesseract."""
    prepared = ImageOps.grayscale(image)
    # Small phone screenshots often have text only a few pixels tall.
    if prepared.width < 1200:
        scale = 1200 / prepared.width
        prepared = prepared.resize(
            (1200, max(1, round(prepared.height * scale))),
            Image.Resampling.LANCZOS,
        )
    prepared = ImageOps.autocontrast(prepared)
    prepared = ImageEnhance.Contrast(prepared).enhance(1.35)
    return prepared.filter(ImageFilter.UnsharpMask(radius=1.5, percent=150, threshold=3))


def extract_receipt_data(image: Image.Image) -> dict:
    """Run Tesseract OCR on a preprocessed receipt image."""
    prepared = _prepare_for_ocr(image)
    text = pytesseract.image_to_string(
        prepared,
        config="--oem 3 --psm 6 -c preserve_interword_spaces=1",
    )
    return parse_receipt_text(text)
