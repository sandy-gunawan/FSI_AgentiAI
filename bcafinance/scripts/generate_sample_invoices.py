"""Generate 20 realistic Indonesian commercial invoices as PDF + PNG.

Output: data/sample_invoices/INV-XX.pdf and .png plus a manifest.json describing
the intended "defect" of each (clean, missing NPWP, missing PO, math error,
over-limit, expired tenor, low-quality scan) so you can predict the review
outcome (APPROVE / REFER / REJECT) when demoing both extraction options.

RUN
---
    python scripts/generate_sample_invoices.py
"""
from __future__ import annotations

import json
import pathlib
import random
import sys
from dataclasses import dataclass, field

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402
from PIL import Image, ImageDraw, ImageFont, ImageFilter  # noqa: E402

from app.core.config import get_settings  # noqa: E402

random.seed(42)

_SELLERS = [
    ("PT Maju Bersama", "8820-1177-9043"),
    ("PT Sinar Teknologi", "8811-2244-1090"),
    ("CV Karya Mandiri", "8890-5533-2211"),
    ("PT Nusantara Logistik", "8802-7788-6655"),
    ("PT Agro Sejahtera", "8877-1122-3344"),
]
_BUYERS = [
    ("PT Karya Retail Nusantara", "01.234.567.8-901.000"),
    ("PT Global Distribusi", "02.345.678.9-012.000"),
    ("PT Prima Konstruksi", "03.456.789.0-123.000"),
    ("PT Sentosa Manufaktur", "04.567.890.1-234.000"),
    ("PT Bahari Niaga", "05.678.901.2-345.000"),
]
_ITEMS = [
    ("Panel surya 450W", 1_850_000), ("Inverter hybrid 5kW", 4_200_000),
    ("Semen 50kg (sak)", 62_000), ("Baja ringan 4m (batang)", 98_000),
    ("Pupuk NPK 50kg", 720_000), ("Server rack 42U", 18_500_000),
    ("Router industrial", 3_400_000), ("Truk tronton (sewa/hari)", 2_750_000),
]


@dataclass
class Spec:
    idx: int
    defect: str                       # clean | missing_npwp | missing_po | math_error | over_limit | expired_tenor | low_quality
    expected: str                     # APPROVE | REFER | REJECT
    seller: tuple = field(default=None)
    buyer: tuple = field(default=None)


# 20 invoices: mix of outcomes to exercise the reviewer + rules engine.
_PLAN = (
    [("clean", "APPROVE")] * 7
    + [("missing_po", "REFER"), ("missing_npwp", "REFER"), ("math_error", "REFER"),
       ("low_quality", "REFER"), ("missing_npwp", "REFER"), ("missing_po", "REFER")]
    + [("over_limit", "REJECT"), ("over_limit", "REJECT"), ("expired_tenor", "REJECT")]
    + [("clean", "APPROVE"), ("low_quality", "REFER"), ("math_error", "REFER"), ("clean", "APPROVE")]
)


def _fmt(n: int) -> str:
    return f"Rp {n:,}".replace(",", ".")


def _build(spec: Spec) -> dict:
    seller = _SELLERS[spec.idx % len(_SELLERS)]
    buyer = _BUYERS[(spec.idx * 3) % len(_BUYERS)]
    n_items = random.randint(1, 3)
    items = []
    for _ in range(n_items):
        name, price = random.choice(_ITEMS)
        qty = random.randint(5, 200)
        items.append({"description": name, "quantity": qty,
                      "unit_price_idr": price, "amount_idr": qty * price})
    subtotal = sum(i["amount_idr"] for i in items)

    # Over-limit: scale up beyond max_facility (1,000,000,000).
    if spec.defect == "over_limit":
        factor = (1_200_000_000 // max(subtotal, 1)) + 1
        for i in items:
            i["quantity"] *= factor
            i["amount_idr"] = i["quantity"] * i["unit_price_idr"]
        subtotal = sum(i["amount_idr"] for i in items)

    tax = round(subtotal * 0.11)
    total = subtotal + tax
    if spec.defect == "math_error":
        total = subtotal + tax - random.randint(500_000, 2_000_000)  # inconsistent

    issue = f"2026-07-{(spec.idx % 27) + 1:02d}"
    term = 240 if spec.defect == "expired_tenor" else random.choice([30, 60, 90])
    from datetime import date, timedelta
    due = (date.fromisoformat(issue) + timedelta(days=term)).isoformat()

    return {
        "invoice_number": f"INV-2026-{1000 + spec.idx:04d}",
        "issue_date": issue, "due_date": due, "term_days": term,
        "seller": {"name": seller[0], "account": seller[1]},
        "buyer": {"name": buyer[0], "npwp": "" if spec.defect == "missing_npwp" else buyer[1]},
        "po_number": "" if spec.defect == "missing_po" else f"PO-{2000 + spec.idx}",
        "items": items, "subtotal_idr": subtotal, "tax_idr": tax, "total_amount_idr": total,
    }


def _draw_pdf(path: pathlib.Path, inv: dict) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 30 * mm
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, y, inv["seller"]["name"])
    c.setFont("Helvetica", 10)
    y -= 7 * mm
    c.drawString(20 * mm, y, f"Rekening: BCA {inv['seller']['account']}")
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(w - 20 * mm, h - 30 * mm, "FAKTUR / INVOICE")
    c.setFont("Helvetica", 10)
    c.drawRightString(w - 20 * mm, h - 37 * mm, f"No: {inv['invoice_number']}")
    c.drawRightString(w - 20 * mm, h - 43 * mm, f"Tanggal: {inv['issue_date']}")
    c.drawRightString(w - 20 * mm, h - 49 * mm, f"Jatuh tempo: {inv['due_date']}")
    if inv["po_number"]:
        c.drawRightString(w - 20 * mm, h - 55 * mm, f"PO: {inv['po_number']}")

    y -= 12 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Kepada:")
    c.setFont("Helvetica", 10)
    c.drawString(35 * mm, y, inv["buyer"]["name"])
    y -= 6 * mm
    c.drawString(35 * mm, y, f"NPWP: {inv['buyer']['npwp'] or '-'}")

    y -= 12 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "Deskripsi")
    c.drawString(105 * mm, y, "Qty")
    c.drawRightString(150 * mm, y, "Harga")
    c.drawRightString(w - 20 * mm, y, "Jumlah")
    c.line(20 * mm, y - 2 * mm, w - 20 * mm, y - 2 * mm)
    c.setFont("Helvetica", 9)
    y -= 8 * mm
    for it in inv["items"]:
        c.drawString(20 * mm, y, it["description"][:45])
        c.drawString(105 * mm, y, str(it["quantity"]))
        c.drawRightString(150 * mm, y, _fmt(it["unit_price_idr"]))
        c.drawRightString(w - 20 * mm, y, _fmt(it["amount_idr"]))
        y -= 6 * mm

    y -= 4 * mm
    c.line(120 * mm, y, w - 20 * mm, y)
    y -= 7 * mm
    for label, val in (("Subtotal", inv["subtotal_idr"]), ("PPN 11%", inv["tax_idr"]),
                       ("TOTAL", inv["total_amount_idr"])):
        c.setFont("Helvetica-Bold" if label == "TOTAL" else "Helvetica", 10)
        c.drawString(120 * mm, y, label)
        c.drawRightString(w - 20 * mm, y, _fmt(val))
        y -= 7 * mm

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(20 * mm, 30 * mm, "Tanda tangan & cap perusahaan")
    c.rect(20 * mm, 12 * mm, 45 * mm, 15 * mm)
    c.save()


def _draw_png(path: pathlib.Path, inv: dict, low_quality: bool) -> None:
    W, H = 1000, 1414
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    def font(sz, bold=False):
        try:
            return ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", sz)
        except Exception:
            return ImageFont.load_default()

    d.text((60, 50), inv["seller"]["name"], fill="black", font=font(34, True))
    d.text((60, 95), f"Rekening: BCA {inv['seller']['account']}", fill="black", font=font(20))
    d.text((640, 50), "FAKTUR / INVOICE", fill="black", font=font(26, True))
    d.text((640, 95), f"No: {inv['invoice_number']}", fill="black", font=font(18))
    d.text((640, 120), f"Tanggal: {inv['issue_date']}", fill="black", font=font(18))
    d.text((640, 145), f"Jatuh tempo: {inv['due_date']}", fill="black", font=font(18))
    if inv["po_number"]:
        d.text((640, 170), f"PO: {inv['po_number']}", fill="black", font=font(18))

    d.text((60, 210), "Kepada:", fill="black", font=font(20, True))
    d.text((170, 210), inv["buyer"]["name"], fill="black", font=font(20))
    d.text((170, 240), f"NPWP: {inv['buyer']['npwp'] or '-'}", fill="black", font=font(20))

    y = 320
    d.text((60, y), "Deskripsi", fill="black", font=font(18, True))
    d.text((520, y), "Qty", fill="black", font=font(18, True))
    d.text((640, y), "Harga", fill="black", font=font(18, True))
    d.text((840, y), "Jumlah", fill="black", font=font(18, True))
    d.line((60, y + 28, 940, y + 28), fill="black", width=2)
    y += 45
    for it in inv["items"]:
        d.text((60, y), it["description"][:40], fill="black", font=font(17))
        d.text((520, y), str(it["quantity"]), fill="black", font=font(17))
        d.text((640, y), _fmt(it["unit_price_idr"]), fill="black", font=font(17))
        d.text((840, y), _fmt(it["amount_idr"]), fill="black", font=font(17))
        y += 34

    y += 20
    for label, val in (("Subtotal", inv["subtotal_idr"]), ("PPN 11%", inv["tax_idr"]),
                       ("TOTAL", inv["total_amount_idr"])):
        d.text((640, y), label, fill="black", font=font(19, label == "TOTAL"))
        d.text((840, y), _fmt(val), fill="black", font=font(19, label == "TOTAL"))
        y += 34

    d.text((60, H - 140), "Tanda tangan & cap perusahaan", fill="black", font=font(16))
    d.rectangle((60, H - 110, 260, H - 40), outline="black", width=2)

    if low_quality:
        img = img.rotate(-1.5, expand=False, fillcolor="white")
        img = img.filter(ImageFilter.GaussianBlur(1.1))
        img = img.resize((int(W * 0.7), int(H * 0.7))).resize((W, H))
    img.save(str(path), "PNG")


def main() -> None:
    out = get_settings().sample_invoices_dir
    manifest = []
    for idx, (defect, expected) in enumerate(_PLAN):
        spec = Spec(idx=idx, defect=defect, expected=expected)
        inv = _build(spec)
        stem = f"INV-{idx + 1:02d}-{defect}"
        _draw_pdf(out / f"{stem}.pdf", inv)
        _draw_png(out / f"{stem}.png", inv, low_quality=(defect == "low_quality"))
        manifest.append({
            "file": stem, "defect": defect, "expected_decision": expected,
            "invoice_number": inv["invoice_number"], "total_amount_idr": inv["total_amount_idr"],
            "term_days": inv["term_days"], "buyer_npwp": inv["buyer"]["npwp"],
            "po_number": inv["po_number"],
        })
        print(f"  {stem:<28} expected={expected}")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
    print(f"\nWrote {len(_PLAN)} invoices (PDF+PNG) + manifest.json to {out}")


if __name__ == "__main__":
    main()
