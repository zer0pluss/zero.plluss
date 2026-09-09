import base64
import sqlite3
from datetime import date, datetime

import pandas as pd
import streamlit as st


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="ZERO Advertising | Management System",
    layout="wide",
    initial_sidebar_state="expanded",
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
    return sqlite3.connect(DB_NAME)


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

    # Daily notes / notebook
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
            background-repeat: non-repeat;
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

@keyframes shimmer {{
    0% {{ background-position: -500px 0; }}
    100% {{ background-position: 500px 0; }}
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
}}

.hero-sub {{
    color: #8492a6;
    font-size: 12px;
    margin-top: 3px;
}}

.online {{
    display: inline-flex;
    align-items: center;
    gap: 7px;
    background: rgba(34,197,94,.08);
    border: 1px solid rgba(34,197,94,.20);
    color: #86efac;
    border-radius: 30px;
    padding: 7px 12px;
    font-size: 11px;
}}

.online-dot {{
    width: 7px;
    height: 7px;
    background: #22c55e;
    border-radius: 50%;
    box-shadow: 0 0 10px #22c55e;
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

</style>
        """,
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
                <div class="brand-name">ZERO Advertising</div>
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
    ]

    choice = st.selectbox(
        "القائمة",
        menu,
        label_visibility="collapsed"
    )

    st.divider()

    # Small preview of today's note
    today_note = get_today_note()

    st.markdown(
        '<div class="side-label">ملاحظة اليوم</div>',
        unsafe_allow_html=True
    )

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
time_text = datetime.now().strftime("%I:%M %p")

st.markdown(
    f"""
    <div class="hero">
        <div style="display:flex;justify-content:space-between;
                    align-items:center;gap:20px;direction:ltr">
            <div>
                <div class="hero-title">ZERO Advertising | Management System</div>
                <div class="hero-title"> {today_text} &nbsp</div>
                <div class="hero-sub">
                    نظام إدارة الطلبات والعملاء والمبيعات
                    &nbsp; • &nbsp; {today_text} &nbsp; • &nbsp; {time_text}
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
            st.markdown(
                '<div class="mini-title">👤 بيانات العميل</div>',
                unsafe_allow_html=True
            )

            customer_name = st.text_input(
                "اسم العميل *",
                placeholder="مثال: أحمد محمد"
            )

            customer_phone = st.text_input(
                "رقم التليفون",
                placeholder="01XXXXXXXXX"
            )

        with col2:
            st.markdown(
                '<div class="mini-title">📄 تفاصيل الطلب</div>',
                unsafe_allow_html=True
            )

            order_details = st.text_area(
                "تفاصيل الطلب *",
                placeholder="مثال: 500 فلاير — مقاس A5 — وجهين — ألوان...",
                height=155
            )

        with col3:
            st.markdown(
                '<div class="mini-title">💰 الحساب والحالة</div>',
                unsafe_allow_html=True
            )

            total_cost = st.number_input(
                "التكلفة الإجمالية (جنيه)",
                min_value=0.0,
                step=10.0,
                format="%.2f"
            )

            deposit = st.number_input(
                "المبلغ المدفوع / العربون",
                min_value=0.0,
                step=10.0,
                format="%.2f"
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

                st.success(
                    f"✅ تم حفظ طلب العميل «{customer_name}» بنجاح."
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

        search_col, filter_col = st.columns([2, 1])

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
                st.success("✅ تم تحديث الطلب بنجاح.")
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

        st.success(
            f"✅ تم حفظ ملاحظة يوم {today_iso}."
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
