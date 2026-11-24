"""Regenerates gpay_statement_sample.pdf: a made-up statement in the Google Pay layout.

All names and ids are fictional. Needs reportlab (`pip install reportlab`), which the app itself
does not require:  python tests/fixtures/make_gpay_fixture.py
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
OUT = Path(__file__).with_name("gpay_statement_sample.pdf")

# (date, time, details, upi id, bank line, amount)
ROWS = [
    ("01 Oct, 2026", "09:15 AM", "Paid to CITY METRO TRANSPORT", "100000000001", "Paid by Demo Bank 1234", "₹40"),
    ("01 Oct, 2026", "11:30 AM", "Received from Asha Kumar", "200000000001", "Paid to Demo Bank 1234", "₹2,000"),
    ("01 Oct, 2026", "01:05 PM", "Paid to GREEN LEAF TEA KADAI", "100000000002", "Paid by Demo Bank 1234", "₹30"),
    ("02 Oct, 2026", "08:00 PM", "Paid to Ravi Shankar", "100000000003", "Paid by Demo Bank 1234", "₹20"),
    ("02 Oct, 2026", "08:01 PM", "Paid to Ravi Shankar", "100000000004", "Paid by Demo Bank 1234", "₹20"),
    ("03 Oct, 2026", "10:10 AM", "Self transfer to Demo Bank 5678", "300000000001", "Paid by Demo Bank 1234", "₹500"),
    # page 2
    ("13Oct, 2026", "06:45 PM", "Received from Monthly Stipend Co", "200000000002", "Paid to Demo Bank 1234", "₹1,250.50"),
    ("20 Oct, 2026", "03:49 PM", "Paid to", "100000000005", "Paid by Demo Bank 1234", "₹96"),
    ("31 Oct, 2026", "09:00 PM", "Paid to SUNRISE PHARMACY", "100000000006", "Paid by Demo Bank 1234", "₹210"),
]


def main():
    pdfmetrics.registerFont(TTFont("DejaVu", FONT))
    c = canvas.Canvas(str(OUT), pagesize=A4)
    width, height = A4
    pages = [ROWS[:6], ROWS[6:]]
    for number, rows in enumerate(pages, start=1):
        c.setFont("DejaVu", 9)
        c.drawRightString(width - 40, height - 40, "Transaction statement")
        c.drawRightString(width - 40, height - 52, "9000000000, demo.user@example.com")
        y = height - 90
        if number == 1:
            c.drawString(40, y, "Transaction statement period")
            c.drawString(330, y, "Sent")
            c.drawString(460, y, "Received")
            c.drawString(40, y - 12, "01 October 2026 - 31 October 2026")
            c.drawString(330, y - 12, "₹416")
            c.drawString(460, y - 12, "₹3,250.50")
            y -= 50
        c.drawString(40, y, "Date & time")
        c.drawString(150, y, "Transaction details")
        c.drawRightString(width - 40, y, "Amount")
        y -= 28
        for day, time, details, upi, bank, amount in rows:
            c.drawString(40, y, day)
            c.drawString(150, y, details)
            c.drawRightString(width - 40, y, amount)
            c.drawString(40, y - 12, time)
            c.drawString(150, y - 12, f"UPI Transaction ID: {upi}")
            c.drawString(155, y - 24, bank)
            y -= 48
        c.drawString(40, 70, "Note: This statement reflects payments made by you on the Google Pay app. Self transfer")
        c.drawString(40, 58, "payments are not included in the total money paid and received.")
        c.drawRightString(width - 40, 40, f"Page {number} of {len(pages)}")
        c.showPage()
    c.save()


if __name__ == "__main__":
    main()
