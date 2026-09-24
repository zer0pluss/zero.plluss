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
    initial_sidebar_state="collapsed",  # مهم جداً للموبايل
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
                # Excel sheet names are limited to 31 chars; these are all safe.
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

    # Build a fresh database using the same schema, then insert the rows.
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
            # Convert NaN to None so SQLite stores SQL NULLs cleanly.
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
# CSS / PREMIUM DESIGN
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
            background-position: 20% 30%;
            background-size: min(1000px, 65vw);
            opacity: 0.06;
            filter: none;
            pointer-events: none;
            z-index: 0;
        }}
        """

    st.markdown(
        f"""
<style>

@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Tajawal:wght@400;500;700&display=swap');

/* =========================================================
   CORE
   ========================================================= */

* {{
    font-family: 'Cairo', 'Tajawal', -apple-system, sans-serif !important;
}}

html, body, [class*="css"] {{
    direction: rtl;
}}

:root {{
    --gold: #f0b429;
    --gold-soft: rgba(240,180,41,.14);
    --red: #e2172c;
    --red-2: #9c0e1f;
    --green: #22c55e;
    --green-soft: rgba(34,197,94,.14);
    --ink: #eef2f7;
    --muted: #7c8aa0;
    --surface: rgba(15,23,38,.92);
    --surface-2: rgba(10,16,27,.88);
    --line: rgba(148,163,184,.14);
}}

.stApp {{
    background:
        radial-gradient(circle at 12% 8%, rgba(226,23,44,.13), transparent 30%),
        radial-gradient(circle at 90% 12%, rgba(240,180,41,.07), transparent 28%),
        radial-gradient(circle at 85% 85%, rgba(55,75,110,.14), transparent 32%),
        linear-gradient(150deg, #05080f 0%, #090f1c 45%, #05080f 100%);
    color: var(--ink);
}}

{background_css}

.main .block-container {{
    position: relative;
    z-index: 1;
    max-width: 1550px;
    padding-top: 1.1rem;
    padding-bottom: 2.5rem;
}}

#MainMenu,
footer {{
    visibility: hidden;
}}

header {{
    background: transparent !important;
}}

::-webkit-scrollbar {{
    width: 10px;
    height: 10px;
}}
::-webkit-scrollbar-track {{
    background: transparent;
}}
::-webkit-scrollbar-thumb {{
    background: linear-gradient(180deg, var(--red), var(--red-2));
    border-radius: 10px;
}}


/* =========================================================
   ANIMATIONS
   ========================================================= */

@keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(16px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}

@keyframes glow {{
    0%, 100% {{ box-shadow: 0 0 0 0 rgba(240,180,41,.18); }}
    50% {{ box-shadow: 0 0 0 7px rgba(240,180,41,0); }}
}}

.fade-up {{ animation: fadeUp .5s ease both; }}


/* =========================================================
   SIDEBAR
   ========================================================= */

section[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, #060a13 0%, #090e19 55%, #05080f 100%) !important;
    border-left: 1px solid rgba(226,23,44,.55);
    box-shadow: -18px 0 50px rgba(0,0,0,.4);
}}

section[data-testid="stSidebar"] > div {{
    padding: 1rem .85rem 1.5rem;
}}

section[data-testid="stSidebar"] * {{
    color: #f1f5f9 !important;
}}

.brand-box {{
    text-align: center;
    padding: 10px 4px 18px;
}}

.brand-logo {{
    width: 108px;
    height: 108px;
    object-fit: cover;
    border-radius: 20px;
    border: 1px solid rgba(240,180,41,.35);
    box-shadow: 0 18px 45px rgba(0,0,0,.5), 0 0 0 4px rgba(226,23,44,.08);
    animation: fadeUp .55s ease both;
}}

.brand-name {{
    font-size: 20px;
    font-weight: 900;
    margin-top: 12px;
    letter-spacing: .5px;
    background: linear-gradient(90deg, #ffffff, var(--gold));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}}

.brand-caption {{
    color: var(--muted) !important;
    font-size: 10.5px;
    margin-top: 3px;
    letter-spacing: 1.5px;
}}

.side-label {{
    color: #5e6c81 !important;
    font-size: 10px;
    font-weight: 700;
    margin: 15px 3px 8px;
    letter-spacing: .6px;
}}

.side-note {{
    background: linear-gradient(150deg, rgba(22,32,52,.95), rgba(8,13,23,.95));
    border: 1px solid var(--line);
    border-left: 3px solid var(--gold);
    border-radius: 14px;
    padding: 14px;
    margin-top: 12px;
}}

.side-note-title {{
    font-weight: 800;
    font-size: 12.5px;
    color: #f8fafc !important;
}}

.side-note-date {{
    font-size: 10px;
    color: var(--muted) !important;
    margin-top: 3px;
}}

.side-note-text {{
    margin-top: 8px;
    font-size: 11px;
    line-height: 1.8;
    color: #aeb9c9 !important;
    white-space: pre-wrap;
}}


/* =========================================================
   HEADER
   ========================================================= */

.hero {{
    background: linear-gradient(115deg, rgba(20,30,49,.94), rgba(7,12,22,.85));
    border: 1px solid var(--line);
    border-radius: 22px;
    padding: 22px 26px;
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
    animation: fadeUp .45s ease both;
}}

.hero::after {{
    content: "";
    position: absolute;
    top: 0; right: 0;
    width: 4px; height: 100%;
    background: linear-gradient(var(--gold), var(--red));
    animation: glow 2.4s infinite;
}}

.hero-eyebrow {{
    color: var(--gold);
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 2px;
    margin-bottom: 4px;
}}

.hero-title {{
    font-size: 27px;
    font-weight: 900;
    color: #ffffff;
    line-height: 1.3;
}}

.hero-sub {{
    color: var(--muted);
    font-size: 12px;
    margin-top: 4px;
}}


/* =========================================================
   STAT CARDS
   ========================================================= */

.stat-card {{
    background: linear-gradient(150deg, rgba(21,32,52,.95), rgba(8,13,23,.92));
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 18px 19px;
    min-height: 116px;
    position: relative;
    overflow: hidden;
    transition: transform .25s ease, border-color .25s ease, box-shadow .25s ease;
    animation: fadeUp .55s ease both;
}}

.stat-card:hover {{
    transform: translateY(-5px);
    border-color: rgba(240,180,41,.4);
    box-shadow: 0 18px 38px rgba(0,0,0,.32);
}}

.stat-card::before {{
    content: "";
    position: absolute;
    top: 0; right: 0;
    width: 3px; height: 100%;
    background: var(--accent, var(--red));
}}

.stat-icon {{
    width: 38px; height: 38px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 11px;
    font-size: 18px;
    background: color-mix(in srgb, var(--accent, var(--red)) 16%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent, var(--red)) 40%, transparent);
}}

.stat-title {{
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
    margin-top: 10px;
}}

.stat-value {{
    color: #f8fafc;
    font-size: 24px;
    font-weight: 900;
    margin-top: 2px;
}}


/* =========================================================
   PANELS
   ========================================================= */

.panel {{
    background: linear-gradient(150deg, rgba(18,28,46,.92), rgba(6,11,21,.88));
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 22px;
    margin-bottom: 18px;
    box-shadow: 0 18px 50px rgba(0,0,0,.22);
    animation: fadeUp .6s ease both;
}}

.panel-title {{
    font-size: 19px;
    font-weight: 900;
    color: #f8fafc;
    display: flex;
    align-items: center;
    gap: 8px;
}}


/* =========================================================
   BADGES (payment / remaining)
   ========================================================= */

.badge-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 6px;
}}

.badge {{
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 10px 16px;
    border-radius: 12px;
    font-weight: 800;
    font-size: 13.5px;
    border: 1px solid transparent;
}}

.badge-remaining {{
    background: linear-gradient(135deg, rgba(240,180,41,.20), rgba(240,180,41,.06));
    border-color: rgba(240,180,41,.5);
    color: var(--gold);
}}

.badge-paid {{
    background: linear-gradient(135deg, rgba(34,197,94,.20), rgba(34,197,94,.06));
    border-color: rgba(34,197,94,.5);
    color: #4ade80;
}}

.badge-warn {{
    background: linear-gradient(135deg, rgba(226,23,44,.20), rgba(226,23,44,.06));
    border-color: rgba(226,23,44,.5);
    color: #f87171;
}}


/* =========================================================
   INPUTS
   ========================================================= */

div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div,
div[data-baseweb="select"] > div {{
    background: #0c1526 !important;
    border: 1px solid #24344c !important;
    border-radius: 11px !important;
    transition: border-color .2s ease, box-shadow .2s ease;
}}

div[data-baseweb="input"] > div:focus-within,
div[data-baseweb="textarea"] > div:focus-within,
div[data-baseweb="select"] > div:focus-within {{
    border-color: rgba(240,180,41,.6) !important;
    box-shadow: 0 0 0 3px rgba(240,180,41,.10);
}}

input, textarea {{
    color: #f8fafc !important;
}}

input::placeholder,
textarea::placeholder {{
    color: #4c586c !important;
}}

label {{
    color: #cbd5e1 !important;
    font-size: 12px !important;
    font-weight: 700 !important;
}}


/* =========================================================
   BUTTONS
   ========================================================= */

.stButton > button,
.stFormSubmitButton > button {{
    border: 0 !important;
    border-radius: 11px !important;
    min-height: 46px;
    background: linear-gradient(135deg, #f5253b, #ad0f21) !important;
    color: #fff !important;
    font-weight: 800 !important;
    letter-spacing: .2px;
    transition: transform .2s ease, box-shadow .2s ease, filter .2s ease;
}}

.stButton > button:hover,
.stFormSubmitButton > button:hover {{
    transform: translateY(-2px);
    filter: brightness(1.08);
    box-shadow: 0 14px 30px rgba(226,23,44,.3);
}}


/* =========================================================
   DATAFRAME
   ========================================================= */

[data-testid="stDataFrame"] {{
    border: 1px solid var(--line);
    border-radius: 16px;
    overflow: hidden;
}}


/* =========================================================
   MESSAGES
   ========================================================= */

div[data-testid="stAlert"] {{
    border-radius: 12px;
}}


/* =========================================================
   DIVIDER
   ========================================================= */

hr {{
    border-color: rgba(148,163,184,.10) !important;
}}


/* =========================================================
   FOOTER
   ========================================================= */

.footer {{
    text-align: center;
    color: #3d4759;
    font-size: 10px;
    padding: 22px 0 4px;
    letter-spacing: .5px;
}}

.footer strong {{
    background: linear-gradient(90deg, var(--red), var(--gold));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}}


/* =========================================================
   MOBILE FIXES
   ========================================================= */

@media (max-width: 768px) {{

    .hero-title {{ font-size: 19px; }}
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

    .stat-card {{ min-height: 92px; padding: 14px 15px; }}
    .stat-value {{ font-size: 21px; }}

    section[data-testid="stSidebar"][aria-expanded="false"] {{
        visibility: hidden;
    }}
}}

</style>  """,
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


def payment_status_short(total, deposit):
    """Short status label (remaining amount is shown separately, highlighted)."""
    if total > 0 and deposit >= total:
        return "مدفوع بالكامل"
    if deposit > 0:
        return "عربون مدفوع"
    return "لم يُدفع"


def render_payment_badge(total, deposit):
    """Render a clearly highlighted remaining-balance badge."""
    remaining = total - deposit
    if total > 0 and deposit >= total:
        st.markdown(
            '<div class="badge-row"><span class="badge badge-paid">✅ مدفوع بالكامل</span></div>',
            unsafe_allow_html=True,
        )
    elif remaining > 0 and total > 0:
        st.markdown(
            f"""<div class="badge-row">
                <span class="badge badge-remaining">المتبقي: {remaining:,.2f} ج</span>
            </div>""",
            unsafe_allow_html=True,
        )
    elif total > 0:
        st.markdown(
            '<div class="badge-row"><span class="badge badge-warn">لم يُدفع</span></div>',
            unsafe_allow_html=True,
        )


def get_statistics():
    conn = get_connection()

    df = pd.read_sql_query(
        "SELECT total_cost, order_status FROM orders",
        conn
    )

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
                <img class="brand-logo"
                     src="data:image/jpeg;base64,{logo_b64}">
                <div class="brand-name">ZERO PLUS</div>
                <div class="brand-caption">
                    PRINT • DESIGN • ADVERTISING
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.divider()

    st.markdown(
        '<div class="side-label">القائمة الرئيسية</div>',
        unsafe_allow_html=True
    )

    menu = [
        "➕  تسجيل طلب جديد",
        "📋  عرض واستعلام الطلبات",
        "⚙️  تحديث حالة طلب",
        "📝  المفكرة اليومية",
        "☁️  النسخ الاحتياطي (Google Drive)",
    ]

    choice = st.selectbox(
        "القائمة",
        menu,
        label_visibility="collapsed"
    )

    st.divider()

    # Small preview of today's note
    today_note = get_today_note()

    if today_note:
        preview = today_note[:150]
        if len(today_note) > 150:
            preview += "..."

        st.markdown(
            f"""
            <div class="side-note">
                <div class="side-note-title">📌 ملاحظة اليوم</div>
                <div class="side-note-date">
                    {date.today().strftime("%Y-%m-%d")}
                </div>
                <div class="side-note-text">{preview}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <div class="side-note">
                <div class="side-note-title">📌 لا توجد ملاحظات</div>
            </div>
            """,
            unsafe_allow_html=True
        )

# =========================================================
# TOP HEADER
# =========================================================
today_text = date.today().strftime("%Y-%m-%d")

st.markdown(
    f"""
    <div class="hero">
        <div class="hero-eyebrow">ZERO PLUS</div>
        <div class="hero-title">نظام إدارة الطلبات</div>
        <div class="hero-sub">{today_text}</div>
    </div>
    """,
    unsafe_allow_html=True
)

# =========================================================
# DASHBOARD STATS
# =========================================================
total_orders, completed, in_progress, total_sales = get_statistics()

c1, c2, c3, c4 = st.columns(4)

stats = [
    ("📦", "إجمالي الطلبات", total_orders, "#5b8def"),
    ("🚀", "قيد التنفيذ", in_progress, "#f0b429"),
    ("✅", "تم التسليم", completed, "#22c55e"),
    ("💰", "إجمالي القيمة", f"{total_sales:,.0f} ج", "#e2172c"),
]

for col, (icon, title, value, accent) in zip([c1, c2, c3, c4], stats):
    with col:
        st.markdown(
            f"""
            <div class="stat-card" style="--accent:{accent}">
                <div class="stat-icon">{icon}</div>
                <div class="stat-title">{title}</div>
                <div class="stat-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

st.markdown("<br>", unsafe_allow_html=True)

# =========================================================
# 1. NEW ORDER
# =========================================================
if choice == "➕  تسجيل طلب جديد":

    st.markdown(
        """
        <div class="panel">
            <div class="panel-title">📝 تسجيل طلب جديد</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    with st.form("add_order_form", clear_on_submit=True):

        col1, col2, col3 = st.columns(3)

        with col1:

            customer_name = st.text_input(
                "اسم العميل *",
                placeholder="مثال: أحمد محمد"
            )

            customer_phone = st.text_input(
                "رقم التليفون",
                placeholder="01XXXXXXXXX"
            )

        with col2:

            order_details = st.text_area(
                "تفاصيل الطلب *",
                placeholder="500 فلاير — مقاس A5 — وجهين — ألوان...",
                height=155
            )

        with col3:

            total_cost = st.number_input(
                "التكلفة الإجمالية (جنيه)",
                min_value=0.0,
                value=None,
                step=25.0,
                format="%.0f",
                placeholder="0"
            )

            deposit = st.number_input(
                "المبلغ المدفوع / العربون",
                min_value=0.0,
                value=None,
                step=25.0,
                format="%.0f",
                placeholder="0"
            )

            order_status = st.selectbox(
                "حالة الطلب",
                ["قيد التنفيذ", "جاهز للتسليم", "تم التسليم"]
            )

        total_cost = total_cost if total_cost is not None else 0.0
        deposit = deposit if deposit is not None else 0.0

        st.divider()

        if total_cost > 0:
            if deposit > total_cost:
                st.markdown(
                    '<div class="badge-row"><span class="badge badge-warn">⚠️ العربون أكبر من الإجمالي</span></div>',
                    unsafe_allow_html=True
                )
            else:
                render_payment_badge(total_cost, deposit)

        save = st.form_submit_button(
            "💾  حفظ الطلب",
            use_container_width=True
        )

        if save:

            if not customer_name.strip():
                st.error("اكتب اسم العميل.")

            elif not order_details.strip():
                st.error("اكتب تفاصيل الطلب.")

            elif deposit > total_cost and total_cost > 0:
                st.error("العربون لا يمكن أن يكون أكبر من إجمالي الطلب.")

            else:

                payment_status = calculate_payment(
                    total_cost,
                    deposit
                )

                conn = get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO customers (name, phone)
                    VALUES (?, ?)
                    """,
                    (
                        customer_name.strip(),
                        customer_phone.strip()
                    )
                )

                customer_id = cursor.lastrowid

                cursor.execute(
                    """
                    INSERT INTO orders
                    (
                        customer_id,
                        order_details,
                        total_cost,
                        deposit,
                        payment_status,
                        order_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        customer_id,
                        order_details.strip(),
                        total_cost,
                        deposit,
                        payment_status,
                        order_status
                    )
                )

                conn.commit()
                conn.close()

                backup_result = backup_after_save()

                st.success(f"تم حفظ طلب العميل «{customer_name}».")
                if not backup_result["success"]:
                    st.warning(
                        "الداتا اتحفظت، لكن حصلت مشكلة في المزامنة السحابية: "
                        + str(backup_result["error"])
                    )

# =========================================================
# 2. ORDERS
# =========================================================
elif choice == "📋  عرض واستعلام الطلبات":

    st.markdown(
        """
        <div class="panel">
            <div class="panel-title">📋 الطلبات المسجلة</div>
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
            (o.total_cost - o.deposit) AS 'المتبقي',
            o.order_status AS 'حالة الطلب',
            o.order_date AS 'تاريخ الطلب'
        FROM orders o
        JOIN customers c
            ON o.customer_id = c.customer_id
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
            search_name = st.text_input(
                "🔍 البحث",
                placeholder="ابحث باسم العميل..."
            )

        with filter_col:
            status_filter = st.selectbox(
                "📌 حالة الطلب",
                [
                    "الكل",
                    "قيد التنفيذ",
                    "جاهز للتسليم",
                    "تم التسليم"
                ]
            )

        if search_name:
            df = df[
                df["اسم العميل"].str.contains(
                    search_name,
                    case=False,
                    na=False
                )
            ]

        if status_filter != "الكل":
            df = df[df["حالة الطلب"] == status_filter]

        def _highlight_remaining(val):
            try:
                v = float(val)
            except (TypeError, ValueError):
                return ""
            if v <= 0:
                return "color:#4ade80; font-weight:800;"
            return "color:#f0b429; font-weight:800;"

        styled = (
            df.style
            .format({
                "الإجمالي": "{:,.0f} ج",
                "العربون": "{:,.0f} ج",
                "المتبقي": "{:,.0f} ج",
            })
            .applymap(_highlight_remaining, subset=["المتبقي"])
        )

        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
            height=520,
        )

        st.caption(f"عدد النتائج: {len(df)}")

# =========================================================
# 3. UPDATE ORDER
# =========================================================
elif choice == "⚙️  تحديث حالة طلب":

    st.markdown(
        """
        <div class="panel">
            <div class="panel-title">⚙️ تحديث حالة طلب</div>
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
        JOIN customers c
            ON o.customer_id = c.customer_id
        ORDER BY o.order_id DESC
        """
    )

    orders = cursor.fetchall()

    if not orders:

        st.info("لا توجد طلبات لتعديلها.")

    else:

        options = {
            f"طلب #{order_id} — {name}": order_id
            for order_id, name in orders
        }

        selected_label = st.selectbox(
            "📌 اختر الطلب",
            list(options.keys())
        )

        selected_id = options[selected_label]

        cursor.execute(
            """
            SELECT
                total_cost,
                deposit,
                payment_status,
                order_status
            FROM orders
            WHERE order_id = ?
            """,
            (selected_id,)
        )

        current = cursor.fetchone()

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                """
                <div class="panel">
                    <div class="panel-title">💰 الحساب</div>
                </div>
                """,
                unsafe_allow_html=True
            )

            total_cost = float(current[0] or 0)
            current_deposit = float(current[1] or 0)

            new_deposit = st.number_input(
                "المبلغ المدفوع",
                min_value=0.0,
                value=(None if current_deposit == 0 else current_deposit),
                step=25.0,
                format="%.0f",
                placeholder="0"
            )
            new_deposit = new_deposit if new_deposit is not None else 0.0

            remaining = total_cost - new_deposit

            if new_deposit > total_cost and total_cost > 0:
                st.markdown(
                    '<div class="badge-row"><span class="badge badge-warn">⚠️ المبلغ أكبر من قيمة الطلب</span></div>',
                    unsafe_allow_html=True
                )
                new_payment_status = current[2]
            else:
                new_payment_status = calculate_payment(
                    total_cost,
                    new_deposit
                )
                render_payment_badge(total_cost, new_deposit)

        with col2:

            st.markdown(
                """
                <div class="panel">
                    <div class="panel-title">📦 التنفيذ</div>
                </div>
                """,
                unsafe_allow_html=True
            )

            statuses = [
                "قيد التنفيذ",
                "جاهز للتسليم",
                "تم التسليم"
            ]

            current_status = current[3]
            if current_status not in statuses:
                current_status = statuses[0]

            new_order_status = st.selectbox(
                "حالة الطلب الجديدة",
                statuses,
                index=statuses.index(current_status)
            )

        if st.button(
            "🔄  حفظ التعديلات",
            use_container_width=True
        ):

            if new_deposit > total_cost and total_cost > 0:
                st.error("لا يمكن دفع مبلغ أكبر من قيمة الطلب.")

            else:

                cursor.execute(
                    """
                    UPDATE orders
                    SET
                        deposit = ?,
                        payment_status = ?,
                        order_status = ?
                    WHERE order_id = ?
                    """,
                    (
                        new_deposit,
                        new_payment_status,
                        new_order_status,
                        selected_id
                    )
                )

                conn.commit()
                conn.close()

                backup_result = backup_after_save()

                st.success("تم تحديث الطلب.")
                if not backup_result["success"]:
                    st.warning(
                        "التحديث اتحفظ، لكن حصلت مشكلة في المزامنة السحابية: "
                        + str(backup_result["error"])
                    )
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
        <div class="panel">
            <div class="panel-title">📌 ملاحظة يوم {today_iso}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    current_note = get_today_note()

    note = st.text_area(
        "اكتب ملاحظتك هنا",
        value=current_note,
        height=260,
        placeholder="اكتب مهامك أو ملاحظاتك لليوم..."
    )

    if st.button(
        "💾  حفظ ملاحظة اليوم",
        use_container_width=True
    ):

        save_today_note(note.strip())
        backup_result = backup_after_save()

        st.success(f"تم حفظ ملاحظة يوم {today_iso}.")
        if not backup_result["success"]:
            st.warning(
                "الملاحظة اتحفظت، لكن حصلت مشكلة في المزامنة السحابية: "
                + str(backup_result["error"])
            )

        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    recent = get_recent_notes(10)

    if not recent.empty:

        st.markdown(
            """
            <div class="panel">
                <div class="panel-title">🗓️ الملاحظات السابقة</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        for _, row in recent.iterrows():

            with st.expander(
                f"📅 {row['note_date']}"
            ):
                st.write(row["note_text"])

# =========================================================
# 5. CLOUD BACKUP (Google Drive)
# =========================================================
elif choice == "☁️  النسخ الاحتياطي (Google Drive)":

    st.markdown(
        """
        <div class="panel">
            <div class="panel-title">☁️ حماية البيانات</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if not drive_backup_configured():
        st.error("النسخ الاحتياطي غير مُهيأ.")
        st.markdown("### ⚙️ الإعداد لأول مرة")
        st.markdown(
            """
            1) افتح Google Apps Script وأنشئ مشروعاً جديداً.
            2) الصق كود google_drive_backup_apps_script.gs.
            3) Deploy → New deployment → Web app.
            4) Execute as: **Me** — Who has access: **Anyone**.
            5) انسخ Web app URL.
            6) ضعه في Streamlit Secrets مع السر الموجود في Apps Script.
            """
        )
    else:
        st.success("Google Drive Backup متصل.")

        db_file = FilePath(DB_NAME)
        if db_file.exists():
            db_size = db_file.stat().st_size / 1024
            st.info(f"📦 `{DB_NAME}` — {db_size:.1f} KB")

        remote = drive_backup_info()
        if remote and remote.get("found"):
            st.success("☁️ آخر نسخة: " + str(remote.get("filename", "غير معروف")))
        else:
            st.info("لا توجد نسخة احتياطية على Google Drive حتى الآن.")

        if st.button("☁️ عمل Backup الآن", use_container_width=True):
            with st.spinner("جاري رفع النسخة..."):
                result = drive_backup_db()
            if result["success"]:
                st.success("تم رفع النسخة بنجاح إلى Google Drive.")
            else:
                st.error("فشل النسخ الاحتياطي:\n\n" + str(result["error"]))

        st.markdown("<br>", unsafe_allow_html=True)
        st.warning("⚠️ الاسترجاع سيستبدل قاعدة البيانات الحالية بآخر Backup على Google Drive.")

        if st.button("🔄 استرجاع آخر Backup", use_container_width=True):
            with st.spinner("جاري تنزيل وفحص النسخة..."):
                result = drive_restore_latest()
            if result["success"]:
                st.success("تم الاسترجاع: " + str(result.get("filename", "latest backup")))
                st.rerun()
            else:
                st.error("فشل الاسترجاع:\n\n" + str(result["error"]))

# =========================================================
# FOOTER
# =========================================================
st.markdown(
    """
    <div class="footer">
        ZERO Advertising Management System
        <br>
        <strong>PRINT • DESIGN • ADVERTISING</strong>
    </div>
    """,
    unsafe_allow_html=True
)
