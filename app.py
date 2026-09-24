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
# CLOUD SYNC — ONE Google Drive FILE (Google Spreadsheet)
# ---------------------------------------------------------
# The cloud backup is ONE spreadsheet named:
#     ZERO_DATABASE_BACKUP
#
# It contains:
#   - customers       -> exact database columns
#   - orders          -> exact database columns
#   - daily_notes     -> exact database columns
#   - orders_details  -> easy-to-read order view with customer data
#
# Every save updates the SAME spreadsheet file. No new backup file
# is created for each order.
#
# Streamlit Cloud Secrets:
#   DRIVE_BACKUP_URL = "YOUR_APPS_SCRIPT_WEB_APP_URL"
#   DRIVE_BACKUP_TOKEN = "YOUR_TOKEN"
# =========================================================

import io
import json
import shutil
import requests

DB_NAME = "print_shop.db"
CLOUD_FILE_NAME = "ZERO_DATABASE_BACKUP"

# Tables that are real SQLite tables. We also create a readable
# "orders_details" view in the cloud spreadsheet; it is NOT a DB table.
CORE_TABLES = ("customers", "orders", "daily_notes")


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
        return {
            "success": False,
            "error": response.text[:1000] or f"HTTP {response.status_code}",
        }


def _serialize_cell(value):
    """Convert SQLite values to JSON/Google-Sheets-safe values."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _sqlite_tables_and_schema(conn):
    rows = conn.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()

    schema = []
    for name, create_sql in rows:
        if not create_sql:
            continue
        schema.append(
            {
                "name": str(name),
                "create_sql": str(create_sql),
            }
        )
    return schema


def _build_cloud_payload():
    """Read the whole SQLite DB, preserving every real table/column."""
    conn = get_connection()
    try:
        schema = _sqlite_tables_and_schema(conn)
        tables = {}

        for item in schema:
            table = item["name"]
            columns = [
                row[1]
                for row in conn.execute(
                    f'PRAGMA table_info("{table.replace(chr(34), chr(34)*2)}")'
                ).fetchall()
            ]
            rows = conn.execute(
                f'SELECT * FROM "{table.replace(chr(34), chr(34)*2)}"'
            ).fetchall()

            tables[table] = {
                "columns": columns,
                "rows": [
                    [_serialize_cell(v) for v in row]
                    for row in rows
                ],
            }

        # A readable joined order sheet for quick human viewing.
        try:
            joined = conn.execute(
                """
                SELECT
                    o.order_id,
                    o.customer_id,
                    c.name AS customer_name,
                    c.phone AS customer_phone,
                    o.order_details,
                    o.order_date,
                    o.total_cost,
                    o.deposit,
                    o.payment_status,
                    o.order_status
                FROM orders o
                LEFT JOIN customers c ON c.customer_id = o.customer_id
                ORDER BY o.order_id ASC
                """
            ).fetchall()

            tables["_orders_details"] = {
                "columns": [
                    "order_id",
                    "customer_id",
                    "customer_name",
                    "customer_phone",
                    "order_details",
                    "order_date",
                    "total_cost",
                    "deposit",
                    "payment_status",
                    "order_status",
                ],
                "rows": [
                    [_serialize_cell(v) for v in row]
                    for row in joined
                ],
            }
        except Exception:
            # Keep the backup working even if the convenience sheet cannot
            # be built for some reason.
            pass

        return {
            "schema": schema,
            "tables": tables,
        }
    finally:
        conn.close()


def drive_backup_db():
    """
    Sync the COMPLETE local SQLite database to ONE Google Spreadsheet.
    The Apps Script updates the same Drive file every time.
    Includes automatic retry for short-lived network failures.
    """
    result = {"success": False, "error": None}

    if not drive_backup_configured():
        result["error"] = (
            "النسخ الاحتياطي غير مُهيأ. راجع DRIVE_BACKUP_URL "
            "و DRIVE_BACKUP_TOKEN في Streamlit Secrets."
        )
        return result

    if not FilePath(DB_NAME).exists():
        result["error"] = "ملف قاعدة البيانات غير موجود."
        return result

    try:
        payload = {
            "action": "backup",
            "token": DRIVE_BACKUP_TOKEN,
            "filename": CLOUD_FILE_NAME,
            "database": _build_cloud_payload(),
        }

        last_error = None
        response = None
        parsed = None

        for attempt in range(2):
            try:
                response = requests.post(
                    DRIVE_BACKUP_URL,
                    json=payload,
                    timeout=120,
                )
                parsed = _json_response(response)

                if response.ok and parsed.get("success"):
                    result["success"] = True
                    result["filename"] = parsed.get(
                        "filename", CLOUD_FILE_NAME
                    )
                    result["url"] = parsed.get("url", "")
                    result["tables"] = parsed.get("tables", [])
                    return result

                last_error = (
                    parsed.get("error")
                    or f"HTTP {response.status_code}"
                )
            except Exception as exc:
                last_error = str(exc)

        result["error"] = last_error or "فشل الاتصال بخدمة Google Drive."
        return result

    except Exception as exc:
        result["error"] = str(exc)
        return result


def _coerce_restore_value(value, declared_type):
    """Convert Google Sheets values back to SQLite-friendly values."""
    if value == "":
        return None

    typ = (declared_type or "").upper()

    if "INT" in typ:
        try:
            return int(float(value))
        except Exception:
            return value

    if any(x in typ for x in ("REAL", "FLOA", "DOUB", "NUM", "DEC")):
        try:
            return float(value)
        except Exception:
            return value

    return str(value)


def _quote_identifier(name):
    return '"' + str(name).replace('"', '""') + '"'


def _rebuild_db_from_cloud_payload(cloud_data, target_path):
    """Build a valid SQLite DB from schema + cloud table data."""
    schema = cloud_data.get("schema") or []
    tables = cloud_data.get("tables") or {}

    real_tables = [
        item for item in schema
        if item.get("name") in tables and item.get("name") != "_orders_details"
    ]

    if not real_tables:
        raise ValueError("النسخة السحابية لا تحتوي على جداول قاعدة البيانات.")

    target = FilePath(target_path)
    if target.exists():
        target.unlink()

    conn = sqlite3.connect(str(target), timeout=30)
    conn.execute("PRAGMA foreign_keys=OFF")

    try:
        # Create every table using its original CREATE TABLE SQL.
        for item in real_tables:
            create_sql = item.get("create_sql")
            if not create_sql:
                raise ValueError(
                    f"لا يوجد مخطط محفوظ للجدول: {item.get('name')}"
                )
            conn.execute(create_sql)

        # Insert data after ALL tables have been created.
        for item in real_tables:
            table_name = item["name"]
            table = tables.get(table_name, {})
            columns = table.get("columns") or []
            rows = table.get("rows") or []

            if not columns:
                continue

            escaped_table = _quote_identifier(table_name)
            escaped_cols = ",".join(_quote_identifier(c) for c in columns)
            placeholders = ",".join(["?"] * len(columns))

            pragma_rows = conn.execute(
                f'PRAGMA table_info({_quote_identifier(table_name)})'
            ).fetchall()

            type_by_col = {
                row[1]: row[2]
                for row in pragma_rows
            }

            insert_sql = (
                f"INSERT INTO {escaped_table} "
                f"({escaped_cols}) VALUES ({placeholders})"
            )

            converted_rows = []
            for row in rows:
                padded = list(row) + [""] * max(0, len(columns) - len(row))
                padded = padded[:len(columns)]
                converted_rows.append(
                    tuple(
                        _coerce_restore_value(
                            value,
                            type_by_col.get(col, ""),
                        )
                        for col, value in zip(columns, padded)
                    )
                )

            conn.executemany(insert_sql, converted_rows)

        conn.commit()

        integrity = conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise ValueError(
                "فشل فحص سلامة قاعدة البيانات بعد الاسترجاع."
            )
    finally:
        conn.close()


def drive_restore_latest():
    """Download the ONE cloud spreadsheet snapshot and restore SQLite."""
    result = {"success": False, "error": None}

    if not drive_backup_configured():
        result["error"] = "النسخ الاحتياطي غير مُهيأ."
        return result

    try:
        response = requests.get(
            DRIVE_BACKUP_URL,
            params={
                "action": "download",
                "token": DRIVE_BACKUP_TOKEN,
            },
            timeout=120,
        )

        payload = _json_response(response)

        if not response.ok or not payload.get("success"):
            result["error"] = (
                payload.get("error")
                or f"HTTP {response.status_code}"
            )
            return result

        cloud_data = payload.get("database")
        if not cloud_data:
            raise ValueError(
                "لم يتم العثور على بيانات قاعدة البيانات في النسخة السحابية."
            )

        temp_path = FilePath(DB_NAME + ".restore_tmp")
        _rebuild_db_from_cloud_payload(cloud_data, temp_path)

        # Keep a local safety copy before replacing the current DB.
        db_file = FilePath(DB_NAME)
        if db_file.exists():
            shutil.copy2(
                db_file,
                (
                    "print_shop_before_restore_"
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                ),
            )

        shutil.move(str(temp_path), DB_NAME)

        result["success"] = True
        result["filename"] = payload.get(
            "filename",
            CLOUD_FILE_NAME,
        )
        result["url"] = payload.get("url", "")
        return result

    except Exception as exc:
        try:
            FilePath(DB_NAME + ".restore_tmp").unlink(missing_ok=True)
        except Exception:
            pass

        result["error"] = str(exc)
        return result


def drive_backup_info():
    """Get status and direct Google Sheets URL."""
    if not drive_backup_configured():
        return None

    try:
        response = requests.get(
            DRIVE_BACKUP_URL,
            params={
                "action": "status",
                "token": DRIVE_BACKUP_TOKEN,
            },
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


# =========================================================
# FIRST RUN
# If the local DB is missing but the ONE cloud file exists,
# restore it automatically.
# =========================================================
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
            opacity: 0.077;
            filter: none;
            pointer-events: none;
            z-index: 0;
        }}
        """

    st.markdown(
        f"""
<style>

/* =========================================================
   CORE
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

#MainMenu,
footer {{
    visibility: hidden;
}}

header {{
    background: transparent !important;
}}


/* =========================================================
   ANIMATIONS
   ========================================================= */

@keyframes fadeUp {{
    from {{
        opacity: 0;
        transform: translateY(18px);
    }}
    to {{
        opacity: 1;
        transform: translateY(0);
    }}
}}

@keyframes pulseRed {{
    0%, 100% {{
        box-shadow: 0 0 0 0 rgba(226,27,43,.20);
    }}
    50% {{
        box-shadow: 0 0 0 8px rgba(226,27,43,0);
    }}
}}

.fade-up {{
    animation: fadeUp .55s ease both;
}}

.fade-up-2 {{
    animation: fadeUp .70s ease both;
}}

.fade-up-3 {{
    animation: fadeUp .85s ease both;
}}


/* =========================================================
   SIDEBAR
   ========================================================= */

section[data-testid="stSidebar"] {{
    background:
        linear-gradient(180deg, #070c15 0%, #0a101b 55%, #060a12 100%)
        !important;
    border-left: 1px solid rgba(226,27,43,.65);
    box-shadow: -15px 0 45px rgba(0,0,0,.35);
    overflow: hidden !important;
}}

section[data-testid="stSidebar"] > div {{
    padding: 1rem .85rem 1.5rem;
}}

section[data-testid="stSidebar"] * {{
    color: #f1f5f9 !important;
}}

.brand-box {{
    text-align: center;
    padding: 8px 4px 16px;
}}

.brand-logo {{
    width: 120px;
    height: 120px;
    object-fit: cover;
    border-radius: 18px;
    border: 1px solid rgba(255,255,255,.13);
    box-shadow: 0 18px 45px rgba(0,0,0,.45);
    animation: fadeUp .6s ease both;
}}

.brand-name {{
    font-size: 21px;
    font-weight: 800;
    margin-top: 11px;
    letter-spacing: .3px;
}}

.brand-caption {{
    color: #7f8da3 !important;
    font-size: 11px;
    margin-top: 2px;
}}

.side-label {{
    color: #69778b !important;
    font-size: 10px;
    margin: 13px 3px 7px;
    letter-spacing: .4px;
}}

.side-note {{
    background: linear-gradient(145deg, rgba(20,30,48,.94), rgba(9,15,26,.94));
    border: 1px solid rgba(148,163,184,.13);
    border-radius: 14px;
    padding: 13px;
    margin-top: 12px;
}}

.side-note-title {{
    font-weight: 800;
    font-size: 13px;
    color: #f8fafc !important;
}}

.side-note-date {{
    font-size: 10px;
    color: #7f8da3 !important;
    margin-top: 3px;
}}

.side-note-text {{
    margin-top: 8px;
    font-size: 11px;
    line-height: 1.8;
    color: #b9c3d1 !important;
    white-space: pre-wrap;
}}


/* =========================================================
   HEADER
   ========================================================= */

.hero {{
    background:
        linear-gradient(110deg, rgba(18,28,45,.92), rgba(8,14,25,.82));
    border: 1px solid rgba(148,163,184,.14);
    border-radius: 20px;
    padding: 20px 24px;
    margin-bottom: 18px;
    position: relative;
    overflow: hidden;
    animation: fadeUp .45s ease both;
}}

.hero::after {{
    content: "";
    position: absolute;
    top: 0;
    right: 0;
    width: 4px;
    height: 100%;
    background: linear-gradient(#ff2639, #a90e1e);
    animation: pulseRed 2.2s infinite;
}}

.hero-title {{
    font-size: 28px;
    font-weight: 800;
    color: #ffffff;
    line-height: 1.35;
    word-break: break-word;
}}

.hero-sub {{
    color: #8492a6;
    font-size: 12px;
    margin-top: 3px;
}}


/* =========================================================
   STAT CARDS
   ========================================================= */

.stat-card {{
    background:
        linear-gradient(145deg, rgba(20,31,50,.94), rgba(9,15,26,.92));
    border: 1px solid rgba(148,163,184,.12);
    border-radius: 17px;
    padding: 18px 19px;
    min-height: 118px;
    position: relative;
    overflow: hidden;
    transition: transform .25s ease, border-color .25s ease, box-shadow .25s ease;
    animation: fadeUp .6s ease both;
}}

.stat-card:hover {{
    transform: translateY(-5px);
    border-color: rgba(226,27,43,.42);
    box-shadow: 0 16px 35px rgba(0,0,0,.28);
}}

.stat-card::before {{
    content: "";
    position: absolute;
    top: 0;
    right: 0;
    width: 3px;
    height: 100%;
    background: #e21b2b;
}}

.stat-icon {{
    font-size: 22px;
}}

.stat-title {{
    color: #78869a;
    font-size: 11px;
    margin-top: 5px;
}}

.stat-value {{
    color: #f8fafc;
    font-size: 25px;
    font-weight: 800;
    margin-top: 1px;
}}


/* =========================================================
   CARDS
   ========================================================= */

.panel {{
    background:
        linear-gradient(145deg, rgba(17,28,46,.90), rgba(7,13,24,.86));
    border: 1px solid rgba(148,163,184,.13);
    border-radius: 19px;
    padding: 22px;
    margin-bottom: 18px;
    box-shadow: 0 18px 50px rgba(0,0,0,.20);
    animation: fadeUp .65s ease both;
}}

.panel-title {{
    font-size: 20px;
    font-weight: 800;
    color: #f8fafc;
}}

.panel-sub {{
    color: #69788d;
    font-size: 11px;
    margin-top: 2px;
    margin-bottom: 18px;
}}

.mini-title {{
    color: #d8dee8;
    font-size: 14px;
    font-weight: 800;
    margin-bottom: 9px;
}}


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

input, textarea {{
    color: #f8fafc !important;
}}

input::placeholder,
textarea::placeholder {{
    color: #536176 !important;
}}

label {{
    color: #cbd5e1 !important;
    font-size: 12px !important;
    font-weight: 600 !important;
}}


/* =========================================================
   BUTTONS
   ========================================================= */

.stButton > button,
.stFormSubmitButton > button {{
    border: 0 !important;
    border-radius: 10px !important;
    min-height: 44px;
    background: linear-gradient(135deg, #f21f33, #bc1021) !important;
    color: #fff !important;
    font-weight: 800 !important;
    transition: transform .2s ease, box-shadow .2s ease, filter .2s ease;
}}

.stButton > button:hover,
.stFormSubmitButton > button:hover {{
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


/* =========================================================
   MESSAGES
   ========================================================= */

div[data-testid="stAlert"] {{
    border-radius: 11px;
}}

.remaining-box {{
    margin-top: 10px;
    padding: 14px 16px;
    border-radius: 12px;
    border: 1px solid rgba(245, 158, 11, .45);
    background: linear-gradient(135deg, rgba(120, 53, 15, .34), rgba(69, 26, 3, .20));
    color: #fbbf24;
    font-size: 16px;
    font-weight: 800;
    text-align: center;
    box-shadow: 0 8px 24px rgba(245, 158, 11, .08);
}}

.remaining-paid {{
    border-color: rgba(34, 197, 94, .42);
    background: linear-gradient(135deg, rgba(20, 83, 45, .34), rgba(5, 46, 22, .20));
    color: #86efac;
    box-shadow: 0 8px 24px rgba(34, 197, 94, .08);
}}

.remaining-error {{
    border-color: rgba(239, 68, 68, .48);
    background: linear-gradient(135deg, rgba(127, 29, 29, .34), rgba(69, 10, 10, .20));
    color: #fca5a5;
    box-shadow: 0 8px 24px rgba(239, 68, 68, .08);
}}

.cost-hint {{
    color: #7f8da3;
    font-size: 10px;
    margin-top: -4px;
    margin-bottom: 7px;
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
    color: #465267;
    font-size: 10px;
    padding: 24px 0 4px;
}}

.footer strong {{
    color: #e21b2b;
}}


/* =========================================================
   MOBILE FIXES
   ========================================================= */

@media (max-width: 768px) {{

    .hero-title {{
        font-size: 20px;
    }}

    .panel-title {{
        font-size: 17px;
    }}

    div[data-testid="stHorizontalBlock"] {{
        flex-wrap: wrap !important;
        gap: 0.6rem;
    }}

    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
        flex: 1 1 100% !important;
        min-width: 100% !important;
        width: 100% !important;
    }}

    .stat-card {{
        min-height: 95px;
        padding: 14px 15px;
    }}

    .stat-value {{
        font-size: 22px;
    }}

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
    # لو التكلفة غير محددة، لا نحسب متبقي ولا نعرض رقم سالب/خاطئ.
    if total <= 0:
        if deposit > 0:
            return f"تم تسجيل المدفوع: {deposit:,.2f} ج — التكلفة غير محددة"
        return "لم يدفع"

    if deposit >= total:
        return "تم الدفع بالكامل"

    if deposit > 0:
        return f"تم دفع عربون — المتبقي: {total - deposit:,.2f} ج"

    return "لم يدفع"


def parse_money_input(value):
    """Convert a user-entered money string to float; blank means zero."""
    if value is None:
        return 0.0

    value = str(value).strip()
    if not value:
        return 0.0

    # Accept Arabic-Indic and Persian digits as well as Western digits.
    translation = str.maketrans(
        "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
        "01234567890123456789"
    )
    value = value.translate(translation)
    value = value.replace("،", ",").replace(" ", "")
    value = value.replace(",", "")

    try:
        amount = float(value)
    except ValueError:
        raise ValueError("اكتب رقمًا صحيحًا للتكلفة أو المبلغ المدفوع.")

    if amount < 0:
        raise ValueError("المبلغ لا يمكن أن يكون بالسالب.")

    return amount


def remaining_box(total, deposit):
    """Render a highly visible remaining-balance box."""
    if total <= 0:
        return

    remaining = total - deposit

    if remaining > 0:
        st.markdown(
            f'<div class="remaining-box">💳 المتبقي على العميل: {remaining:,.2f} جنيه</div>',
            unsafe_allow_html=True,
        )
    elif remaining == 0:
        st.markdown(
            '<div class="remaining-box remaining-paid">✅ تم دفع قيمة الطلب بالكامل</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="remaining-box remaining-error">⚠️ المدفوع أكبر من قيمة الطلب بمقدار {abs(remaining):,.2f} جنيه</div>',
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
        "☁️  المزامنة السحابية (ملف واحد)",
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
                <div class="side-note-title">📌 Today note</div>
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
                <div class="side-note-title">📌 مفيش ملاحظات</div>
                <div class="side-note-date">
                    اكتب ملاحظة من قسم المفكرة اليومية
                </div>
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
        <div style="display:flex;justify-content:space-between;
                    align-items:center;gap:20px;direction:ltr">
            <div>
                <div class="hero-title">ZERO Advertising | Management System</div>
                <div class="hero-sub">{today_text}</div>
            </div>
        </div>
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
    ("📦", "إجمالي الطلبات", total_orders),
    ("🚀", "طلبات قيد التنفيذ", in_progress),
    ("✅", "تم التسليم", completed),
    ("💰", "إجمالي قيمة الطلبات", f"{total_sales:,.0f} ج"),
]

for col, (icon, title, value) in zip([c1, c2, c3, c4], stats):
    with col:
        st.markdown(
            f"""
            <div class="stat-card">
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
            <div class="panel-sub">
                أضف بيانات العميل والطلب والتكلفة وحالة التنفيذ.
            </div>
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
                placeholder="مثال: 500 فلاير — مقاس A5 — وجهين — ألوان...",
                height=155
            )

        with col3:

            total_cost_text = st.text_input(
                "التكلفة الإجمالية (جنيه)",
                value="",
                placeholder="اكتب التكلفة بدون أصفار مسبقة"
            )

            st.markdown(
                '<div class="cost-hint">اترك الخانة فارغة لو لا توجد تكلفة محددة. لن يظهر أي متبقي بدون تكلفة.</div>',
                unsafe_allow_html=True,
            )

            deposit_text = st.text_input(
                "المبلغ المدفوع / العربون",
                value="",
                placeholder="اكتب المبلغ المدفوع"
            )

            order_status = st.selectbox(
                "حالة الطلب",
                ["قيد التنفيذ", "جاهز للتسليم", "تم التسليم"]
            )

        st.divider()

        try:
            total_cost = parse_money_input(total_cost_text)
            deposit = parse_money_input(deposit_text)
            money_input_error = None
        except ValueError as exc:
            total_cost = 0.0
            deposit = 0.0
            money_input_error = str(exc)

        if money_input_error:
            st.error(f"❌ {money_input_error}")
        elif total_cost > 0:
            remaining_box(total_cost, deposit)

        save = st.form_submit_button(
            "💾  حفظ الطلب",
            use_container_width=True
        )

        if save:

            if money_input_error:
                st.error(f"❌ {money_input_error}")

            elif not customer_name.strip():
                st.error("❌ اكتب اسم العميل.")

            elif not order_details.strip():
                st.error("❌ اكتب تفاصيل الطلب.")

            elif deposit > total_cost and total_cost > 0:
                st.error("❌ العربون لا يمكن أن يكون أكبر من إجمالي الطلب.")

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

                st.success(
                    f"✅ تم حفظ طلب العميل «{customer_name}» بنجاح."
                )
                if not backup_result["success"]:
                    st.warning(
                        "⚠️ الداتا اتحفظت، لكن حصلت مشكلة في المزامنة السحابية: "
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
            <div class="panel-sub">
                ابحث عن العملاء واستعرض جميع الطلبات والحسابات.
            </div>
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
        JOIN customers c
            ON o.customer_id = c.customer_id
        ORDER BY o.order_id DESC
        """,
        conn
    )

    conn.close()

    if df.empty:
        st.info("📭 لا توجد طلبات مسجلة حالياً.")

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

        # أضف المتبقي كعمود مستقل، لكن لو التكلفة غير محددة
        # اترك المتبقي فارغًا بدل عرض قيمة سالبة مثل -1000.
        df["المتبقي"] = (
            df["الإجمالي"].fillna(0) - df["العربون"].fillna(0)
        )
        df.loc[df["الإجمالي"].fillna(0) <= 0, "المتبقي"] = pd.NA

        def remaining_cell_style(value):
            if pd.isna(value):
                return ""
            if value > 0:
                return (
                    "background-color: rgba(245, 158, 11, .20); "
                    "color: #fbbf24; font-weight: 900;"
                )
            if value == 0:
                return (
                    "background-color: rgba(34, 197, 94, .18); "
                    "color: #86efac; font-weight: 900;"
                )
            return (
                "background-color: rgba(239, 68, 68, .18); "
                "color: #fca5a5; font-weight: 900;"
            )

        styled_df = df.style.apply(
            lambda col: [remaining_cell_style(v) for v in col],
            subset=["المتبقي"]
        )

        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            height=520,
            column_config={
                "الإجمالي": st.column_config.NumberColumn(
                    format="%.2f ج"
                ),
                "العربون": st.column_config.NumberColumn(
                    format="%.2f ج"
                ),
                "المتبقي": st.column_config.NumberColumn(
                    format="%.2f ج"
                ),
            }
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
            <div class="panel-sub">
                عدّل العربون وحالة التنفيذ وسيتم تحديث حالة الدفع تلقائياً.
            </div>
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

        st.info("📭 لا توجد طلبات لتعديلها.")

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

            new_deposit_text = st.text_input(
                "المبلغ المدفوع",
                value="" if current_deposit == 0 else f"{current_deposit:g}",
                placeholder="اكتب المبلغ المدفوع"
            )

            try:
                new_deposit = parse_money_input(new_deposit_text)
                edit_money_input_error = None
            except ValueError as exc:
                new_deposit = 0.0
                edit_money_input_error = str(exc)

            remaining = total_cost - new_deposit

            if edit_money_input_error:
                st.error(f"❌ {edit_money_input_error}")
                new_payment_status = current[2]
            elif new_deposit > total_cost and total_cost > 0:
                st.error("❌ المبلغ المدفوع أكبر من قيمة الطلب.")
                new_payment_status = current[2]
            else:
                new_payment_status = calculate_payment(
                    total_cost,
                    new_deposit
                )

                if total_cost > 0:
                    if remaining > 0:
                        st.markdown(
                            f'<div class="remaining-box">💳 المتبقي على العميل: {remaining:,.2f} جنيه</div>',
                            unsafe_allow_html=True,
                        )
                    elif remaining == 0:
                        st.markdown(
                            '<div class="remaining-box remaining-paid">✅ تم دفع الطلب بالكامل</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f'<div class="remaining-box remaining-error">⚠️ المدفوع أكبر من قيمة الطلب بمقدار {abs(remaining):,.2f} جنيه</div>',
                            unsafe_allow_html=True,
                        )

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

            if edit_money_input_error:
                st.error(f"❌ {edit_money_input_error}")

            elif new_deposit > total_cost and total_cost > 0:
                st.error("❌ لا يمكن دفع مبلغ أكبر من قيمة الطلب.")

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

                st.success("✅ تم تحديث الطلب بنجاح.")
                if not backup_result["success"]:
                    st.warning(
                        "⚠️ التحديث اتحفظ، لكن حصلت مشكلة في المزامنة السحابية: "
                        + str(backup_result["error"])
                    )
                st.rerun()

    conn.close()

# =========================================================
# 4. DAILY NOTEBOOK
# =========================================================
elif choice == "📝  المفكرة اليومية":

    st.markdown(
        """
        <div class="panel">
            <div class="panel-title">📝 المفكرة اليومية</div>
            <div class="panel-sub">
                اكتب أي ملاحظات أو مهام أو تعليمات خاصة بالمطبعة.
                كل يوم له ملاحظة مستقلة بالتاريخ.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    today = date.today()
    today_iso = today.isoformat()

    st.markdown(
        f"""
        <div class="panel">
            <div class="panel-title">📌 ملاحظة يوم {today_iso}</div>
            <div class="panel-sub">
                أي كلام تكتبه هنا يتم حفظه لهذا اليوم فقط ويمكن تعديله لاحقاً.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    current_note = get_today_note()

    note = st.text_area(
        "اكتب ملاحظتك هنا",
        value=current_note,
        height=260,
        placeholder=(
            "مثال:\n"
            "• أحمد يستلم البانر الساعة 5\n"
            "• مراجعة تصميم محل الملابس\n"
            "• شراء خامة فينيل\n"
            "• الاتصال بالعميل محمد..."
        )
    )

    if st.button(
        "💾  حفظ ملاحظة اليوم",
        use_container_width=True
    ):

        save_today_note(note.strip())
        backup_result = backup_after_save()

        st.success(
            f"✅ تم حفظ ملاحظة يوم {today_iso}."
        )
        if not backup_result["success"]:
            st.warning(
                "⚠️ الملاحظة اتحفظت، لكن حصلت مشكلة في المزامنة السحابية: "
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
                <div class="panel-sub">
                    آخر 10 أيام تم تسجيل ملاحظات بها.
                </div>
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
# 5. CLOUD SYNC — ONE FILE
# =========================================================
elif choice == "☁️  المزامنة السحابية (ملف واحد)":

    st.markdown(
        """
        <div class="panel">
            <div class="panel-title">☁️ المزامنة السحابية — ملف واحد فقط</div>
            <div class="panel-sub">
                كل البيانات تتزامن تلقائياً إلى <strong>ملف Google Sheets واحد</strong>
                داخل Google Drive. كل طلب جديد أو تعديل يظهر في نفس الملف فور نجاح المزامنة،
                بدون إنشاء ملف جديد لكل طلب.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if not drive_backup_configured():

        st.error("❌ المزامنة السحابية غير مُهيأة.")

        st.markdown(
            """
            <div class="panel">
                <div class="panel-title">⚙️ الإعداد لأول مرة</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown(
            """
1) افتح Google Apps Script وأنشئ مشروعاً جديداً.

2) الصق كود:
`google_drive_backup_apps_script_single.gs`

3) من Deploy اختر:
**New deployment → Web app**

4) اجعل:
**Execute as: Me**
و
**Who has access: Anyone**

5) انسخ Web App URL.

6) في Streamlit Cloud → Settings → Secrets ضع:

```toml
DRIVE_BACKUP_URL = "ضع_رابط_Web_App_هنا"
DRIVE_BACKUP_TOKEN = "ضع_نفس_التوكن_الموجود_في_Apps_Script"
```

لا تحتاج Service Account ولا Google Cloud Project ولا Google Sheets API.
            """
        )

    else:

        st.success("✅ المزامنة السحابية متصلة.")

        remote = drive_backup_info()

        if remote and remote.get("found"):

            st.success(
                "☁️ يوجد ملف واحد فقط للنسخة السحابية: "
                + str(remote.get("filename", CLOUD_FILE_NAME))
            )

            if remote.get("url"):
                st.markdown(
                    f"### [📂 فتح ملف البيانات مباشرة على Google Drive]({remote['url']})"
                )

            counts = remote.get("counts") or {}
            if counts:
                st.caption(
                    "عدد السجلات: "
                    + " | ".join(
                        f"{name}: {count}"
                        for name, count in counts.items()
                        if name != "_orders_details"
                    )
                )

        else:

            st.info(
                "📭 الملف السحابي لم يُنشأ بعد. "
                "هيتعمل تلقائياً مع أول حفظ أو من زر المزامنة اليدوي."
            )

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button(
            "☁️  مزامنة كل البيانات الآن",
            use_container_width=True
        ):

            with st.spinner(
                "⏳ جاري تحديث نفس ملف Google Drive..."
            ):

                result = drive_backup_db()

            if result["success"]:

                st.success(
                    "✅ تمت مزامنة قاعدة البيانات كاملة داخل نفس الملف."
                )

                if result.get("url"):
                    st.markdown(
                        f"[📂 فتح ملف البيانات]({result['url']})"
                    )

            else:

                st.error(
                    "❌ فشلت المزامنة:\n\n"
                    + str(result["error"])
                )

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            """
            <div class="panel">
                <div class="panel-title">📊 ماذا ستجد داخل الملف؟</div>
                <div class="panel-sub">
                    <strong>customers</strong> = كل أعمدة جدول العملاء كاملة.<br>
                    <strong>orders</strong> = كل أعمدة جدول الطلبات كاملة.<br>
                    <strong>daily_notes</strong> = كل أعمدة المفكرة كاملة.<br>
                    <strong>orders_details</strong> = نسخة سهلة للقراءة تجمع الطلب مع اسم العميل وتليفونه وباقي التفاصيل.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown(
            "تعديل الطلب داخل البرنامج → حفظ → المزامنة تحدث **نفس الملف**.",
        )

        st.warning(
            "⚠️ زر الاسترجاع يستبدل قاعدة البيانات المحلية بآخر نسخة موجودة في ملف Google Drive."
        )

        if st.button(
            "🔄  استرجاع آخر نسخة من السحابة",
            use_container_width=True
        ):

            with st.spinner(
                "⏳ جاري تنزيل وفحص آخر نسخة..."
            ):

                result = drive_restore_latest()

            if result["success"]:

                st.success(
                    "✅ تم استرجاع آخر نسخة بنجاح."
                )

                st.rerun()

            else:

                st.error(
                    "❌ فشل الاسترجاع:\n\n"
                    + str(result["error"])
                )

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
