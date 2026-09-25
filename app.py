import base64
import io
import os
import shutil
import sqlite3
from pathlib import Path as FilePath
from datetime import date, datetime

import pandas as pd
import requests
import streamlit as st


# =========================================================
# PAGE
# =========================================================

st.set_page_config(
    page_title="ZERO Advertising",
    page_icon="zero.jpg",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =========================================================
# FILES
# =========================================================

LOGO_PATH = "zero.jpg"
DB_NAME = "print_shop.db"
EXCEL_BACKUP_FILENAME = "ZERO_DATABASE_BACKUP.xlsx"


def image_base64(path):
    try:
        with open(path, "rb") as file:
            return base64.b64encode(file.read()).decode("utf-8")
    except Exception:
        return ""


logo_b64 = image_base64(LOGO_PATH)


# =========================================================
# DATABASE
# =========================================================

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
# GOOGLE DRIVE BACKUP
# =========================================================

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
    return bool(
        DRIVE_BACKUP_URL and
        DRIVE_BACKUP_TOKEN
    )


def _json_response(response):

    try:
        return response.json()

    except Exception:

        return {
            "success": False,
            "error": response.text[:500]
        }


def _db_to_excel_bytes():

    output = io.BytesIO()

    conn = sqlite3.connect(
        DB_NAME,
        timeout=30
    )

    try:

        with pd.ExcelWriter(
            output,
            engine="openpyxl"
        ) as writer:

            for table in (
                "customers",
                "orders",
                "daily_notes"
            ):

                df = pd.read_sql_query(
                    f"SELECT * FROM {table}",
                    conn
                )

                df.to_excel(
                    writer,
                    sheet_name=table,
                    index=False
                )

    finally:
        conn.close()

    return output.getvalue()


def _excel_bytes_to_db(
    excel_bytes,
    target_path
):

    xls = pd.ExcelFile(
        io.BytesIO(excel_bytes),
        engine="openpyxl"
    )

    required = {
        "customers",
        "orders",
        "daily_notes"
    }

    if not required.issubset(
        set(xls.sheet_names)
    ):
        raise ValueError(
            "ملف النسخة الاحتياطية غير صالح."
        )

    target = FilePath(target_path)

    if target.exists():
        target.unlink()

    conn = sqlite3.connect(
        target_path,
        timeout=30
    )

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
                FOREIGN KEY (customer_id)
                REFERENCES customers(customer_id)
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

        for table in (
            "customers",
            "orders",
            "daily_notes"
        ):

            df = pd.read_excel(
                xls,
                sheet_name=table,
                engine="openpyxl"
            )

            df = df.where(
                pd.notna(df),
                None
            )

            if not df.empty:

                columns = list(df.columns)

                placeholders = ",".join(
                    ["?"] * len(columns)
                )

                sql = f"""
                    INSERT INTO {table}
                    ({','.join(columns)})
                    VALUES ({placeholders})
                """

                rows = [
                    tuple(row)
                    for row in df.itertuples(
                        index=False,
                        name=None
                    )
                ]

                cursor.executemany(
                    sql,
                    rows
                )

        conn.commit()

        integrity = conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise ValueError(
                "فشل فحص قاعدة البيانات."
            )

    finally:
        conn.close()


def drive_backup_db():

    result = {
        "success": False,
        "error": None
    }

    if not drive_backup_configured():

        result["error"] = (
            "النسخ الاحتياطي غير مُهيأ."
        )

        return result

    db_file = FilePath(DB_NAME)

    if not db_file.exists():

        result["error"] = (
            "ملف قاعدة البيانات غير موجود."
        )

        return result

    try:

        excel_bytes = _db_to_excel_bytes()

        encoded = base64.b64encode(
            excel_bytes
        ).decode("ascii")

        response = requests.post(
            DRIVE_BACKUP_URL,
            data={
                "action": "backup",
                "token": DRIVE_BACKUP_TOKEN,
                "filename": EXCEL_BACKUP_FILENAME,
                "data": encoded,
            },
            timeout=90
        )

        payload = _json_response(response)

        if (
            response.ok and
            payload.get("success")
        ):

            result["success"] = True

            result["filename"] = (
                EXCEL_BACKUP_FILENAME
            )

        else:

            result["error"] = (
                payload.get("error")
                or
                f"HTTP {response.status_code}"
            )

    except Exception as exc:

        result["error"] = str(exc)

    return result


def drive_restore_latest():

    result = {
        "success": False,
        "error": None
    }

    if not drive_backup_configured():

        result["error"] = (
            "النسخ الاحتياطي غير مُهيأ."
        )

        return result

    try:

        response = requests.get(
            DRIVE_BACKUP_URL,
            params={
                "action": "download",
                "token": DRIVE_BACKUP_TOKEN,
                "latest": "1"
            },
            timeout=90
        )

        payload = _json_response(response)

        if (
            not response.ok
            or
            not payload.get("success")
        ):

            result["error"] = (
                payload.get("error")
                or
                f"HTTP {response.status_code}"
            )

            return result

        excel_bytes = base64.b64decode(
            payload.get("data", "")
        )

        temp_path = FilePath(
            DB_NAME + ".restore_tmp"
        )

        _excel_bytes_to_db(
            excel_bytes,
            temp_path
        )

        db_file = FilePath(DB_NAME)

        if db_file.exists():

            shutil.copy2(
                db_file,
                (
                    "print_shop_before_restore_"
                    +
                    datetime.now().strftime(
                        "%Y%m%d_%H%M%S"
                    )
                    +
                    ".db"
                )
            )

        shutil.move(
            str(temp_path),
            DB_NAME
        )

        result["success"] = True

        result["filename"] = payload.get(
            "filename",
            EXCEL_BACKUP_FILENAME
        )

    except Exception as exc:

        try:

            FilePath(
                DB_NAME + ".restore_tmp"
            ).unlink(
                missing_ok=True
            )

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
            params={
                "action": "status",
                "token": DRIVE_BACKUP_TOKEN
            },
            timeout=30
        )

        payload = _json_response(response)

        if (
            response.ok
            and
            payload.get("success")
        ):
            return payload

    except Exception:
        pass

    return None


def backup_after_save():
    return drive_backup_db()


# =========================================================
# AUTO RESTORE
# =========================================================

if not FilePath(DB_NAME).exists():

    info = drive_backup_info()

    if (
        info
        and
        info.get("found")
    ):
        drive_restore_latest()


init_db()


# =========================================================
# DESIGN
# =========================================================

def set_custom_design():

    background_css = ""

    if logo_b64:

        background_css = f"""

        .stApp::before {{
            content: "";
            position: fixed;
            inset: 0;

            background-image:
                url("data:image/jpeg;base64,{logo_b64}");

            background-repeat: no-repeat;
            background-position: 50% 45%;
            background-size: min(850px, 55vw);

            opacity: .035;

            pointer-events: none;
            z-index: 0;
        }}

        """

    st.markdown(
        f"""
<style>

* {{
    box-sizing: border-box;
}}

html,
body,
.stApp {{
    direction: rtl;
}}

.stApp {{

    background:

        radial-gradient(
            circle at 5% 5%,
            rgba(225, 25, 45, .14),
            transparent 25%
        ),

        radial-gradient(
            circle at 95% 90%,
            rgba(70, 85, 120, .16),
            transparent 28%
        ),

        linear-gradient(
            135deg,
            #05070c 0%,
            #090d15 45%,
            #05070c 100%
        );

    color: #f8fafc;
}}

{background_css}


.main .block-container {{

    position: relative;
    z-index: 1;

    max-width: 1600px;

    padding-top: 1.2rem;
    padding-bottom: 3rem;
    padding-left: 2rem;
    padding-right: 2rem;
}}


#MainMenu,
footer {{
    visibility: hidden;
}}

header {{
    background: transparent !important;
}}


/* =========================================================
   SIDEBAR
   ========================================================= */

section[data-testid="stSidebar"] {{

    background:
        linear-gradient(
            180deg,
            #07090f 0%,
            #0b101a 55%,
            #06080d 100%
        ) !important;

    border-left:
        1px solid rgba(226,27,43,.35);

    box-shadow:
        -20px 0 60px rgba(0,0,0,.45);

}}

section[data-testid="stSidebar"] > div {{
    padding: 1rem .8rem 1.5rem;
}}

section[data-testid="stSidebar"] * {{
    color: #f5f7fb !important;
}}


.brand-box {{
    text-align: center;
    padding: 5px 5px 18px;
}}

.brand-logo {{
    width: 108px;
    height: 108px;

    object-fit: cover;

    border-radius: 24px;

    border:
        1px solid rgba(255,255,255,.13);

    box-shadow:
        0 20px 55px rgba(0,0,0,.55);
}}

.brand-name {{
    font-size: 23px;
    font-weight: 900;
    margin-top: 13px;
    letter-spacing: 1px;
}}

.brand-caption {{
    color: #69758a !important;
    font-size: 9px;
    letter-spacing: 2px;
    margin-top: 3px;
}}


.side-label {{
    color: #68758b !important;
    font-size: 10px;
    margin: 12px 3px 7px;
}}


/* =========================================================
   HERO
   ========================================================= */

.hero {{

    position: relative;

    background:
        linear-gradient(
            135deg,
            rgba(24,31,47,.92),
            rgba(8,11,18,.86)
        );

    border:
        1px solid rgba(255,255,255,.08);

    border-radius: 25px;

    padding: 27px 30px;

    margin-bottom: 22px;

    overflow: hidden;

    box-shadow:
        0 25px 70px rgba(0,0,0,.28);

}}

.hero::before {{

    content: "";

    position: absolute;

    width: 250px;
    height: 250px;

    left: -100px;
    top: -140px;

    background:
        radial-gradient(
            circle,
            rgba(226,27,43,.30),
            transparent 70%
        );

}}

.hero-line {{

    width: 55px;
    height: 4px;

    background:
        linear-gradient(
            90deg,
            #ff3044,
            #9c0c1d
        );

    border-radius: 20px;

    margin-bottom: 11px;

}}

.hero-title {{

    font-size: 30px;
    font-weight: 900;

    letter-spacing: -.7px;

    color: #ffffff;

}}

.hero-sub {{

    color: #7f8ba0;

    font-size: 11px;

    margin-top: 5px;

}}


/* =========================================================
   STAT CARDS
   ========================================================= */

.stat-card {{

    position: relative;

    min-height: 130px;

    padding: 21px;

    border-radius: 21px;

    background:
        linear-gradient(
            145deg,
            rgba(20,27,42,.94),
            rgba(8,12,20,.92)
        );

    border:
        1px solid rgba(255,255,255,.075);

    box-shadow:
        0 18px 50px rgba(0,0,0,.24);

    overflow: hidden;

    transition:
        transform .25s ease,
        border-color .25s ease,
        box-shadow .25s ease;

}}

.stat-card:hover {{

    transform: translateY(-6px);

    border-color:
        rgba(226,27,43,.42);

    box-shadow:
        0 25px 60px rgba(0,0,0,.36);

}}

.stat-card::after {{

    content: "";

    position: absolute;

    right: 0;
    top: 0;

    width: 3px;
    height: 100%;

    background:
        linear-gradient(
            #ff3044,
            #9b0d1e
        );

}}

.stat-icon {{
    font-size: 24px;
}}

.stat-title {{

    color: #68758a;

    font-size: 10px;

    margin-top: 8px;

}}

.stat-value {{

    color: #ffffff;

    font-size: 25px;

    font-weight: 900;

    margin-top: 3px;

}}


/* =========================================================
   PANELS
   ========================================================= */

.panel {{

    background:
        linear-gradient(
            145deg,
            rgba(17,24,38,.92),
            rgba(7,10,17,.88)
        );

    border:
        1px solid rgba(255,255,255,.075);

    border-radius: 21px;

    padding: 22px;

    margin-bottom: 18px;

    box-shadow:
        0 20px 55px rgba(0,0,0,.22);

}}

.panel-title {{

    color: #ffffff;

    font-size: 19px;

    font-weight: 900;

}}

.panel-sub {{

    color: #68758a;

    font-size: 10px;

    margin-top: 4px;

}}


/* =========================================================
   INPUTS
   ========================================================= */

div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div,
div[data-baseweb="select"] > div {{

    background:
        rgba(10,16,27,.92) !important;

    border:
        1px solid #243047 !important;

    border-radius: 12px !important;

}}

div[data-baseweb="input"] > div:focus-within,
div[data-baseweb="textarea"] > div:focus-within,
div[data-baseweb="select"] > div:focus-within {{

    border-color:
        rgba(226,27,43,.70) !important;

    box-shadow:
        0 0 0 3px rgba(226,27,43,.08);

}}

input,
textarea {{
    color: #ffffff !important;
}}

input::placeholder,
textarea::placeholder {{
    color: #4e5c72 !important;
}}

label {{
    color: #cbd5e1 !important;
    font-size: 11px !important;
    font-weight: 700 !important;
}}


/* =========================================================
   BUTTONS
   ========================================================= */

.stButton > button,
.stFormSubmitButton > button {{

    min-height: 46px;

    border:
        1px solid rgba(255,255,255,.06) !important;

    border-radius: 12px !important;

    background:
        linear-gradient(
            135deg,
            #ef2035,
            #a70d1e
        ) !important;

    color: white !important;

    font-weight: 900 !important;

    box-shadow:
        0 10px 25px rgba(226,27,43,.16);

    transition:
        all .22s ease;

}}

.stButton > button:hover,
.stFormSubmitButton > button:hover {{

    transform:
        translateY(-2px);

    filter:
        brightness(1.08);

    box-shadow:
        0 16px 35px rgba(226,27,43,.28);

}}


/* =========================================================
   TABLE
   ========================================================= */

.zero-table-wrapper {{

    width: 100%;

    overflow-x: auto;

    border-radius: 18px;

    border:
        1px solid rgba(255,255,255,.07);

    background:
        rgba(5,8,14,.78);

}}

.zero-table {{

    width: 100%;

    border-collapse: separate;

    border-spacing: 0;

    min-width: 950px;

    font-size: 12px;

}}

.zero-table th {{

    background:
        #111827;

    color:
        #8490a4;

    padding:
        14px 12px;

    text-align:
        right;

    font-size:
        10px;

    font-weight:
        800;

    white-space:
        nowrap;

    border-bottom:
        1px solid rgba(255,255,255,.07);

}}

.zero-table td {{

    padding:
        14px 12px;

    color:
        #dce3ed;

    border-bottom:
        1px solid rgba(255,255,255,.045);

    vertical-align:
        middle;

}}

.zero-table tr:last-child td {{
    border-bottom: none;
}}

.zero-table tr:hover td {{

    background:
        rgba(226,27,43,.045);

}}

.order-number {{

    color:
        #ff4254;

    font-weight:
        900;

}}

.money {{

    font-weight:
        800;

    color:
        #ffffff;

}}

.remaining {{

    display:
        inline-block;

    margin-right:
        5px;

    color:
        #ff5364;

    font-weight:
        900;

    background:
        rgba(226,27,43,.09);

    padding:
        4px 8px;

    border-radius:
        7px;

    border:
        1px solid rgba(226,27,43,.18);

}}

.paid {{
    color: #55d68a;
    font-weight: 800;
}}

.not-paid {{
    color: #ffb454;
    font-weight: 800;
}}

.status {{
    display:
        inline-block;

    padding:
        5px 9px;

    border-radius:
        8px;

    font-size:
        10px;

    font-weight:
        800;
}}

.status-progress {{

    color:
        #ffc35a;

    background:
        rgba(255,195,90,.09);

}}

.status-ready {{

    color:
        #61b9ff;

    background:
        rgba(97,185,255,.09);

}}

.status-done {{

    color:
        #56d88c;

    background:
        rgba(86,216,140,.09);

}}


/* =========================================================
   NOTE
   ========================================================= */

.note-card {{

    background:
        linear-gradient(
            145deg,
            rgba(20,27,42,.95),
            rgba(8,12,20,.92)
        );

    border:
        1px solid rgba(255,255,255,.07);

    border-radius: 18px;

    padding: 17px;

    margin-bottom: 10px;

}}

.note-date {{

    color:
        #ff4254;

    font-size:
        10px;

    font-weight:
        800;

}}

.note-text {{

    color:
        #cdd5e1;

    font-size:
        12px;

    line-height:
        1.9;

    margin-top:
        7px;

    white-space:
        pre-wrap;

}}


/* =========================================================
   ALERTS
   ========================================================= */

div[data-testid="stAlert"] {{
    border-radius: 12px;
}}


/* =========================================================
   MOBILE
   ========================================================= */

@media(max-width: 768px) {{

    .main .block-container {{

        padding-left: .8rem;
        padding-right: .8rem;

    }}

    .hero {{
        padding: 21px;
        border-radius: 19px;
    }}

    .hero-title {{
        font-size: 20px;
    }}

    .stat-card {{
        min-height: 105px;
    }}

    .stat-value {{
        font-size: 21px;
    }}

    div[data-testid="stHorizontalBlock"] {{
        flex-wrap: wrap !important;
        gap: .6rem;
    }}

    div[data-testid="stHorizontalBlock"]
    > div[data-testid="column"] {{
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }}

}}

</style>
        """,
        unsafe_allow_html=True
    )


set_custom_design()


# =========================================================
# HELPERS
# =========================================================

def calculate_payment(total, deposit):

    if total > 0 and deposit >= total:
        return "تم الدفع بالكامل"

    if deposit > 0:

        remaining = total - deposit

        return (
            f"تم دفع عربون|{remaining}"
        )

    return "لم يدفع"


def get_payment_html(
    total,
    deposit
):

    total = float(total or 0)
    deposit = float(deposit or 0)

    if total > 0 and deposit >= total:

        return (
            '<span class="paid">'
            '✓ تم الدفع بالكامل'
            '</span>'
        )

    if deposit > 0:

        remaining = total - deposit

        return (
            '<span>تم دفع عربون</span> '
            '<span class="remaining">'
            f'المتبقي: {remaining:,.2f} ج'
            '</span>'
        )

    return (
        '<span class="not-paid">'
        'لم يدفع'
        '</span>'
    )


def get_order_status_html(status):

    if status == "تم التسليم":

        return (
            '<span class="status status-done">'
            '✓ تم التسليم'
            '</span>'
        )

    if status == "جاهز للتسليم":

        return (
            '<span class="status status-ready">'
            '● جاهز للتسليم'
            '</span>'
        )

    return (
        '<span class="status status-progress">'
        '● قيد التنفيذ'
        '</span>'
    )


def get_statistics():

    conn = get_connection()

    df = pd.read_sql_query(
        """
        SELECT
            total_cost,
            order_status
        FROM orders
        """,
        conn
    )

    conn.close()

    if df.empty:
        return 0, 0, 0, 0

    return (
        len(df),
        int(
            (
                df["order_status"]
                == "تم التسليم"
            ).sum()
        ),
        int(
            (
                df["order_status"]
                == "قيد التنفيذ"
            ).sum()
        ),
        float(
            df["total_cost"]
            .fillna(0)
            .sum()
        )
    )


def get_today_note():

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT note_text
        FROM daily_notes
        WHERE note_date = ?
        """,
        (
            date.today().isoformat(),
        )
    )

    row = cursor.fetchone()

    conn.close()

    return row[0] if row else ""


def save_today_note(note_text):

    conn = get_connection()

    cursor = conn.cursor()

    today = date.today().isoformat()

    cursor.execute(
        """
        INSERT INTO daily_notes
        (
            note_date,
            note_text,
            updated_at
        )
        VALUES
        (?, ?, CURRENT_TIMESTAMP)

        ON CONFLICT(note_date)
        DO UPDATE SET
            note_text = excluded.note_text,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            today,
            note_text
        )
    )

    conn.commit()
    conn.close()


def get_recent_notes(limit=10):

    conn = get_connection()

    df = pd.read_sql_query(
        """
        SELECT
            note_date,
            note_text
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
                <img
                    class="brand-logo"
                    src="data:image/jpeg;base64,{logo_b64}"
                >
                <div class="brand-name">
                    ZERO PLUS
                </div>
                <div class="brand-caption">
                    PRINT • DESIGN • ADVERTISING
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.divider()

    menu = [
        "➕  تسجيل طلب جديد",
        "📋  الطلبات",
        "⚙️  تحديث طلب",
        "📝  المفكرة",
        "☁️  Google Drive",
    ]

    choice = st.selectbox(
        "القائمة",
        menu,
        label_visibility="collapsed"
    )

    st.divider()

    today_note = get_today_note()

    if today_note:

        preview = today_note[:110]

        if len(today_note) > 110:
            preview += "..."

        st.markdown(
            f"""
            <div class="note-card">
                <div class="note-date">
                    📌 {date.today().isoformat()}
                </div>
                <div class="note-text">
                    {preview}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )


# =========================================================
# HEADER
# =========================================================

today_text = date.today().strftime(
    "%Y-%m-%d"
)

st.markdown(
    f"""
    <div class="hero">
        <div class="hero-line"></div>
        <div class="hero-title">
            ZERO Advertising
        </div>
        <div class="hero-sub">
            Management System&nbsp;&nbsp;•&nbsp;&nbsp;{today_text}
        </div>
    </div>
    """,
    unsafe_allow_html=True
)


# =========================================================
# DASHBOARD
# =========================================================

total_orders, completed, in_progress, total_sales = (
    get_statistics()
)

c1, c2, c3, c4 = st.columns(4)

stats = [

    (
        "📦",
        "إجمالي الطلبات",
        total_orders
    ),

    (
        "⚡",
        "قيد التنفيذ",
        in_progress
    ),

    (
        "✓",
        "تم التسليم",
        completed
    ),

    (
        "💰",
        "إجمالي الطلبات",
        f"{total_sales:,.0f} ج"
    ),
]


for col, (icon, title, value) in zip(
    [c1, c2, c3, c4],
    stats
):

    with col:

        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-icon">
                    {icon}
                </div>
                <div class="stat-title">
                    {title}
                </div>
                <div class="stat-value">
                    {value}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )


st.markdown(
    "<br>",
    unsafe_allow_html=True
)


# =========================================================
# NEW ORDER
# =========================================================

if choice == "➕  تسجيل طلب جديد":

    st.markdown(
        """
        <div class="panel">
            <div class="panel-title">
                تسجيل طلب جديد
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    with st.form(
        "add_order_form",
        clear_on_submit=True
    ):

        col1, col2, col3 = st.columns(3)

        with col1:

            customer_name = st.text_input(
                "اسم العميل *",
                placeholder="اسم العميل"
            )

            customer_phone = st.text_input(
                "رقم التليفون",
                placeholder="01XXXXXXXXX"
            )

        with col2:

            order_details = st.text_area(
                "تفاصيل الطلب *",
                placeholder="تفاصيل الطلب...",
                height=150
            )

        with col3:

            # =================================================
            # IMPORTANT:
            # value=None means the field starts EMPTY.
            # No zero to type over.
            # =================================================

            total_cost = st.number_input(
                "التكلفة الإجمالية",
                min_value=0.0,
                value=None,
                step=1.0,
                format="%.0f",
                placeholder="اكتب المبلغ"
            )

            deposit = st.number_input(
                "المبلغ المدفوع",
                min_value=0.0,
                value=None,
                step=1.0,
                format="%.0f",
                placeholder="اكتب المبلغ"
            )

            order_status = st.selectbox(
                "حالة الطلب",
                [
                    "قيد التنفيذ",
                    "جاهز للتسليم",
                    "تم التسليم"
                ]
            )

        st.divider()

        if (
            total_cost is not None
            and
            total_cost > 0
        ):

            current_deposit = (
                deposit
                if deposit is not None
                else 0
            )

            remaining = (
                total_cost
                - current_deposit
            )

            if current_deposit > total_cost:

                st.warning(
                    "العربون أكبر من قيمة الطلب."
                )

            elif remaining > 0:

                st.markdown(
                    f"""
                    <div class="panel"
                         style="margin:0;
                                padding:13px 16px;">
                        <span>
                            المتبقي على العميل
                        </span>
                        <span class="remaining">
                            {remaining:,.2f} ج
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            else:

                st.success(
                    "✓ تم دفع قيمة الطلب بالكامل."
                )

        save = st.form_submit_button(
            "حفظ الطلب",
            use_container_width=True
        )

        if save:

            final_total = (
                float(total_cost)
                if total_cost is not None
                else 0.0
            )

            final_deposit = (
                float(deposit)
                if deposit is not None
                else 0.0
            )

            if not customer_name.strip():

                st.error(
                    "اكتب اسم العميل."
                )

            elif not order_details.strip():

                st.error(
                    "اكتب تفاصيل الطلب."
                )

            elif (
                final_deposit > final_total
                and
                final_total > 0
            ):

                st.error(
                    "العربون لا يمكن أن يكون أكبر من قيمة الطلب."
                )

            else:

                payment_status = calculate_payment(
                    final_total,
                    final_deposit
                )

                conn = get_connection()

                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO customers
                    (
                        name,
                        phone
                    )
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
                        final_total,
                        final_deposit,
                        payment_status,
                        order_status
                    )
                )

                conn.commit()
                conn.close()

                backup_result = backup_after_save()

                st.success(
                    f"تم حفظ طلب «{customer_name}»."
                )

                if not backup_result["success"]:

                    st.warning(
                        "تم الحفظ، لكن لم تتم المزامنة مع Drive: "
                        +
                        str(
                            backup_result["error"]
                        )
                    )


# =========================================================
# ORDERS
# =========================================================

elif choice == "📋  الطلبات":

    st.markdown(
        """
        <div class="panel">
            <div class="panel-title">
                الطلبات
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    conn = get_connection()

    df = pd.read_sql_query(
        """
        SELECT
            o.order_id AS order_id,
            c.name AS customer_name,
            c.phone AS phone,
            o.order_details AS details,
            o.total_cost AS total_cost,
            o.deposit AS deposit,
            o.payment_status AS payment_status,
            o.order_status AS order_status,
            o.order_date AS order_date

        FROM orders o

        JOIN customers c
            ON o.customer_id = c.customer_id

        ORDER BY o.order_id DESC
        """,
        conn
    )

    conn.close()

    if df.empty:

        st.info(
            "لا توجد طلبات مسجلة."
        )

    else:

        search_col, filter_col = st.columns(2)

        with search_col:

            search_name = st.text_input(
                "البحث",
                placeholder="اسم العميل..."
            )

        with filter_col:

            status_filter = st.selectbox(
                "حالة الطلب",
                [
                    "الكل",
                    "قيد التنفيذ",
                    "جاهز للتسليم",
                    "تم التسليم"
                ]
            )

        if search_name:

            df = df[
                df["customer_name"]
                .astype(str)
                .str.contains(
                    search_name,
                    case=False,
                    na=False
                )
            ]

        if status_filter != "الكل":

            df = df[
                df["order_status"]
                ==
                status_filter
            ]

        # =================================================
        # CUSTOM PREMIUM TABLE
        # This allows the remaining amount to have its
        # own color WITHOUT creating another column.
        # =================================================

        rows_html = ""

        for _, row in df.iterrows():

            payment_html = get_payment_html(
                row["total_cost"],
                row["deposit"]
            )

            status_html = get_order_status_html(
                row["order_status"]
            )

            details = str(
                row["details"] or ""
            )

            details = (
                details
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

            name = str(
                row["customer_name"] or ""
            )

            phone = str(
                row["phone"] or ""
            )

            rows_html += f"""

            <tr>
                <td>
                    <span class="order-number">
                        #{int(row["order_id"])}
                    </span>
                </td>
                <td>
                    {name}
                </td>
                <td>
                    {phone}
                </td>
                <td>
                    {details}
                </td>
                <td>
                    <span class="money">
                        {float(row["total_cost"] or 0):,.2f} ج
                    </span>
                </td>
                <td>
                    <span class="money">
                        {float(row["deposit"] or 0):,.2f} ج
                    </span>
                </td>
                <td>
                    {payment_html}
                </td>
                <td>
                    {status_html}
                </td>
                <td>
                    {row["order_date"]}
                </td>
            </tr>
            """

        st.markdown(
            f"""
            <div class="zero-table-wrapper">
                <table class="zero-table">
                    <thead>
                        <tr>
                            <th>الطلب</th>
                            <th>العميل</th>
                            <th>التليفون</th>
                            <th>التفاصيل</th>
                            <th>الإجمالي</th>
                            <th>المدفوع</th>
                            <th>حالة الدفع</th>
                            <th>الحالة</th>
                            <th>التاريخ</th>
                        </tr>
                    </thead>
                </table>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.caption(
            f"عدد النتائج: {len(df)}"
        )


# =========================================================
# UPDATE ORDER
# =========================================================

elif choice == "⚙️  تحديث طلب":

    st.markdown(
        """
        <div class="panel">
            <div class="panel-title">
                تحديث الطلب
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            o.order_id,
            c.name

        FROM orders o

        JOIN customers c
            ON o.customer_id = c.customer_id

        ORDER BY o.order_id DESC
        """
    )

    orders = cursor.fetchall()

    if not orders:

        st.info(
            "لا توجد طلبات."
        )

        conn.close()

    else:

        options = {
            f"طلب #{order_id} — {name}":
            order_id

            for order_id, name in orders
        }

        selected_label = st.selectbox(
            "اختر الطلب",
            list(options.keys())
        )

        selected_id = options[
            selected_label
        ]

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

        total_cost = float(
            current[0] or 0
        )

        old_deposit = float(
            current[1] or 0
        )

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                """
                <div class="panel">
                    <div class="panel-title">
                        💰 الحساب
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            new_deposit = st.number_input(
                "المبلغ المدفوع",
                min_value=0.0,
                value=old_deposit if old_deposit > 0 else None,
                step=1.0,
                format="%.0f",
                placeholder="اكتب المبلغ"
            )

            final_deposit = (
                float(new_deposit)
                if new_deposit is not None
                else 0.0
            )

            remaining = (
                total_cost
                -
                final_deposit
            )

            if (
                final_deposit > total_cost
                and
                total_cost > 0
            ):

                st.error(
                    "المبلغ المدفوع أكبر من قيمة الطلب."
                )

            elif remaining > 0:

                st.markdown(
                    f"""
                    <div class="panel"
                         style="padding:14px;
                                margin-top:10px;">
                        <span>
                            المتبقي
                        </span>
                        <span class="remaining">
                            {remaining:,.2f} ج
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            elif total_cost > 0:

                st.success(
                    "✓ تم دفع الطلب بالكامل."
                )

        with col2:

            st.markdown(
                """
                <div class="panel">
                    <div class="panel-title">
                        📦 التنفيذ
                    </div>
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
                "حالة الطلب",
                statuses,
                index=statuses.index(
                    current_status
                )
            )

        if st.button(
            "حفظ التعديلات",
            use_container_width=True
        ):

            if (
                final_deposit > total_cost
                and
                total_cost > 0
            ):

                st.error(
                    "لا يمكن دفع مبلغ أكبر من قيمة الطلب."
                )

            else:

                new_payment_status = calculate_payment(
                    total_cost,
                    final_deposit
                )

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
                        final_deposit,
                        new_payment_status,
                        new_order_status,
                        selected_id
                    )
                )

                conn.commit()
                conn.close()

                backup_result = backup_after_save()

                st.success(
                    "تم تحديث الطلب."
                )

                if not backup_result["success"]:

                    st.warning(
                        "تم التحديث، لكن لم تتم المزامنة مع Drive: "
                        +
                        str(
                            backup_result["error"]
                        )
                    )

                st.rerun()


# =========================================================
# DAILY NOTE
# =========================================================

elif choice == "📝  المفكرة":

    st.markdown(
        """
        <div class="panel">
            <div class="panel-title">
                المفكرة اليومية
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    today_iso = date.today().isoformat()

    current_note = get_today_note()

    note = st.text_area(
        "ملاحظة اليوم",
        value=current_note,
        height=260,
        placeholder="اكتب ملاحظات اليوم..."
    )

    if st.button(
        "حفظ الملاحظة",
        use_container_width=True
    ):

        save_today_note(
            note.strip()
        )

        backup_result = backup_after_save()

        st.success(
            "تم حفظ الملاحظة."
        )

        if not backup_result["success"]:

            st.warning(
                "تم الحفظ، لكن لم تتم المزامنة مع Drive: "
                +
                str(
                    backup_result["error"]
                )
            )

        st.rerun()

    recent = get_recent_notes(10)

    if not recent.empty:

        st.markdown(
            "<br>",
            unsafe_allow_html=True
        )

        for _, row in recent.iterrows():

            st.markdown(
                f"""
                <div class="note-card">
                    <div class="note-date">
                        📅 {row["note_date"]}
                    </div>
                    <div class="note-text">
                        {row["note_text"]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )


# =========================================================
# GOOGLE DRIVE
# =========================================================

elif choice == "☁️  Google Drive":

    st.markdown(
        """
        <div class="panel">
            <div class="panel-title">
                ☁️ Google Drive
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if not drive_backup_configured():

        st.error(
            "النسخ الاحتياطي غير مُهيأ."
        )

        st.info(
            "ضع DRIVE_BACKUP_URL و DRIVE_BACKUP_TOKEN "
            "داخل Streamlit Secrets."
        )

    else:

        st.success(
            "✓ Google Drive متصل"
        )

        db_file = FilePath(
            DB_NAME
        )

        if db_file.exists():

            db_size = (
                db_file.stat().st_size
                /
                1024
            )

            st.info(
                f"قاعدة البيانات: "
                f"{db_size:.1f} KB"
            )

        remote = drive_backup_info()

        if (
            remote
            and
            remote.get("found")
        ):

            st.success(
                "آخر نسخة: "
                +
                str(
                    remote.get(
                        "filename",
                        EXCEL_BACKUP_FILENAME
                    )
                )
            )

        else:

            st.info(
                "لا توجد نسخة Backup حتى الآن."
            )

        st.markdown(
            "<br>",
            unsafe_allow_html=True
        )

        if st.button(
            "☁️ Backup الآن",
            use_container_width=True
        ):

            with st.spinner(
                "جاري رفع النسخة..."
            ):

                result = drive_backup_db()

            if result["success"]:

                st.success(
                    "✓ تم رفع النسخة بنجاح."
                )

            else:

                st.error(
                    "فشل Backup: "
                    +
                    str(
                        result["error"]
                    )
                )

        st.markdown(
            "<br>",
            unsafe_allow_html=True
        )

        st.warning(
            "الاسترجاع سيستبدل قاعدة البيانات الحالية."
        )

        if st.button(
            "🔄 استرجاع آخر Backup",
            use_container_width=True
        ):

            with st.spinner(
                "جاري الاسترجاع..."
            ):

                result = drive_restore_latest()

            if result["success"]:

                st.success(
                    "✓ تم استرجاع النسخة."
                )

                st.rerun()

            else:

                st.error(
                    "فشل الاسترجاع: "
                    +
                    str(
                        result["error"]
                    )
                )


# =========================================================
# FOOTER
# =========================================================

st.markdown(
    """
    <div style="
        text-align:center;
        color:#3f4b5e;
        font-size:9px;
        padding:35px 0 5px;
        letter-spacing:1px;
    ">
        ZERO ADVERTISING
        <br>
        <span style="color:#a91425;">
            PRINT • DESIGN • ADVERTISING
        </span>
    </div>
    """,
    unsafe_allow_html=True
)
