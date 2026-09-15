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
# BACKUP TO GOOGLE DRIVE DESKTOP
# ---------------------------------------------------------
# No Google Cloud, Service Account, OAuth, API keys, or paid
# service is needed here. The app copies verified SQLite
# snapshots into the normal Google Drive for desktop folder.
# Google Drive for desktop then syncs those files to your
# personal Google Drive account.
# =========================================================
import shutil
import tempfile


# ===== Robust Google Drive Desktop Backup =====
DRIVE_BACKUP_FOLDER_NAME = "ZERO BACKUPS"
DRIVE_MAX_BACKUPS = 30

def _drive_roots():
    home = Path.home()
    roots = [
        home / "Google Drive" / "My Drive",
        home / "My Drive",
    ]
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        roots += [Path(f"{letter}:/My Drive")]
    seen, result = set(), []
    for p in roots:
        key = str(p).lower()
        if key not in seen and p.exists():
            seen.add(key)
            result.append(p)
    return result

def get_drive_backup_dir():
    """Find My Drive locally and create ZERO BACKUPS automatically."""
    for root in _drive_roots():
        if root.exists() and root.is_dir():
            folder = root / DRIVE_BACKUP_FOLDER_NAME
            folder.mkdir(parents=True, exist_ok=True)
            return folder
    return None

def _verify_sqlite(path):
    try:
        with sqlite3.connect(str(path), timeout=10) as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
        return bool(result and str(result[0]).lower() == "ok")
    except Exception:
        return False

def backup_database_to_drive(db_path="print_shop.db"):
    db = Path(db_path)
    if not db.exists():
        return False, "قاعدة البيانات المحلية غير موجودة."

    if not _verify_sqlite(db):
        return False, "قاعدة البيانات المحلية لم تجتز فحص SQLite."

    folder = get_drive_backup_dir()
    if folder is None:
        return False, "Google Drive for desktop غير موجود أو My Drive غير ظاهر على الجهاز."

    target = folder / f"print_shop_backup_{datetime.now():%Y-%m-%d_%H-%M-%S}.db"
    try:
        shutil.copy2(db, target)

        # Do not report success until the copied file is verified.
        if not target.exists() or target.stat().st_size != db.stat().st_size:
            target.unlink(missing_ok=True)
            return False, "فشل التحقق من نسخة Drive."

        if not _verify_sqlite(target):
            target.unlink(missing_ok=True)
            return False, "نسخة Drive موجودة لكن فحص SQLite فشل."

        backups = sorted(folder.glob("print_shop_backup_*.db"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[DRIVE_MAX_BACKUPS:]:
            try:
                old.unlink()
            except Exception:
                pass

        return True, f"تم الـBackup بنجاح: {target.name}"
    except Exception as e:
        return False, f"فشل الـBackup: {e}"

def list_drive_backups():
    folder = get_drive_backup_dir()
    if folder is None:
        return []
    return sorted(folder.glob("print_shop_backup_*.db"),
                  key=lambda p: p.stat().st_mtime, reverse=True)

def restore_database_from_drive(backup_path, db_path="print_shop.db"):
    backup = Path(backup_path)
    db = Path(db_path)

    if not backup.exists() or not _verify_sqlite(backup):
        return False, "نسخة الـBackup غير موجودة أو غير سليمة."

    try:
        if db.exists():
            safety = db.with_name(
                f"{db.stem}_before_restore_{datetime.now():%Y-%m-%d_%H-%M-%S}{db.suffix}"
            )
            shutil.copy2(db, safety)

        temp = db.with_name(db.stem + "_restore_tmp.db")
        shutil.copy2(backup, temp)
        if not _verify_sqlite(temp):
            temp.unlink(missing_ok=True)
            return False, "فشل فحص النسخة قبل الاستعادة."

        os.replace(temp, db)
        return True, f"تمت الاستعادة بنجاح من: {backup.name}"
    except Exception as e:
        return False, f"فشل الـRestore: {e}"

def render_drive_backup_ui():
    st.subheader("☁️ Backup to Google Drive")
    st.caption("يعمل من خلال Google Drive for desktop — بدون Google Cloud أو Service Account.")

    folder = get_drive_backup_dir()
    if folder is None:
        st.error("Google Drive غير جاهز على هذا الكمبيوتر.")
        st.info("افتح Google Drive for desktop وسجّل الدخول، ثم تأكد أن My Drive ظاهر في File Explorer.")
        return

    st.success(f"Google Drive جاهز ✅\n`{folder}`")

    if st.button("☁️ Backup to Drive", use_container_width=True):
        ok, msg = backup_database_to_drive("print_shop.db")
        (st.success if ok else st.error)(msg)

    backups = list_drive_backups()
    if backups:
        labels = [f"{p.name} — {p.stat().st_size:,} bytes" for p in backups]
        selected_label = st.selectbox("اختر نسخة للاستعادة", labels)
        selected = backups[labels.index(selected_label)]
        if st.button("♻️ Restore selected backup", use_container_width=True):
            ok, msg = restore_database_from_drive(selected)
            (st.success if ok else st.error)(msg)
            if ok:
                st.warning("أعد تشغيل التطبيق بعد الاستعادة.")
    else:
        st.info("لا توجد نسخ احتياطية حتى الآن.")


BACKUP_PREFIX = "ZERO_backup_"
BACKUP_RETENTION = 30


def get_secret(key):
    try:
        value = st.secrets.get(key, "")
        if value:
            return str(value)
    except Exception:
        pass
    return os.environ.get(key, "")


def detect_google_drive_folder():
    """Find common Google Drive for desktop locations on Windows."""
    candidates = []
    user_home = os.environ.get("USERPROFILE") or str(FilePath.home())

    candidates.extend([
        FilePath(user_home) / "Google Drive" / "My Drive",
        FilePath(user_home) / "My Drive",
        FilePath(user_home) / "Google Drive",
    ])

    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        candidates.extend([
            FilePath(f"{letter}:\\My Drive"),
            FilePath(f"{letter}:\\Google Drive"),
        ])

    # Google Drive for desktop commonly appears as a mounted drive
    # (for example G:\\My Drive). Prefer an actually existing My Drive.

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_dir():
                return str(candidate)
        except Exception:
            pass

    return ""


DEFAULT_DRIVE_FOLDER = get_secret("GOOGLE_DRIVE_BACKUP_FOLDER").strip()
if not DEFAULT_DRIVE_FOLDER:
    DEFAULT_DRIVE_FOLDER = detect_google_drive_folder()


def _clean_drive_path(value):
    """Normalize a Windows Google Drive path pasted with or without quotes."""
    if not value:
        return ""
    value = str(value).strip()
    # Users often paste paths as "G:\\My Drive\\ZERO BACKUPS".
    # The quotes are not part of the Windows path.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1].strip()
    value = value.replace("/", "\\")
    return value

def get_drive_folder():
    folder = st.session_state.get("google_drive_backup_folder", DEFAULT_DRIVE_FOLDER)
    folder = _clean_drive_path(folder)
    return FilePath(folder).expanduser() if folder else None


def drive_configured():
    folder = get_drive_folder()
    return bool(folder and folder.exists() and folder.is_dir())


def drive_list_backups():
    folder = get_drive_folder()
    if not folder or not folder.exists():
        return []

    files = []
    try:
        for item in folder.iterdir():
            if item.is_file() and item.name.startswith(BACKUP_PREFIX) and item.suffix.lower() == ".db":
                stat = item.stat()
                files.append({
                    "id": str(item),
                    "name": item.name,
                    "size": str(stat.st_size),
                    "createdTime": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modifiedTime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
    except Exception:
        return []

    return sorted(files, key=lambda x: x.get("createdTime", ""), reverse=True)


def _verify_sqlite(path):
    conn = None
    try:
        conn = sqlite3.connect(str(path), timeout=30)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        return bool(result and result[0] == "ok")
    except Exception:
        return False
    finally:
        if conn:
            conn.close()


def drive_upload_backup():
    """Create a verified snapshot in the local Drive-synced folder."""
    result = {"success": False, "error": None, "file_name": None}
    folder = get_drive_folder()
    db_file = FilePath(DB_NAME)

    if not folder:
        result["error"] = (
            "لم يتم تحديد فولدر Google Drive. ثبّت Google Drive for desktop "
            "ثم اختر فولدر My Drive من خانة مسار Backup."
        )
        return result

    if not folder.exists() or not folder.is_dir():
        result["error"] = f"فولدر Google Drive غير موجود أو غير متاح:\n{folder}"
        return result

    if not db_file.exists():
        result["error"] = "ملف قاعدة البيانات غير موجود."
        return result

    if not _verify_sqlite(db_file):
        result["error"] = "قاعدة البيانات الحالية غير سليمة، وتم إلغاء الـBackup لحماية النسخ القديمة."
        return result

    temp_path = None
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        backup_name = f"{BACKUP_PREFIX}{timestamp}.db"
        final_path = folder / backup_name
        temp_path = folder / f".{backup_name}.tmp"

        shutil.copy2(str(db_file), str(temp_path))

        if temp_path.stat().st_size != db_file.stat().st_size:
            raise IOError("حجم نسخة الـBackup لا يطابق قاعدة البيانات الأصلية.")

        if not _verify_sqlite(temp_path):
            raise IOError("تم نسخ الملف لكن فشل فحص سلامة SQLite.")

        os.replace(str(temp_path), str(final_path))

        if not final_path.exists() or final_path.stat().st_size != db_file.stat().st_size:
            raise IOError("فشل التحقق من النسخة النهائية داخل Google Drive.")

        # Keep newest copies. If cleanup fails, the successful new backup remains.
        backups = drive_list_backups()
        for old_file in backups[BACKUP_RETENTION:]:
            try:
                FilePath(old_file["id"]).unlink(missing_ok=True)
            except Exception:
                pass

        result["success"] = True
        result["file_name"] = backup_name
        return result

    except Exception as exc:
        result["error"] = str(exc)
        return result
    finally:
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


def drive_download_backup(file_id, destination=DB_NAME):
    """Restore a selected verified backup into the local database."""
    result = {"success": False, "error": None}
    temp_path = None

    try:
        source = FilePath(file_id)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError("نسخة الـBackup غير موجودة في Google Drive.")

        if not _verify_sqlite(source):
            raise IOError("نسخة الـBackup تالفة أو ليست قاعدة SQLite سليمة.")

        fd, temp_name = tempfile.mkstemp(prefix="zero_restore_", suffix=".db")
        os.close(fd)
        temp_path = FilePath(temp_name)

        shutil.copy2(str(source), str(temp_path))
        if not _verify_sqlite(temp_path):
            raise IOError("فشل فحص النسخة أثناء الاسترجاع.")

        os.replace(str(temp_path), str(FilePath(destination)))
        temp_path = None

        if not _verify_sqlite(FilePath(destination)):
            raise IOError("تم الاسترجاع لكن فشل الفحص النهائي لقاعدة البيانات.")

        result["success"] = True
        return result

    except Exception as exc:
        result["error"] = str(exc)
        return result
    finally:
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


def drive_latest_backup():
    backups = drive_list_backups()
    return backups[0] if backups else None


def drive_remote_info():
    folder = get_drive_folder()
    backups = drive_list_backups()
    return {
        "configured": bool(folder),
        "folder": str(folder) if folder else "",
        "found": bool(backups),
        "count": len(backups),
        "latest": backups[0] if backups else None,
    }


def backup_after_save():
    return drive_upload_backup()


def restore_from_cloud(file_id=None):
    if file_id:
        return drive_download_backup(file_id)

    latest = drive_latest_backup()
    if not latest:
        return {"success": False, "error": "مفيش Backup موجود على Google Drive."}

    return drive_download_backup(latest["id"])

# =========================================================
# FIRST RUN:
# If there is no local database but a Drive backup exists -> restore it
# =========================================================
if not FilePath(DB_NAME).exists():
    latest_backup = drive_latest_backup()
    if latest_backup:
        drive_download_backup(latest_backup["id"])

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
    if total > 0 and deposit >= total:
        return "تم الدفع بالكامل"
    if deposit > 0:
        return f"تم دفع عربون — المتبقي: {total - deposit:,.2f} ج"
    return "لم يدفع"


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

            total_cost = st.number_input(
                "التكلفة الإجمالية (جنيه)",
                min_value=0.0,
                step=0.0,
                format="%.0f"
            )

            deposit = st.number_input(
                "المبلغ المدفوع / العربون",
                min_value=0.0,
                step=0.0,
            )

            order_status = st.selectbox(
                "حالة الطلب",
                ["قيد التنفيذ", "جاهز للتسليم", "تم التسليم"]
            )

        st.divider()

        if total_cost > 0:
            remaining = total_cost - deposit

            if deposit > total_cost:
                st.warning("⚠️ العربون أكبر من إجمالي قيمة الطلب.")
            elif remaining > 0:
                st.info(f"💳 المتبقي على العميل: {remaining:,.2f} جنيه")
            else:
                st.success("✅ تم دفع قيمة الطلب بالكامل.")

        save = st.form_submit_button(
            "💾  حفظ الطلب",
            use_container_width=True
        )

        if save:

            if not customer_name.strip():
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

        st.dataframe(
            df,
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

            new_deposit = st.number_input(
                "المبلغ المدفوع",
                min_value=0.0,
                value=float(current[1] or 0),
                step=10.0
            )

            remaining = total_cost - new_deposit

            if new_deposit > total_cost and total_cost > 0:
                st.error("❌ المبلغ المدفوع أكبر من قيمة الطلب.")
                new_payment_status = current[2]
            else:
                new_payment_status = calculate_payment(
                    total_cost,
                    new_deposit
                )

                if remaining > 0:
                    st.info(
                        f"المتبقي: {remaining:,.2f} جنيه"
                    )
                elif total_cost > 0:
                    st.success("✅ تم دفع الطلب بالكامل.")

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
# 5. CLOUD BACKUP (Google Drive)
# =========================================================
elif choice == "☁️  النسخ الاحتياطي (Google Drive)":

    st.markdown(
        """
        <div class="panel">
            <div class="panel-title">☁️ حماية البيانات — Google Drive</div>
            <div class="panel-sub">
                النسخ الاحتياطي هنا يتم من خلال فولدر Google Drive الموجود على نفس الكمبيوتر.
                لا يوجد Google Cloud أو Service Account أو API أو اشتراك مدفوع.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # The user only needs Google Drive for desktop installed and signed in.
    current_folder = get_drive_folder()
    current_folder_text = str(current_folder) if current_folder else ""

    st.markdown("### 📁 مكان Backup")
    drive_path = st.text_input(
        "مسار فولدر Google Drive الذي تريد حفظ النسخ بداخله",
        value=current_folder_text,
        placeholder=r"مثال: C:\Users\اسمك\Google Drive\My Drive\ZERO BACKUPS",
        help="يفضل عمل فولدر اسمه ZERO BACKUPS داخل My Drive واستخدام مساره هنا."
    )

    cleaned_drive_path = _clean_drive_path(drive_path)

    if cleaned_drive_path != current_folder_text:
        st.session_state["google_drive_backup_folder"] = cleaned_drive_path
        current_folder = get_drive_folder()

    if not drive_path.strip():
        st.warning(
            "⚠️ لم يتم تحديد فولدر Google Drive. ثبّت Google Drive for desktop "
            "وسجّل دخولك بحساب Google، ثم اختر مسار My Drive هنا."
        )
    elif not current_folder or not current_folder.exists() or not current_folder.is_dir():
        st.error(
            "❌ التطبيق لم يجد الفولدر بهذا المسار على نفس جهاز التشغيل:\n\n"
            f"`{current_folder}`\n\n"
            "لو المسار ظاهر عندك في File Explorer مثل G:\\My Drive\\ZERO BACKUPS، "
            "فلا تكتب علامات اقتباس حوله."
        )
    else:
        st.success(f"✅ فولدر Google Drive جاهز للنسخ:\n`{current_folder}`")

        db_file = FilePath(DB_NAME)
        if db_file.exists():
            db_size = db_file.stat().st_size / 1024
            st.info(
                f"📦 قاعدة البيانات الحالية: `{DB_NAME}` — "
                f"الحجم: {db_size:.1f} KB"
            )

        remote = drive_remote_info()
        if remote.get("found"):
            latest = remote.get("latest") or {}
            st.success(
                f"☁️ موجود {remote.get('count', 0)} نسخة Backup محفوظة."
            )
            st.info(f"🕒 أحدث نسخة: `{latest.get('name', 'غير معروف')}`")
        else:
            st.info("📭 لا توجد نسخة Backup حتى الآن.")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button(
            "☁️ Backup to Drive الآن",
            use_container_width=True
        ):
            with st.spinner("⏳ جاري إنشاء نسخة والتحقق منها..."):
                result = drive_upload_backup()

            if result["success"]:
                st.success(
                    "✅ تم إنشاء الـBackup بنجاح والتحقق من سلامته:\n\n"
                    + str(result["file_name"])
                )
                st.info(
                    "Google Drive for desktop سيقوم بمزامنة الملف مع حسابك."
                )
                st.rerun()
            else:
                st.error("❌ لم يتم اعتبار الـBackup ناجحاً:\n\n" + str(result["error"]))

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            """
            <div class="panel">
                <div class="panel-title">🔄 استرجاع نسخة</div>
                <div class="panel-sub">
                    كل نسخة يتم فحصها قبل الاسترجاع، ويتم عمل Backup للداتا الحالية أولاً.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        backups = drive_list_backups()

        if not backups:
            st.info("📭 مفيش نسخ Backup متاحة للاسترجاع حالياً.")
        else:
            backup_options = {}
            for backup in backups:
                name = backup.get("name", "Backup")
                created = backup.get("createdTime", "")
                size = backup.get("size", "0")
                try:
                    size_kb = float(size) / 1024
                    size_text = f"{size_kb:.1f} KB"
                except Exception:
                    size_text = "الحجم غير معروف"

                label = f"{name} — {size_text}"
                if created:
                    label += f" — {created.replace('T', ' ')[:19]}"
                backup_options[label] = backup["id"]

            selected_backup_label = st.selectbox(
                "📌 اختر النسخة",
                list(backup_options.keys())
            )

            st.warning(
                "⚠️ الاسترجاع سيستبدل قاعدة البيانات الحالية. "
                "سيتم أولاً عمل Backup تلقائي للداتا الحالية، وإذا فشل هذا الـBackup "
                "سيتم إلغاء الاسترجاع."
            )

            if st.button(
                "🔄 استرجاع النسخة المختارة",
                use_container_width=True
            ):
                with st.spinner("⏳ جاري عمل نسخة أمان ثم الاسترجاع..."):
                    safety_backup = drive_upload_backup()

                    if not safety_backup["success"]:
                        st.error(
                            "❌ لم يتم الاسترجاع لأن نسخة الأمان لم تنجح:\n\n"
                            + str(safety_backup["error"])
                        )
                    else:
                        selected_id = backup_options[selected_backup_label]
                        result = drive_download_backup(selected_id)

                        if result["success"]:
                            st.success("✅ تم استرجاع النسخة بنجاح.")
                            st.rerun()
                        else:
                            st.error("❌ فشل الاسترجاع:\n\n" + str(result["error"]))

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
