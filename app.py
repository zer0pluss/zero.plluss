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

@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@500;700;800;900&family=IBM+Plex+Sans+Arabic:wght@400;500;600&display=swap');

/* =========================================================
   TOKENS
   ========================================================= */
:root {{
    --paper: #F6F3EC;
    --panel: #FFFFFF;
    --ink: #201C17;
    --ink-soft: #6B6255;
    --hairline: #E4DDCE;
    --stamp: #A8142B;
    --stamp-soft: rgba(168,20,43,.09);
    --gold: #9C7A2E;
    --good: #1F6E44;
    --good-soft: rgba(31,110,68,.10);
    --warn: #9C6B0B;
    --warn-soft: rgba(156,107,11,.12);
    --bad: #A8142B;
    --bad-soft: rgba(168,20,43,.09);
}}

html, body, [class*="css"] {{
    direction: rtl;
    font-family: 'IBM Plex Sans Arabic', 'Cairo', sans-serif;
}}

.stApp {{
    background: var(--paper);
    color: var(--ink);
    background-image:
        linear-gradient(var(--paper), var(--paper)),
        repeating-linear-gradient(0deg, rgba(32,28,23,.018) 0px, rgba(32,28,23,.018) 1px, transparent 1px, transparent 34px);
}}

{background_css}

.main .block-container {{
    position: relative;
    z-index: 1;
    max-width: 1480px;
    padding-top: 1rem;
    padding-bottom: 2.5rem;
}}

#MainMenu, footer {{ visibility: hidden; }}
header {{ background: transparent !important; }}

h1, h2, h3, h4, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
    font-family: 'Cairo', sans-serif;
    color: var(--ink);
}}


/* =========================================================
   SIDEBAR
   ========================================================= */
section[data-testid="stSidebar"] {{
    background: var(--panel) !important;
    border-left: 1px solid var(--hairline);
}}

section[data-testid="stSidebar"] > div {{
    padding: 1.1rem .9rem 1.5rem;
}}

section[data-testid="stSidebar"] * {{
    color: var(--ink) !important;
}}

.brand-box {{
    padding: 6px 4px 18px;
    border-bottom: 1px solid var(--hairline);
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 12px;
}}

.brand-logo {{
    width: 52px;
    height: 52px;
    object-fit: cover;
    border-radius: 8px;
    border: 1px solid var(--hairline);
    flex-shrink: 0;
}}

.brand-mark {{
    width: 52px;
    height: 52px;
    border-radius: 8px;
    border: 2px solid var(--stamp);
    color: var(--stamp);
    font-family: 'Cairo', sans-serif;
    font-weight: 900;
    font-size: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}}

.brand-name {{
    font-family: 'Cairo', sans-serif;
    font-size: 17px;
    font-weight: 800;
    line-height: 1.3;
}}

.brand-caption {{
    color: var(--ink-soft) !important;
    font-size: 11px;
    margin-top: 1px;
}}

.side-label {{
    color: var(--ink-soft) !important;
    font-size: 11px;
    font-weight: 600;
    margin: 4px 3px 8px;
}}

/* Radio-based nav styled as a menu list */
section[data-testid="stSidebar"] div[role="radiogroup"] {{
    gap: 3px;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label {{
    padding: 10px 12px !important;
    border-radius: 8px;
    border: 1px solid transparent;
    transition: background .12s ease, border-color .12s ease;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
    background: var(--stamp-soft);
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
    background: var(--stamp-soft);
    border-color: rgba(168,20,43,.25);
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label p {{
    font-size: 13.5px !important;
    font-weight: 600;
}}

.side-note {{
    background: var(--paper);
    border: 1px solid var(--hairline);
    border-radius: 10px;
    padding: 12px 13px;
    margin-top: 16px;
}}
.side-note-title {{
    font-weight: 700;
    font-size: 12.5px;
    color: var(--ink) !important;
}}
.side-note-date {{
    font-size: 10.5px;
    color: var(--ink-soft) !important;
    margin-top: 2px;
}}
.side-note-text {{
    margin-top: 7px;
    font-size: 11.5px;
    line-height: 1.75;
    color: #4A4438 !important;
    white-space: pre-wrap;
}}


/* =========================================================
   TOP BAR
   ========================================================= */
.topbar {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    padding-bottom: 14px;
    margin-bottom: 18px;
    border-bottom: 2px solid var(--ink);
}}
.topbar-title {{
    font-family: 'Cairo', sans-serif;
    font-size: 26px;
    font-weight: 800;
    color: var(--ink);
    letter-spacing: .2px;
}}
.topbar-date {{
    font-family: 'Cairo', sans-serif;
    font-size: 13px;
    color: var(--ink-soft);
    font-weight: 600;
}}


/* =========================================================
   LEDGER STATS STRIP
   ========================================================= */
.ledger {{
    display: flex;
    border: 1px solid var(--hairline);
    border-radius: 12px;
    background: var(--panel);
    overflow: hidden;
    margin-bottom: 22px;
}}
.ledger-cell {{
    flex: 1;
    padding: 16px 20px;
    border-left: 1px solid var(--hairline);
}}
.ledger-cell:last-child {{ border-left: none; }}
.ledger-value {{
    font-family: 'Cairo', sans-serif;
    font-size: 26px;
    font-weight: 800;
    color: var(--ink);
}}
.ledger-label {{
    font-size: 11.5px;
    color: var(--ink-soft);
    margin-top: 3px;
}}


/* =========================================================
   PANELS
   ========================================================= */
.panel-head {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 14px;
}}
.panel-title {{
    font-family: 'Cairo', sans-serif;
    font-size: 18px;
    font-weight: 800;
    color: var(--ink);
}}
.panel-rule {{
    flex: 1;
    height: 1px;
    background: var(--hairline);
}}


/* =========================================================
   PAYMENT BADGES
   ========================================================= */
.badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 10px 16px;
    border-radius: 8px;
    font-weight: 700;
    font-size: 14px;
    line-height: 1.4;
}}
.badge-unpaid {{ background: var(--bad-soft); color: var(--bad); border: 1px solid rgba(168,20,43,.30); }}
.badge-partial {{ background: var(--warn-soft); color: var(--warn); border: 1px solid rgba(156,107,11,.30); }}
.badge-paid {{ background: var(--good-soft); color: var(--good); border: 1px solid rgba(31,110,68,.30); }}
.badge-neutral {{ background: #F1EDE2; color: var(--ink-soft); border: 1px solid var(--hairline); }}
.badge strong {{ font-family: 'Cairo', sans-serif; }}


/* =========================================================
   INPUTS
   ========================================================= */
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div,
div[data-baseweb="select"] > div {{
    background: var(--panel) !important;
    border: 1px solid var(--hairline) !important;
    border-radius: 8px !important;
    transition: border-color .15s ease, box-shadow .15s ease;
}}
div[data-baseweb="input"] > div:focus-within,
div[data-baseweb="textarea"] > div:focus-within,
div[data-baseweb="select"] > div:focus-within {{
    border-color: var(--stamp) !important;
    box-shadow: 0 0 0 3px rgba(168,20,43,.08);
}}
input, textarea {{ color: var(--ink) !important; }}
input::placeholder, textarea::placeholder {{ color: #A69C89 !important; }}
label, .stNumberInput label, .stTextInput label, .stTextArea label, .stSelectbox label {{
    color: #4A4438 !important;
    font-size: 12.5px !important;
    font-weight: 600 !important;
}}


/* =========================================================
   BUTTONS
   ========================================================= */
.stButton > button, .stFormSubmitButton > button {{
    border: 1px solid var(--stamp) !important;
    border-radius: 8px !important;
    min-height: 44px;
    background: var(--stamp) !important;
    color: #FBF8F2 !important;
    font-weight: 700 !important;
    font-family: 'Cairo', sans-serif;
    transition: filter .15s ease, transform .1s ease;
}}
.stButton > button:hover, .stFormSubmitButton > button:hover {{
    filter: brightness(1.08);
}}
.stButton > button:active, .stFormSubmitButton > button:active {{
    transform: translateY(1px);
}}


/* =========================================================
   DATAFRAME
   ========================================================= */
[data-testid="stDataFrame"] {{
    border: 1px solid var(--hairline);
    border-radius: 10px;
    overflow: hidden;
}}

div[data-testid="stAlert"] {{ border-radius: 8px; }}
hr {{ border-color: var(--hairline) !important; }}


/* =========================================================
   FOOTER
   ========================================================= */
.footer {{
    text-align: center;
    color: var(--ink-soft);
    font-size: 10.5px;
    padding: 26px 0 4px;
    border-top: 1px solid var(--hairline);
    margin-top: 10px;
    padding-top: 14px;
}}
.footer strong {{ color: var(--stamp); }}


/* =========================================================
   MOBILE
   ========================================================= */
@media (max-width: 768px) {{
    .topbar-title {{ font-size: 20px; }}
    .panel-title {{ font-size: 16px; }}
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
    .ledger-cell {{ flex: 1 1 50%; border-bottom: 1px solid var(--hairline); }}
    .ledger-value {{ font-size: 21px; }}
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
