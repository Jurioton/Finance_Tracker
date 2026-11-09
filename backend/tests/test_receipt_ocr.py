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


def test_parse_receipt_text_suggests_food_from_receipt_items():
    result = parse_receipt_text(
        "Tasty Forks\nPaneer Tikka 240.00\nButter Naan 90.00\n"
        "Masala Chai 120.00\nGrand Total 472.50"
    )
    assert result["merchant"] == "Tasty Forks"
    assert result["amount"] == 472.5
    assert result["suggested_category"] == "Food"


def test_parse_receipt_text_rejects_unreasonable_ocr_year():
    result = parse_receipt_text("Cafe\nDate: 2926-02-06\nGrand Total 100.00")
    assert result["date"] is None
