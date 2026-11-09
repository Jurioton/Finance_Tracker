from app.receipt_ocr import parse_receipt_text


def test_parse_receipt_text_extracts_total_date_and_merchant():
    result = parse_receipt_text(
        "CORNER CAFE\nTax Invoice\nDate: 08/11/2026\n"
        "Coffee 180.00\nTax 32.40\nGrand Total Rs. 212.40"
    )
    assert result["merchant"] == "CORNER CAFE"
    assert result["amount"] == 212.4
    assert result["date"] == "2026-11-08"
    assert result["suggested_category"] == "Food"


def test_parse_receipt_text_handles_missing_fields():
    result = parse_receipt_text("RECEIPT\nThank you")
    assert result["amount"] is None
    assert result["date"] is None
    assert result["suggested_category"] is None
