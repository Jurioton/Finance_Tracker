from io import BytesIO

from PIL import Image

from .conftest import register


def png_bytes():
    image = Image.new("RGB", (80, 40), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_receipt_scan_requires_authentication(client):
    response = client.post("/receipts/scan", files={"file": ("receipt.png", png_bytes(), "image/png")})
    assert response.status_code == 401


def test_receipt_scan_returns_extracted_suggestions(client, monkeypatch):
    auth = register(client)
    from app.routers import receipts

    monkeypatch.setattr(receipts, "extract_receipt_data", lambda image: {
        "merchant": "Corner Cafe",
        "amount": 245.5,
        "date": "2026-11-08",
        "note": "Corner Cafe",
        "suggested_category": "Food",
        "extracted_text": "CORNER CAFE\nTOTAL 245.50",
    })
    response = client.post(
        "/receipts/scan",
        headers=auth,
        files={"file": ("receipt.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["amount"] == 245.5
    assert response.json()["suggested_category"] == "Food"
    # Scanning only suggests values; it must not create a transaction.
    assert client.get("/transactions", headers=auth).json() == []


def test_receipt_scan_rejects_unsupported_mime(client, auth):
    response = client.post(
        "/receipts/scan", headers=auth,
        files={"file": ("receipt.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 415


def test_receipt_scan_rejects_invalid_image(client, auth):
    response = client.post(
        "/receipts/scan", headers=auth,
        files={"file": ("receipt.png", b"not really a png", "image/png")},
    )
    assert response.status_code == 400
