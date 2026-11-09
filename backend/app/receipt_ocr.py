"""OCR helpers for extracting basic transaction details from receipt images."""
from datetime import date
import re

from PIL import Image
import pytesseract


TOTAL_LABELS = ("grand total", "amount due", "total payable", "net amount", "bill total", "total")
CATEGORY_KEYWORDS = {
    "Food": ("restaurant", "cafe", "coffee", "swiggy", "zomato", "food", "dining"),
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
    from datetime import datetime

    for pattern, fmt in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        raw = match.group(0).replace("/", "-").replace(".", "-")
        try:
            return datetime.strptime(raw, fmt).date()
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
    ignored = ("receipt", "tax invoice", "invoice", "bill no", "gstin", "date:")
    for line in lines[:8]:
        if len(line) >= 2 and not any(word in line.lower() for word in ignored):
            if not re.search(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b", line):
                merchant = line[:100]
                break

    category = None
    for name, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lower_text for keyword in keywords):
            category = name
            break

    return {
        "merchant": merchant,
        "amount": amount,
        "date": (_parse_date(text).isoformat() if _parse_date(text) else None),
        "note": merchant or "Receipt expense",
        "suggested_category": category,
        "extracted_text": text[:4000],
    }


def extract_receipt_data(image: Image.Image) -> dict:
    """Run Tesseract OCR on an already validated PIL image."""
    text = pytesseract.image_to_string(image.convert("RGB"), config="--psm 6")
    return parse_receipt_text(text)
