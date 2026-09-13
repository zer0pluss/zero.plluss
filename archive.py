import json
from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC = True
except Exception:
    ARABIC = False


def ar(text):
    text = str(text or "")
    if ARABIC:
        return get_display(arabic_reshaper.reshape(text))
    return text


def register_font():
    candidates = [
        "Cairo-Regular.ttf", "NotoNaskhArabic-Regular.ttf", "DejaVuSans.ttf"
    ]
    import os
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("ZERO_AR", path))
                return "ZERO_AR"
            except Exception:
                pass
    return "Helvetica"


def daily_payload(orders, note, day):
    rows = []
    for o in orders:
        rows.append({
            "order_id": int(o["order_id"]),
            "customer_name": o["name"],
            "phone": o["phone"],
            "details": o["order_details"],
            "order_date": str(o["order_date"]),
            "total_cost": float(o["total_cost"]),
            "deposit": float(o["deposit"]),
            "remaining": float(o["total_cost"] - o["deposit"]),
            "payment_status": o["payment_status"],
            "order_status": o["order_status"],
        })
    return {"date": str(day), "orders": rows, "daily_note": note or ""}


def make_json(orders, note, day):
    return json.dumps(daily_payload(orders, note, day), ensure_ascii=False, indent=2).encode("utf-8")


def make_pdf(orders, note, day):
    font = register_font()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), rightMargin=10*mm, leftMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
    title = ParagraphStyle("title", fontName=font, fontSize=18, leading=22, alignment=TA_RIGHT, textColor=colors.HexColor("#0f172a"))
    normal = ParagraphStyle("normal", fontName=font, fontSize=8, leading=11, alignment=TA_RIGHT)
    center = ParagraphStyle("center", fontName=font, fontSize=8, leading=10, alignment=TA_CENTER)
    story = [Paragraph(ar(f"ZERO Advertising — تقرير طلبات يوم {day}"), title), Spacer(1, 6*mm)]
    headers = ["رقم", "العميل", "التليفون", "التفاصيل", "الإجمالي", "العربون", "المتبقي", "الدفع", "الحالة"]
    data = [[Paragraph(ar(h), center) for h in headers]]
    total = paid = 0
    for o in orders:
        t, d = float(o["total_cost"]), float(o["deposit"])
        total += t; paid += d
        data.append([
            Paragraph(ar(o["order_id"]), center), Paragraph(ar(o["name"]), center), Paragraph(ar(o["phone"] or "-"), center),
            Paragraph(ar(o["order_details"]), normal), Paragraph(ar(f"{t:,.2f}"), center), Paragraph(ar(f"{d:,.2f}"), center),
            Paragraph(ar(f"{t-d:,.2f}"), center), Paragraph(ar(o["payment_status"]), center), Paragraph(ar(o["order_status"]), center)
        ])
    if len(data) == 1:
        data.append([Paragraph(ar("لا توجد طلبات لهذا اليوم"), center)] + [""]*8)
    table = Table(data, repeatRows=1, colWidths=[12*mm, 30*mm, 30*mm, 78*mm, 22*mm, 22*mm, 22*mm, 40*mm, 30*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5)
    ]))
    story.append(table)
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph(ar(f"إجمالي الطلبات: {len(orders)}   |   إجمالي المبيعات: {total:,.2f} ج   |   إجمالي المدفوع: {paid:,.2f} ج   |   المتبقي: {total-paid:,.2f} ج"), normal))
    if note:
        story += [Spacer(1, 4*mm), Paragraph(ar("ملاحظة اليوم"), title), Paragraph(ar(note), normal)]
    doc.build(story)
    return buf.getvalue()
