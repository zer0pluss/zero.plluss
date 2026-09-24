import base64
import os
from pathlib import Path as FilePath
from datetime import date, datetime
import sqlite3

import pandas as pd
import streamlit as st

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="ZERO Advertising | Management System",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =========================================================
# FILES
# Put zero.jpg beside this Python file
# =========================================================
LOGO_PATH = "zero.jpg"


def image_base64(path):
    try:
        with open(path, "rb") as file:
            return base64.b64encode(file.read()).decode("utf-8")
    except FileNotFoundError:
        return ""


logo_b64 = image_base64(LOGO_PATH)

# =========================================================
# DATABASE
# =========================================================
DB_NAME = "print_shop.db"


def get_connection():
    return sqlite3.connect(DB_NAME, timeout=30)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            order_details TEXT NOT NULL,
            order_date DATE DEFAULT CURRENT_DATE,
            total_cost REAL DEFAULT 0,
            deposit REAL DEFAULT 0,
            payment_status TEXT,
            order_status TEXT,
            FOREIGN KEY (customer_id)
                REFERENCES customers(customer_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_notes (
            note_id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_date DATE NOT NULL UNIQUE,
            note_text TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# CLOUD BACKUP (Google Drive via Google Apps Script)
# One readable Excel file containing the COMPLETE database.
# =========================================================
import io
import requests
import shutil

DB_NAME = "print_shop.db"
EXCEL_BACKUP_FILENAME = "ZERO_DATABASE_BACKUP.xlsx"


def get_secret(key):
    try:
        value = st.secrets.get(key, "")
        if value:
            return str(value)
    except Exception:
        pass
    return os.environ.get(key, "")


DRIVE_BACKUP_URL = get_secret("DRIVE_BACKUP_URL").strip()
DRIVE_BACKUP_TOKEN = get_secret("DRIVE_BACKUP_TOKEN").strip()


def drive_backup_configured():
    return bool(DRIVE_BACKUP_URL and DRIVE_BACKUP_TOKEN)


def _json_response(response):
    try:
        return response.json()
    except Exception:
        return {"success": False, "error": response.text[:500]}


def _db_to_excel_bytes():
    """Export the COMPLETE SQLite database to one readable Excel workbook."""
    output = io.BytesIO()
    conn = sqlite3.connect(DB_NAME, timeout=30)
    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for table in ("customers", "orders", "daily_notes"):
                df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
                df.to_excel(writer, sheet_name=table, index=False)
    finally:
        conn.close()
    return output.getvalue()


def _excel_bytes_to_db(excel_bytes, target_path):
    """Rebuild a valid SQLite database from the single Excel backup."""
    xls = pd.ExcelFile(io.BytesIO(excel_bytes), engine="openpyxl")
    required = {"customers", "orders", "daily_notes"}
    if not required.issubset(set(xls.sheet_names)):
        raise ValueError("ملف Excel لا يحتوي على جداول قاعدة البيانات المطلوبة.")

    if FilePath(target_path).exists():
        FilePath(target_path).unlink()

    conn = sqlite3.connect(target_path, timeout=30)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                order_details TEXT NOT NULL,
                order_date DATE DEFAULT CURRENT_DATE,
                total_cost REAL DEFAULT 0,
                deposit REAL DEFAULT 0,
                payment_status TEXT,
                order_status TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE daily_notes (
                note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_date DATE NOT NULL UNIQUE,
                note_text TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        for table in ("customers", "orders", "daily_notes"):
            df = pd.read_excel(xls, sheet_name=table, engine="openpyxl")
            df = df.where(pd.notna(df), None)
            if not df.empty:
                columns = list(df.columns)
                placeholders = ",".join(["?"] * len(columns))
                sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
                rows = [tuple(row) for row in df.itertuples(index=False, name=None)]
                cursor.executemany(sql, rows)

        conn.commit()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError("فشل فحص سلامة قاعدة البيانات بعد الاسترجاع.")
    finally:
        conn.close()


def drive_backup_db():
    """Upload ONE Excel file; every save replaces the same Drive file."""
    result = {"success": False, "error": None}
    if not drive_backup_configured():
        result["error"] = "النسخ الاحتياطي غير مُهيأ."
        return result
    db_file = FilePath(DB_NAME)
    if not db_file.exists():
        result["error"] = "ملف قاعدة البيانات غير موجود."
        return result
    try:
        excel_bytes = _db_to_excel_bytes()
        encoded = base64.b64encode(excel_bytes).decode("ascii")
        response = requests.post(
            DRIVE_BACKUP_URL,
            data={
                "action": "backup",
                "token": DRIVE_BACKUP_TOKEN,
                "filename": EXCEL_BACKUP_FILENAME,
                "data": encoded,
            },
            timeout=90,
        )
        payload = _json_response(response)
        if response.ok and payload.get("success"):
            result["success"] = True
            result["filename"] = EXCEL_BACKUP_FILENAME
        else:
            result["error"] = payload.get("error") or f"HTTP {response.status_code}"
    except Exception as exc:
        result["error"] = str(exc)
    return result


def drive_restore_latest():
    """Download the ONE Excel backup from Drive and rebuild SQLite."""
    result = {"success": False, "error": None}
    if not drive_backup_configured():
        result["error"] = "النسخ الاحتياطي غير مُهيأ."
        return result
    try:
        response = requests.get(
            DRIVE_BACKUP_URL,
            params={"action": "download", "token": DRIVE_BACKUP_TOKEN, "latest": "1"},
            timeout=90,
        )
        payload = _json_response(response)
        if not response.ok or not payload.get("success"):
            result["error"] = payload.get("error") or f"HTTP {response.status_code}"
            return result

        excel_bytes = base64.b64decode(payload.get("data", ""))
        temp_path = FilePath(DB_NAME + ".restore_tmp")
        _excel_bytes_to_db(excel_bytes, temp_path)

        db_file = FilePath(DB_NAME)
        if db_file.exists():
            shutil.copy2(
                db_file,
                f"print_shop_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            )
        shutil.move(str(temp_path), DB_NAME)
        result["success"] = True
        result["filename"] = payload.get("filename", EXCEL_BACKUP_FILENAME)
    except Exception as exc:
        try:
            FilePath(DB_NAME + ".restore_tmp").unlink(missing_ok=True)
        except Exception:
            pass
        result["error"] = str(exc)
    return result


def drive_backup_info():
    if not drive_backup_configured():
        return None
    try:
        response = requests.get(
            DRIVE_BACKUP_URL,
            params={"action": "status", "token": DRIVE_BACKUP_TOKEN},
            timeout=30,
        )
        payload = _json_response(response)
        if response.ok and payload.get("success"):
            return payload
    except Exception:
        pass
    return None


def backup_after_save():
    return drive_backup_db()


def restore_from_cloud():
    return drive_restore_latest()


if not FilePath(DB_NAME).exists():
    info = drive_backup_info()
    if info and info.get("found"):
        drive_restore_latest()

init_db()

# =========================================================
# DESIGN — "ink & paper ledger"
# Warm paper surface, charcoal ink, a single stamp-red accent.
# Two Arabic type families: Cairo (display/numbers) + IBM Plex
# Sans Arabic (body/labels), evoking a print-shop invoice book
# rather than a generic dark SaaS dashboard.
# =========================================================
def set_custom_design():

    background_css = ""
    if logo_b64:
        background_css = f"""
        .stApp::before {{
            content: "";
            position: fixed;
            inset: 0;
            background-image: url("data:image/jpg;base64,{logo_b64}");
            background-repeat: no-repeat;
            background-position: 108% 8%;
            background-size: min(420px, 40vw);
            opacity: 0.05;
            filter: grayscale(1);
            pointer-events: none;
            z-index: 0;
        }}
        """

    st.markdown(
        f"""
<style>

/* =========================================================
   CORE — original palette restored, box SHAPES redesigned
   (chamfered / ticket-stub cuts instead of plain rounded
   rectangles, punch-hole perforation on the stats strip,
   folded-corner "stamp" tab on section panels)
   ========================================================= */

html, body, [class*="css"] {{
    direction: rtl;
}}

.stApp {{
    background:
        radial-gradient(circle at 15% 15%, rgba(226,27,43,.10), transparent 28%),
        radial-gradient(circle at 85% 80%, rgba(55,75,110,.12), transparent 32%),
        linear-gradient(135deg, #060a12 0%, #0a111d 48%, #060a12 100%);
    color: #eef2f7;
}}

{background_css}

.main .block-container {{
    position: relative;
    z-index: 1;
    max-width: 1550px;
    padding-top: 1.2rem;
    padding-bottom: 2.5rem;
}}

#MainMenu, footer {{ visibility: hidden; }}
header {{ background: transparent !important; }}


/* =========================================================
   ANIMATIONS
   ========================================================= */
@keyframes pulseRed {{
    0%, 100% {{ box-shadow: 0 0 0 0 rgba(226,27,43,.20); }}
    50% {{ box-shadow: 0 0 0 8px rgba(226,27,43,0); }}
}}


/* =========================================================
   SIDEBAR
   ========================================================= */
section[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, #070c15 0%, #0a101b 55%, #060a12 100%) !important;
    border-left: 1px solid rgba(226,27,43,.65);
    box-shadow: -15px 0 45px rgba(0,0,0,.35);
    overflow: hidden !important;
}}

section[data-testid="stSidebar"] > div {{ padding: 1rem .85rem 1.5rem; }}
section[data-testid="stSidebar"] * {{ color: #f1f5f9 !important; }}

.brand-box {{
    padding: 6px 4px 18px;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 12px;
    border-bottom: 1px dashed rgba(148,163,184,.25);
}}

.brand-logo {{
    width: 54px;
    height: 54px;
    object-fit: cover;
    border: 1px solid rgba(255,255,255,.13);
    box-shadow: 0 12px 30px rgba(0,0,0,.45);
    clip-path: polygon(14% 0, 100% 0, 100% 86%, 86% 100%, 0 100%, 0 14%);
    flex-shrink: 0;
}}

.brand-mark {{
    width: 54px;
    height: 54px;
    border: 2px solid #e21b2b;
    color: #e21b2b;
    font-weight: 800;
    font-size: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    clip-path: polygon(14% 0, 100% 0, 100% 86%, 86% 100%, 0 100%, 0 14%);
    flex-shrink: 0;
}}

.brand-name {{ font-size: 19px; font-weight: 800; line-height: 1.3; }}
.brand-caption {{ color: #7f8da3 !important; font-size: 11px; margin-top: 2px; }}

.side-label {{ color: #69778b !important; font-size: 10px; margin: 13px 3px 7px; letter-spacing: .4px; }}

/* Radio-based nav styled as angled ticket-stub tabs */
section[data-testid="stSidebar"] div[role="radiogroup"] {{ gap: 4px; }}
section[data-testid="stSidebar"] div[role="radiogroup"] label {{
    padding: 11px 14px !important;
    border: 1px solid transparent;
    border-right: 3px solid transparent;
    transition: background .15s ease, border-color .15s ease;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
    background: rgba(226,27,43,.08);
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
    background: rgba(226,27,43,.12);
    border-right-color: #e21b2b;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label p {{
    font-size: 13.5px !important;
    font-weight: 600;
}}

.side-note {{
    background: linear-gradient(145deg, rgba(20,30,48,.94), rgba(9,15,26,.94));
    border: 1px solid rgba(148,163,184,.13);
    padding: 13px;
    margin-top: 12px;
    position: relative;
    clip-path: polygon(0 0, 100% 0, 100% 100%, 16px 100%, 0 calc(100% - 16px));
}}
.side-note-title {{ font-weight: 800; font-size: 13px; color: #f8fafc !important; }}
.side-note-date {{ font-size: 10px; color: #7f8da3 !important; margin-top: 3px; }}
.side-note-text {{ margin-top: 8px; font-size: 11px; line-height: 1.8; color: #b9c3d1 !important; white-space: pre-wrap; }}


/* =========================================================
   TOP BAR — clipped corner + pulsing spine, like a stamped
   docket header instead of a plain rounded banner
   ========================================================= */
.topbar {{
    background: linear-gradient(110deg, rgba(18,28,45,.92), rgba(8,14,25,.82));
    border: 1px solid rgba(148,163,184,.14);
    padding: 20px 26px;
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    direction: ltr;
    clip-path: polygon(30px 0, 100% 0, 100% 100%, 0 100%, 0 30px);
}}
.topbar::after {{
    content: "";
    position: absolute;
    top: 0; right: 0;
    width: 4px;
    height: 100%;
    background: linear-gradient(#ff2639, #a90e1e);
    animation: pulseRed 2.2s infinite;
}}
.topbar-title {{ font-size: 28px; font-weight: 800; color: #ffffff; line-height: 1.35; }}
.topbar-date {{ color: #8492a6; font-size: 12px; font-weight: 600; }}


/* =========================================================
   LEDGER STATS STRIP — perforated ticket-book divider
   (punch-hole circles instead of a row of separate shadow
   cards)
   ========================================================= */
.ledger {{
    display: flex;
    background: linear-gradient(145deg, rgba(20,31,50,.94), rgba(9,15,26,.92));
    border: 1px solid rgba(148,163,184,.12);
    margin-bottom: 22px;
    position: relative;
}}
.ledger-cell {{
    flex: 1;
    padding: 18px 20px;
    position: relative;
}}
.ledger-cell:not(:last-child) {{ border-left: 1px dashed rgba(148,163,184,.30); }}
.ledger-cell:not(:last-child)::before {{
    content: "";
    position: absolute;
    left: -6px; top: -7px;
    width: 12px; height: 12px;
    border-radius: 50%;
    background: #0a111d;
    border: 1px solid rgba(148,163,184,.28);
}}
.ledger-cell:not(:last-child)::after {{
    content: "";
    position: absolute;
    left: -6px; bottom: -7px;
    width: 12px; height: 12px;
    border-radius: 50%;
    background: #0a111d;
    border: 1px solid rgba(148,163,184,.28);
}}
.ledger-value {{ color: #f8fafc; font-size: 25px; font-weight: 800; }}
.ledger-label {{ color: #78869a; font-size: 11px; margin-top: 3px; }}


/* =========================================================
   PANELS — folded-corner "stamp tab" section headers
   ========================================================= */
.panel-head {{
    display: flex;
    align-items: center;
    gap: 14px;
    background: linear-gradient(145deg, rgba(17,28,46,.90), rgba(7,13,24,.86));
    border: 1px solid rgba(148,163,184,.13);
    padding: 15px 22px;
    margin-bottom: 18px;
    box-shadow: 0 14px 40px rgba(0,0,0,.20);
    position: relative;
    clip-path: polygon(0 0, calc(100% - 24px) 0, 100% 24px, 100% 100%, 0 100%);
}}
.panel-head::before {{
    content: "";
    position: absolute;
    top: 0; right: 0;
    width: 0; height: 0;
    border-style: solid;
    border-width: 0 24px 24px 0;
    border-color: transparent #e21b2b transparent transparent;
    opacity: .85;
}}
.panel-title {{ font-size: 19px; font-weight: 800; color: #f8fafc; }}
.panel-rule {{
    flex: 1;
    height: 1px;
    background: repeating-linear-gradient(90deg, rgba(148,163,184,.35) 0 6px, transparent 6px 13px);
}}
.mini-title {{ color: #d8dee8; font-size: 14px; font-weight: 800; margin-bottom: 9px; }}


/* =========================================================
   PAYMENT BADGES — chamfered ticket-stub corners, high
   contrast for the outstanding balance
   ========================================================= */
.badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 10px 18px;
    font-weight: 700;
    font-size: 14px;
    line-height: 1.4;
    clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
}}
.badge-unpaid {{ background: rgba(239,68,68,.14); color: #f87171; border: 1px solid rgba(239,68,68,.35); }}
.badge-partial {{ background: rgba(245,158,11,.14); color: #fbbf24; border: 1px solid rgba(245,158,11,.35); }}
.badge-paid {{ background: rgba(34,197,94,.14); color: #4ade80; border: 1px solid rgba(34,197,94,.35); }}
.badge-neutral {{ background: rgba(148,163,184,.10); color: #9aa7ba; border: 1px solid rgba(148,163,184,.20); }}
.badge strong {{ font-size: 15px; }}


/* =========================================================
   INPUTS
   ========================================================= */
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div,
div[data-baseweb="select"] > div {{
    background: #0d1728 !important;
    border: 1px solid #26364f !important;
    border-radius: 10px !important;
    transition: border-color .2s ease, box-shadow .2s ease;
}}
div[data-baseweb="input"] > div:focus-within,
div[data-baseweb="textarea"] > div:focus-within,
div[data-baseweb="select"] > div:focus-within {{
    border-color: rgba(226,27,43,.65) !important;
    box-shadow: 0 0 0 3px rgba(226,27,43,.08);
}}
input, textarea {{ color: #f8fafc !important; }}
input::placeholder, textarea::placeholder {{ color: #536176 !important; }}
label {{ color: #cbd5e1 !important; font-size: 12px !important; font-weight: 600 !important; }}


/* =========================================================
   BUTTONS — chamfered corners, ticket-stub silhouette
   ========================================================= */
.stButton > button, .stFormSubmitButton > button {{
    border: 0 !important;
    min-height: 44px;
    background: linear-gradient(135deg, #f21f33, #bc1021) !important;
    color: #fff !important;
    font-weight: 800 !important;
    transition: transform .2s ease, box-shadow .2s ease, filter .2s ease;
    clip-path: polygon(14px 0, 100% 0, 100% calc(100% - 14px), calc(100% - 14px) 100%, 0 100%, 0 14px);
}}
.stButton > button:hover, .stFormSubmitButton > button:hover {{
    transform: translateY(-2px);
    filter: brightness(1.08);
    box-shadow: 0 12px 28px rgba(226,27,43,.28);
}}


/* =========================================================
   DATAFRAME
   ========================================================= */
[data-testid="stDataFrame"] {{
    border: 1px solid rgba(148,163,184,.15);
    border-radius: 14px;
    overflow: hidden;
}}

div[data-testid="stAlert"] {{ border-radius: 11px; }}
hr {{ border-color: rgba(148,163,184,.10) !important; }}


/* =========================================================
   FOOTER
   ========================================================= */
.footer {{
    text-align: center;
    color: #465267;
    font-size: 10px;
    padding: 24px 0 4px;
}}
.footer strong {{ color: #e21b2b; }}


/* =========================================================
   MOBILE FIXES
   ========================================================= */
@media (max-width: 768px) {{
    .topbar-title {{ font-size: 20px; }}
    .panel-title {{ font-size: 17px; }}
    div[data-testid="stHorizontalBlock"] {{
        flex-wrap: wrap !important;
        gap: 0.6rem;
    }}
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
        flex: 1 1 100% !important;
        min-width: 100% !important;
        width: 100% !important;
    }}
    .ledger {{ flex-wrap: wrap; }}
    .ledger-cell {{ flex: 1 1 50%; }}
    .ledger-value {{ font-size: 22px; }}
    section[data-testid="stSidebar"][aria-expanded="false"] {{ visibility: hidden; }}
}}

</style>""",
        unsafe_allow_html=True,
    )


set_custom_design()

# =========================================================
# HELPERS
# =========================================================
def calculate_payment(total, deposit):
    if total > 0 and deposit >= total:
        return "تم الدفع بالكامل"
    if deposit > 0:
        return f"تم دفع عربون — المتبقي: {total - deposit:,.2f} ج"
    return "لم يدفع"


def payment_badge_html(total, deposit):
    """A clearly-colored badge: red = unpaid, amber = remaining balance, green = paid in full."""
    total = total or 0
    deposit = deposit or 0
    if total <= 0:
        return '<span class="badge badge-neutral">لا توجد تكلفة مسجّلة بعد</span>'
    remaining = total - deposit
    if deposit <= 0:
        return f'<span class="badge badge-unpaid">لم يُدفع شيء — <strong>{total:,.0f} ج</strong> مستحقة</span>'
    if remaining <= 0:
        return '<span class="badge badge-paid">✓ تم الدفع بالكامل</span>'
    return f'<span class="badge badge-partial">المتبقي <strong>{remaining:,.0f} ج</strong> — من إجمالي {total:,.0f} ج</span>'


def style_payment_cell(val):
    if val == "لم يدفع":
        return f"color:{'#A8142B'}; font-weight:700;"
    if isinstance(val, str) and val.startswith("تم دفع عربون"):
        return "color:#9C6B0B; font-weight:700;"
    if val == "تم الدفع بالكامل":
        return "color:#1F6E44; font-weight:700;"
    return ""


def style_remaining_cell(val):
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    if v > 0:
        return "color:#9C6B0B; font-weight:800;"
    return "color:#1F6E44; font-weight:700;"


def get_statistics():
    conn = get_connection()
    df = pd.read_sql_query("SELECT total_cost, order_status FROM orders", conn)
    conn.close()

    if df.empty:
        return 0, 0, 0, 0

    return (
        len(df),
        int((df["order_status"] == "تم التسليم").sum()),
        int((df["order_status"] == "قيد التنفيذ").sum()),
        float(df["total_cost"].fillna(0).sum()),
    )


def get_today_note():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT note_text FROM daily_notes WHERE note_date = ?",
        (date.today().isoformat(),)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""


def save_today_note(note_text):
    conn = get_connection()
    cursor = conn.cursor()
    today = date.today().isoformat()
    cursor.execute("""
        INSERT INTO daily_notes (note_date, note_text, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(note_date)
        DO UPDATE SET
            note_text = excluded.note_text,
            updated_at = CURRENT_TIMESTAMP
    """, (today, note_text))
    conn.commit()
    conn.close()


def get_recent_notes(limit=5):
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT note_date, note_text
        FROM daily_notes
        WHERE TRIM(note_text) <> ''
        ORDER BY note_date DESC
        LIMIT ?
        """,
        conn,
        params=(limit,)
    )
    conn.close()
    return df


# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:

    if logo_b64:
        st.markdown(
            f"""
            <div class="brand-box">
                <img class="brand-logo" src="data:image/jpeg;base64,{logo_b64}">
                <div>
                    <div class="brand-name">ZERO PLUS</div>
                    <div class="brand-caption">طباعة وتصميم وإعلان</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <div class="brand-box">
                <div class="brand-mark">Z</div>
                <div>
                    <div class="brand-name">ZERO PLUS</div>
                    <div class="brand-caption">طباعة وتصميم وإعلان</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown('<div class="side-label">القائمة الرئيسية</div>', unsafe_allow_html=True)

    menu = [
        "➕  تسجيل طلب جديد",
        "📋  عرض واستعلام الطلبات",
        "⚙️  تحديث حالة طلب",
        "📝  المفكرة اليومية",
        "☁️  النسخ الاحتياطي (Google Drive)",
    ]

    choice = st.radio("القائمة", menu, label_visibility="collapsed")

    today_note = get_today_note()

    if today_note:
        preview = today_note[:150]
        if len(today_note) > 150:
            preview += "..."
        st.markdown(
            f"""
            <div class="side-note">
                <div class="side-note-title">📌 ملاحظة اليوم</div>
                <div class="side-note-date">{date.today().strftime("%Y-%m-%d")}</div>
                <div class="side-note-text">{preview}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <div class="side-note">
                <div class="side-note-title">📌 مفيش ملاحظات</div>
                <div class="side-note-date">اكتب واحدة من المفكرة اليومية</div>
            </div>
            """,
            unsafe_allow_html=True
        )

# =========================================================
# TOP BAR
# =========================================================
today_text = date.today().strftime("%Y-%m-%d")

st.markdown(
    f"""
    <div class="topbar">
        <div class="topbar-title">ZERO Advertising</div>
        <div class="topbar-date">{today_text}</div>
    </div>
    """,
    unsafe_allow_html=True
)

# =========================================================
# DASHBOARD STATS
# =========================================================
total_orders, completed, in_progress, total_sales = get_statistics()

stats = [
    ("إجمالي الطلبات", total_orders),
    ("قيد التنفيذ", in_progress),
    ("تم التسليم", completed),
    ("إجمالي قيمة الطلبات", f"{total_sales:,.0f} ج"),
]

ledger_html = '<div class="ledger">'
for title, value in stats:
    ledger_html += f"""
        <div class="ledger-cell">
            <div class="ledger-value">{value}</div>
            <div class="ledger-label">{title}</div>
        </div>
    """
ledger_html += "</div>"

st.markdown(ledger_html, unsafe_allow_html=True)

# =========================================================
# 1. NEW ORDER
# =========================================================
if choice == "➕  تسجيل طلب جديد":

    st.markdown(
        """
        <div class="panel-head">
            <div class="panel-title">تسجيل طلب جديد</div>
            <div class="panel-rule"></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    with st.form("add_order_form", clear_on_submit=True):

        col1, col2, col3 = st.columns(3)

        with col1:
            customer_name = st.text_input("اسم العميل *", placeholder="مثال: أحمد محمد")
            customer_phone = st.text_input("رقم التليفون", placeholder="01XXXXXXXXX")

        with col2:
            order_details = st.text_area(
                "تفاصيل الطلب *",
                placeholder="مثال: 500 فلاير — مقاس A5 — وجهين — ألوان...",
                height=155
            )

        with col3:
            total_cost = st.number_input(
                "التكلفة الإجمالية (جنيه)",
                min_value=0.0,
                step=25.0,
                value=None,
                placeholder="0",
            )
            deposit = st.number_input(
                "المبلغ المدفوع / العربون",
                min_value=0.0,
                step=25.0,
                value=None,
                placeholder="0",
            )
            order_status = st.selectbox(
                "حالة الطلب",
                ["قيد التنفيذ", "جاهز للتسليم", "تم التسليم"]
            )

        total_cost_val = total_cost or 0.0
        deposit_val = deposit or 0.0

        st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)

        if deposit_val > total_cost_val and total_cost_val > 0:
            st.markdown(
                '<span class="badge badge-unpaid">⚠ العربون أكبر من إجمالي قيمة الطلب</span>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(payment_badge_html(total_cost_val, deposit_val), unsafe_allow_html=True)

        save = st.form_submit_button("💾  حفظ الطلب", use_container_width=True)

        if save:

            if not customer_name.strip():
                st.error("اكتب اسم العميل.")
            elif not order_details.strip():
                st.error("اكتب تفاصيل الطلب.")
            elif deposit_val > total_cost_val and total_cost_val > 0:
                st.error("العربون لا يمكن أن يكون أكبر من إجمالي الطلب.")
            else:
                payment_status = calculate_payment(total_cost_val, deposit_val)

                conn = get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    "INSERT INTO customers (name, phone) VALUES (?, ?)",
                    (customer_name.strip(), customer_phone.strip())
                )
                customer_id = cursor.lastrowid

                cursor.execute(
                    """
                    INSERT INTO orders
                    (customer_id, order_details, total_cost, deposit, payment_status, order_status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (customer_id, order_details.strip(), total_cost_val, deposit_val, payment_status, order_status)
                )

                conn.commit()
                conn.close()

                backup_result = backup_after_save()

                st.success(f"تم حفظ طلب العميل «{customer_name}» بنجاح.")
                if not backup_result["success"]:
                    st.warning("الداتا اتحفظت، لكن حصلت مشكلة في المزامنة السحابية: " + str(backup_result["error"]))

# =========================================================
# 2. ORDERS
# =========================================================
elif choice == "📋  عرض واستعلام الطلبات":

    st.markdown(
        """
        <div class="panel-head">
            <div class="panel-title">الطلبات المسجلة</div>
            <div class="panel-rule"></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT
            o.order_id AS 'رقم الطلب',
            c.name AS 'اسم العميل',
            c.phone AS 'التليفون',
            o.order_details AS 'التفاصيل',
            o.total_cost AS 'الإجمالي',
            o.deposit AS 'العربون',
            o.payment_status AS 'حالة الدفع',
            o.order_status AS 'حالة الطلب',
            o.order_date AS 'تاريخ الطلب'
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        ORDER BY o.order_id DESC
        """,
        conn
    )
    conn.close()

    if df.empty:
        st.info("لا توجد طلبات مسجلة حالياً.")
    else:
        search_col, filter_col = st.columns(2)

        with search_col:
            search_name = st.text_input("🔍 البحث", placeholder="ابحث باسم العميل...")

        with filter_col:
            status_filter = st.selectbox(
                "📌 حالة الطلب",
                ["الكل", "قيد التنفيذ", "جاهز للتسليم", "تم التسليم"]
            )

        if search_name:
            df = df[df["اسم العميل"].str.contains(search_name, case=False, na=False)]

        if status_filter != "الكل":
            df = df[df["حالة الطلب"] == status_filter]

        df["المتبقي"] = (df["الإجمالي"].fillna(0) - df["العربون"].fillna(0)).clip(lower=0)

        styled = (
            df.style
            .format({"الإجمالي": "{:,.2f} ج", "العربون": "{:,.2f} ج", "المتبقي": "{:,.2f} ج"})
            .map(style_payment_cell, subset=["حالة الدفع"])
            .map(style_remaining_cell, subset=["المتبقي"])
        )

        st.dataframe(styled, use_container_width=True, hide_index=True, height=520)
        st.caption(f"عدد النتائج: {len(df)}")

# =========================================================
# 3. UPDATE ORDER
# =========================================================
elif choice == "⚙️  تحديث حالة طلب":

    st.markdown(
        """
        <div class="panel-head">
            <div class="panel-title">تحديث حالة طلب</div>
            <div class="panel-rule"></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT o.order_id, c.name
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        ORDER BY o.order_id DESC
        """
    )
    orders = cursor.fetchall()

    if not orders:
        st.info("لا توجد طلبات لتعديلها.")
    else:
        options = {f"طلب #{order_id} — {name}": order_id for order_id, name in orders}
        selected_label = st.selectbox("📌 اختر الطلب", list(options.keys()))
        selected_id = options[selected_label]

        cursor.execute(
            "SELECT total_cost, deposit, payment_status, order_status FROM orders WHERE order_id = ?",
            (selected_id,)
        )
        current = cursor.fetchone()

        col1, col2 = st.columns(2)

        with col1:
            st.markdown('<div class="panel-title" style="font-size:15px;margin-bottom:10px">💰 الحساب</div>', unsafe_allow_html=True)

            total_cost = float(current[0] or 0)

            new_deposit = st.number_input(
                "المبلغ المدفوع",
                min_value=0.0,
                value=float(current[1] or 0),
                step=25.0,
            )

            if new_deposit > total_cost and total_cost > 0:
                st.markdown('<span class="badge badge-unpaid">⚠ المبلغ المدفوع أكبر من قيمة الطلب</span>', unsafe_allow_html=True)
                new_payment_status = current[2]
            else:
                new_payment_status = calculate_payment(total_cost, new_deposit)
                st.markdown(payment_badge_html(total_cost, new_deposit), unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="panel-title" style="font-size:15px;margin-bottom:10px">📦 التنفيذ</div>', unsafe_allow_html=True)

            statuses = ["قيد التنفيذ", "جاهز للتسليم", "تم التسليم"]
            current_status = current[3]
            if current_status not in statuses:
                current_status = statuses[0]

            new_order_status = st.selectbox(
                "حالة الطلب الجديدة",
                statuses,
                index=statuses.index(current_status)
            )

        if st.button("🔄  حفظ التعديلات", use_container_width=True):

            if new_deposit > total_cost and total_cost > 0:
                st.error("لا يمكن دفع مبلغ أكبر من قيمة الطلب.")
            else:
                cursor.execute(
                    """
                    UPDATE orders
                    SET deposit = ?, payment_status = ?, order_status = ?
                    WHERE order_id = ?
                    """,
                    (new_deposit, new_payment_status, new_order_status, selected_id)
                )
                conn.commit()
                conn.close()

                backup_result = backup_after_save()

                st.success("تم تحديث الطلب بنجاح.")
                if not backup_result["success"]:
                    st.warning("التحديث اتحفظ، لكن حصلت مشكلة في المزامنة السحابية: " + str(backup_result["error"]))
                st.rerun()

    conn.close()

# =========================================================
# 4. DAILY NOTEBOOK
# =========================================================
elif choice == "📝  المفكرة اليومية":

    today = date.today()
    today_iso = today.isoformat()

    st.markdown(
        f"""
        <div class="panel-head">
            <div class="panel-title">ملاحظة يوم {today_iso}</div>
            <div class="panel-rule"></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    current_note = get_today_note()

    note = st.text_area(
        "اكتب ملاحظتك هنا",
        value=current_note,
        height=260,
        label_visibility="collapsed",
        placeholder=(
            "مثال:\n"
            "• أحمد يستلم البانر الساعة 5\n"
            "• مراجعة تصميم محل الملابس\n"
            "• شراء خامة فينيل\n"
            "• الاتصال بالعميل محمد..."
        )
    )

    if st.button("💾  حفظ ملاحظة اليوم", use_container_width=True):
        save_today_note(note.strip())
        backup_result = backup_after_save()

        st.success(f"تم حفظ ملاحظة يوم {today_iso}.")
        if not backup_result["success"]:
            st.warning("الملاحظة اتحفظت، لكن حصلت مشكلة في المزامنة السحابية: " + str(backup_result["error"]))
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    recent = get_recent_notes(10)

    if not recent.empty:
        st.markdown(
            """
            <div class="panel-head">
                <div class="panel-title">الملاحظات السابقة</div>
                <div class="panel-rule"></div>
            </div>
            """,
            unsafe_allow_html=True
        )

        for _, row in recent.iterrows():
            with st.expander(f"📅 {row['note_date']}"):
                st.write(row["note_text"])

# =========================================================
# 5. CLOUD BACKUP (Google Drive)
# =========================================================
elif choice == "☁️  النسخ الاحتياطي (Google Drive)":

    st.markdown(
        """
        <div class="panel-head">
            <div class="panel-title">حماية البيانات — Google Drive</div>
            <div class="panel-rule"></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if not drive_backup_configured():
        st.error("النسخ الاحتياطي غير مُهيأ.")
        st.markdown("**الإعداد لأول مرة:**")
        st.markdown(
            """
            1. Google Apps Script → مشروع جديد → الصق كود google_drive_backup_apps_script.gs
            2. Deploy → New deployment → Web app — Execute as: **Me**, Access: **Anyone**
            3. انسخ الـ Web app URL والسر، وضعهما في Streamlit Secrets
            """
        )
    else:
        st.success("Google Drive Backup متصل.")

        db_file = FilePath(DB_NAME)
        if db_file.exists():
            db_size = db_file.stat().st_size / 1024
            st.caption(f"قاعدة البيانات الحالية: `{DB_NAME}` — {db_size:.1f} KB")

        remote = drive_backup_info()
        if remote and remote.get("found"):
            st.caption("☁️ آخر نسخة: " + str(remote.get("filename", "غير معروف")))
        else:
            st.caption("لا توجد نسخة احتياطية على Google Drive حتى الآن.")

        if st.button("☁️ عمل Backup الآن", use_container_width=True):
            with st.spinner("جاري رفع النسخة..."):
                result = drive_backup_db()
            if result["success"]:
                st.success("تم رفع النسخة بنجاح إلى Google Drive.")
            else:
                st.error("فشل النسخ الاحتياطي: " + str(result["error"]))

        st.markdown("<br>", unsafe_allow_html=True)
        st.warning("الاسترجاع سيستبدل قاعدة البيانات الحالية بآخر Backup موجود على Google Drive.")

        if st.button("🔄 استرجاع آخر Backup", use_container_width=True):
            with st.spinner("جاري تنزيل وفحص النسخة..."):
                result = drive_restore_latest()
            if result["success"]:
                st.success("تم الاسترجاع: " + str(result.get("filename", "latest backup")))
                st.rerun()
            else:
                st.error("فشل الاسترجاع: " + str(result["error"]))

# =========================================================
# FOOTER
# =========================================================
st.markdown(
    """
    <div class="footer">
        نظام إدارة ZERO Advertising
        <br>
        <strong>طباعة وتصميم وإعلان</strong>
    </div>
    """,
    unsafe_allow_html=True
)
