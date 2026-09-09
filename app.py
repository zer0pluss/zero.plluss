import base64
import sqlite3
import pandas as pd
import streamlit as st


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="ZERO Advertising | Management System",
    page_icon="🖨️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# LOGO
# =========================================================

LOGO_PATH = "zero.jpg"


def get_logo_base64():
    try:
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except:
        return ""


logo_base64 = get_logo_base64()


# =========================================================
# DATABASE
# =========================================================

def get_connection():
    return sqlite3.connect("print_shop.db")


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

    conn.commit()
    conn.close()


init_db()


# =========================================================
# CUSTOM CSS
# =========================================================

def set_custom_design():

    st.markdown(
        f"""
        <style>

        /* =====================================================
           GLOBAL
        ===================================================== */

        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&display=swap');

        * {{
            font-family: 'Cairo', 'Segoe UI', sans-serif !important;
        }}

        html, body, [class*="css"] {{
            direction: rtl;
        }}

        .stApp {{
            background:
                linear-gradient(
                    rgba(5, 10, 20, 0.94),
                    rgba(5, 10, 20, 0.97)
                ),
                url("data:image/jpeg;base64,{logo_base64}");

            background-size: 850px;
            background-repeat: no-repeat;
            background-position: 42% 48%;
            background-attachment: fixed;

            color: #f8fafc;
        }}


        /* =====================================================
           REMOVE STREAMLIT DEFAULTS
        ===================================================== */

        #MainMenu {{
            visibility: hidden;
        }}

        footer {{
            visibility: hidden;
        }}

        header {{
            background: transparent !important;
        }}

        .block-container {{
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            max-width: 1500px;
        }}


        /* =====================================================
           SIDEBAR
        ===================================================== */

        section[data-testid="stSidebar"] {{
            background:
                linear-gradient(
                    180deg,
                    rgba(8,15,30,0.98),
                    rgba(5,10,20,0.99)
                ) !important;

            border-left: 2px solid #e21b2b;
            box-shadow: -10px 0 40px rgba(0,0,0,.35);
        }}

        section[data-testid="stSidebar"] > div {{
            padding-top: 1.5rem;
        }}

        section[data-testid="stSidebar"] * {{
            color: #f8fafc !important;
        }}


        /* =====================================================
           LOGO SIDEBAR
        ===================================================== */

        .sidebar-logo {{
            text-align: center;
            padding: 10px 10px 25px;
        }}

        .sidebar-logo img {{
            width: 145px;
            height: 145px;
            object-fit: cover;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,.12);
            box-shadow:
                0 15px 40px rgba(0,0,0,.5),
                0 0 30px rgba(226,27,43,.15);
        }}

        .brand-title {{
            font-size: 23px;
            font-weight: 800;
            margin-top: 12px;
        }}

        .brand-subtitle {{
            color: #94a3b8;
            font-size: 13px;
        }}


        /* =====================================================
           SIDEBAR SELECTBOX
        ===================================================== */

        section[data-testid="stSidebar"]
        div[data-baseweb="select"] > div {{
            background: #111c31 !important;
            border: 1px solid #27364f !important;
            border-radius: 12px !important;
        }}


        /* =====================================================
           MAIN HEADER
        ===================================================== */

        .top-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;

            padding: 18px 25px;
            margin-bottom: 22px;

            border: 1px solid rgba(148,163,184,.15);
            border-radius: 18px;

            background:
                linear-gradient(
                    135deg,
                    rgba(17,28,49,.85),
                    rgba(8,15,30,.70)
                );

            backdrop-filter: blur(18px);

            box-shadow:
                0 20px 50px rgba(0,0,0,.25);
        }}

        .header-title {{
            font-size: 27px;
            font-weight: 800;
            color: white;
        }}

        .header-subtitle {{
            color: #94a3b8;
            font-size: 13px;
        }}

        .header-badge {{
            background: rgba(226,27,43,.12);
            border: 1px solid rgba(226,27,43,.35);
            padding: 9px 16px;
            border-radius: 50px;
            color: #ff4b5c;
            font-size: 13px;
        }}


        /* =====================================================
           SECTION CARDS
        ===================================================== */

        .glass-card {{
            background:
                linear-gradient(
                    135deg,
                    rgba(20,32,53,.88),
                    rgba(8,15,28,.80)
                );

            border: 1px solid rgba(100,116,139,.22);
            border-radius: 20px;

            padding: 25px;

            margin-bottom: 22px;

            box-shadow:
                0 20px 60px rgba(0,0,0,.25),
                inset 0 1px 0 rgba(255,255,255,.03);

            backdrop-filter: blur(18px);
        }}

        .section-title {{
            font-size: 21px;
            font-weight: 800;
            color: #f8fafc;
        }}

        .section-subtitle {{
            color: #64748b;
            font-size: 12px;
            margin-top: 2px;
        }}


        /* =====================================================
           STAT CARDS
        ===================================================== */

        .stat-card {{
            background:
                linear-gradient(
                    135deg,
                    rgba(20,32,53,.95),
                    rgba(10,18,32,.9)
                );

            border: 1px solid rgba(71,85,105,.3);
            border-radius: 17px;

            padding: 20px;

            position: relative;
            overflow: hidden;

            box-shadow: 0 15px 40px rgba(0,0,0,.22);
        }}

        .stat-card:before {{
            content: "";
            position: absolute;
            top: 0;
            right: 0;
            width: 4px;
            height: 100%;
            background: #e21b2b;
        }}

        .stat-icon {{
            font-size: 25px;
        }}

        .stat-title {{
            color: #94a3b8;
            font-size: 13px;
            margin-top: 8px;
        }}

        .stat-value {{
            color: white;
            font-size: 27px;
            font-weight: 800;
            margin-top: 4px;
        }}


        /* =====================================================
           INPUTS
        ===================================================== */

        div[data-baseweb="input"],
        div[data-baseweb="textarea"],
        div[data-baseweb="select"] > div {{
            background: #101b2f !important;
            border: 1px solid #293a56 !important;
            border-radius: 11px !important;
        }}

        input,
        textarea {{
            color: #f8fafc !important;
        }}

        input::placeholder,
        textarea::placeholder {{
            color: #64748b !important;
        }}

        label {{
            color: #cbd5e1 !important;
            font-weight: 600 !important;
        }}


        /* =====================================================
           BUTTONS
        ===================================================== */

        .stButton > button,
        .stFormSubmitButton > button {{
            width: 100%;

            border: none !important;
            border-radius: 11px !important;

            padding: 12px 20px !important;

            background:
                linear-gradient(
                    135deg,
                    #ff2436,
                    #c91425
                ) !important;

            color: white !important;

            font-weight: 800 !important;

            box-shadow:
                0 8px 25px rgba(226,27,43,.25);

            transition: all .25s ease;
        }}

        .stButton > button:hover,
        .stFormSubmitButton > button:hover {{
            transform: translateY(-2px);

            box-shadow:
                0 12px 35px rgba(226,27,43,.4);
        }}


        /* =====================================================
           TABLE
        ===================================================== */

        [data-testid="stDataFrame"] {{
            border-radius: 15px;
            overflow: hidden;
            border: 1px solid #26364f;
        }}


        /* =====================================================
           ALERTS
        ===================================================== */

        div[data-testid="stAlert"] {{
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,.08);
        }}


        /* =====================================================
           DIVIDER
        ===================================================== */

        hr {{
            border-color: rgba(148,163,184,.12) !important;
        }}


        /* =====================================================
           FOOTER
        ===================================================== */

        .footer {{
            text-align: center;
            color: #475569;
            font-size: 11px;
            margin-top: 35px;
            padding: 20px;
        }}

        .footer span {{
            color: #e21b2b;
            font-weight: bold;
        }}

        </style>
        """,
        unsafe_allow_html=True,
    )


set_custom_design()


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def calculate_payment(total, deposit):

    if deposit >= total and total > 0:
        return "تم الدفع بالكامل"

    elif deposit > 0:
        remaining = total - deposit
        return f"تم دفع عربون — المتبقي: {remaining:.2f} ج"

    return "لم يدفع"


def get_statistics():

    conn = get_connection()

    df = pd.read_sql_query("""
        SELECT *
        FROM orders
    """, conn)

    conn.close()

    if df.empty:
        return 0, 0, 0, 0

    total_orders = len(df)

    completed = len(
        df[df["order_status"] == "تم التسليم"]
    )

    in_progress = len(
        df[df["order_status"] == "قيد التنفيذ"]
    )

    total_sales = df["total_cost"].fillna(0).sum()

    return total_orders, completed, in_progress, total_sales


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    if logo_base64:

        st.markdown(
            f"""
            <div class="sidebar-logo">
                <img src="data:image/jpeg;base64,{logo_base64}">
                <div class="brand-title">ZERO Advertising</div>
                <div class="brand-subtitle">
                    نظام إدارة المطبعة والإعلانات
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    st.markdown(
        """
        <div style="
            color:#64748b;
            font-size:11px;
            margin-bottom:8px;
        ">
        القائمة الرئيسية
        </div>
        """,
        unsafe_allow_html=True,
    )

    menu = [
        "➕  تسجيل طلب جديد",
        "📋  الطلبات المسجلة",
        "⚙️  تحديث حالة طلب",
    ]

    choice = st.selectbox(
        "اختر القسم",
        menu,
        label_visibility="collapsed",
    )

    st.divider()

    st.markdown(
        """
        <div style="
            background:#101b2f;
            border:1px solid #26364f;
            padding:15px;
            border-radius:14px;
            text-align:center;
        ">
            <div style="font-size:12px;color:#64748b;">
                ZERO PRINTING SYSTEM
            </div>
            <div style="
                color:#e21b2b;
                font-weight:800;
                margin-top:5px;
            ">
                Management v2.0
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# HEADER
# =========================================================

st.markdown(
    """
    <div class="top-header">

        <div>
            <div class="header-title">
                🖨️ ZERO Advertising
            </div>

            <div class="header-subtitle">
                نظام إدارة الطلبات والعملاء والمبيعات
            </div>
        </div>

        <div class="header-badge">
            ● النظام يعمل بشكل طبيعي
        </div>

    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# STATISTICS
# =========================================================

total_orders, completed, in_progress, total_sales = get_statistics()

s1, s2, s3, s4 = st.columns(4)

with s1:
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-icon">📦</div>
            <div class="stat-title">إجمالي الطلبات</div>
            <div class="stat-value">{total_orders}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with s2:
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-icon">🚀</div>
            <div class="stat-title">طلبات قيد التنفيذ</div>
            <div class="stat-value">{in_progress}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with s3:
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-icon">✅</div>
            <div class="stat-title">تم التسليم</div>
            <div class="stat-value">{completed}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with s4:
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-icon">💰</div>
            <div class="stat-title">إجمالي قيمة الطلبات</div>
            <div class="stat-value">
                {total_sales:,.0f} ج
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.markdown("<br>", unsafe_allow_html=True)


# =========================================================
# 1. NEW ORDER
# =========================================================

if choice == "➕  تسجيل طلب جديد":

    st.markdown(
        """
        <div class="glass-card">

            <div class="section-title">
                📝 إضافة عميل وطلب جديد
            </div>

            <div class="section-subtitle">
                قم بإدخال بيانات العميل وتفاصيل الطلب
            </div>

        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("add_order_form", clear_on_submit=True):

        col1, col2, col3 = st.columns([1, 1, 1])

        with col1:

            st.markdown("### 👤 بيانات العميل")

            customer_name = st.text_input(
                "اسم العميل *",
                placeholder="مثال: أحمد محمد"
            )

            customer_phone = st.text_input(
                "رقم التليفون",
                placeholder="01XXXXXXXXX"
            )

        with col2:

            st.markdown("### 📄 تفاصيل الطلب")

            order_details = st.text_area(
                "تفاصيل الطلب *",
                placeholder="اكتب تفاصيل الطباعة أو التصميم هنا...",
                height=150
            )

        with col3:

            st.markdown("### 💰 البيانات المالية")

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
                [
                    "قيد التنفيذ",
                    "جاهز للتسليم",
                    "تم التسليم"
                ]
            )

        st.divider()

        remaining_preview = total_cost - deposit

        if deposit > total_cost and total_cost > 0:

            st.warning(
                "⚠️ المبلغ المدفوع أكبر من إجمالي قيمة الطلب."
            )

        elif total_cost > 0:

            st.info(
                f"💳 المتبقي على العميل: "
                f"{max(remaining_preview, 0):,.2f} جنيه"
            )

        st.markdown("<br>", unsafe_allow_html=True)

        submit_button = st.form_submit_button(
            "💾  حفظ الطلب",
            use_container_width=True
        )

        if submit_button:

            if not customer_name.strip():

                st.error("❌ يرجى إدخال اسم العميل.")

            elif not order_details.strip():

                st.error("❌ يرجى إدخال تفاصيل الطلب.")

            elif deposit > total_cost and total_cost > 0:

                st.error(
                    "❌ العربون لا يمكن أن يكون أكبر من إجمالي الطلب."
                )

            else:

                payment_status = calculate_payment(
                    total_cost,
                    deposit
                )

                conn = get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO customers
                    (name, phone)
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
                    f"✅ تم حفظ طلب العميل "
                    f"'{customer_name}' بنجاح!"
                )

                st.balloons()


# =========================================================
# 2. ORDERS
# =========================================================

elif choice == "📋  الطلبات المسجلة":

    st.markdown(
        """
        <div class="glass-card">

            <div class="section-title">
                📋 قائمة الطلبات المسجلة
            </div>

            <div class="section-subtitle">
                عرض وإدارة جميع الطلبات والعملاء
            </div>

        </div>
        """,
        unsafe_allow_html=True,
    )

    conn = get_connection()

    query = """
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
    """

    df = pd.read_sql_query(query, conn)

    conn.close()

    if not df.empty:

        search_col1, search_col2 = st.columns([2, 1])

        with search_col1:

            search_name = st.text_input(
                "🔍 بحث باسم العميل",
                placeholder="اكتب اسم العميل..."
            )

        with search_col2:

            status_filter = st.selectbox(
                "📌 تصفية حسب الحالة",
                [
                    "الكل",
                    "قيد التنفيذ",
                    "جاهز للتسليم",
                    "تم التسليم"
                ]
            )

        if search_name:

            df = df[
                df["اسم العميل"]
                .str.contains(
                    search_name,
                    case=False,
                    na=False
                )
            ]

        if status_filter != "الكل":

            df = df[
                df["حالة الطلب"] == status_filter
            ]

        st.markdown("<br>", unsafe_allow_html=True)

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=520,
            column_config={
                "الإجمالي": st.column_config.NumberColumn(
                    "الإجمالي",
                    format="%.2f ج"
                ),

                "العربون": st.column_config.NumberColumn(
                    "العربون",
                    format="%.2f ج"
                ),
            }
        )

        st.caption(
            f"عدد النتائج المعروضة: {len(df)}"
        )

    else:

        st.info(
            "📭 لا توجد طلبات مسجلة حالياً."
        )


# =========================================================
# 3. UPDATE ORDER
# =========================================================

elif choice == "⚙️  تحديث حالة طلب":

    st.markdown(
        """
        <div class="glass-card">

            <div class="section-title">
                ⚙️ تحديث بيانات الطلب
            </div>

            <div class="section-subtitle">
                تعديل حالة الطلب والمبلغ المدفوع
            </div>

        </div>
        """,
        unsafe_allow_html=True,
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

    orders_list = cursor.fetchall()

    if orders_list:

        options = {
            f"طلب رقم #{o[0]} — {o[1]}": o[0]
            for o in orders_list
        }

        selected_option = st.selectbox(
            "📌 اختر الطلب للتعديل",
            list(options.keys())
        )

        selected_order_id = options[selected_option]

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
            (selected_order_id,)
        )

        current_order = cursor.fetchone()

        st.markdown("<br>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                """
                <div class="glass-card">
                <div class="section-title">
                    💰 البيانات المالية
                </div>
                """,
                unsafe_allow_html=True
            )

            total_cost = float(
                current_order[0] or 0
            )

            new_deposit = st.number_input(
                "المبلغ المدفوع",
                min_value=0.0,
                value=float(current_order[1] or 0),
                step=10.0
            )

            remaining = total_cost - new_deposit

            if new_deposit > total_cost and total_cost > 0:

                st.error(
                    "❌ المبلغ المدفوع أكبر من قيمة الطلب."
                )

            else:

                new_payment_status = calculate_payment(
                    total_cost,
                    new_deposit
                )

                if remaining > 0:

                    st.info(
                        f"💳 المتبقي: "
                        f"{remaining:,.2f} جنيه"
                    )

                elif total_cost > 0:

                    st.success(
                        "✅ تم دفع قيمة الطلب بالكامل"
                    )

                else:

                    st.info(
                        "لم يتم تحديد قيمة للطلب."
                    )

            st.markdown("</div>", unsafe_allow_html=True)

        with col2:

            st.markdown(
                """
                <div class="glass-card">
                <div class="section-title">
                    📦 حالة الطلب
                </div>
                """,
                unsafe_allow_html=True
            )

            status_options = [
                "قيد التنفيذ",
                "جاهز للتسليم",
                "تم التسليم"
            ]

            current_status = current_order[3]

            if current_status not in status_options:
                current_status = "قيد التنفيذ"

            new_order_status = st.selectbox(
                "الحالة الجديدة",
                status_options,
                index=status_options.index(
                    current_status
                )
            )

            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button(
            "🔄  تحديث البيانات",
            use_container_width=True
        ):

            if new_deposit > total_cost and total_cost > 0:

                st.error(
                    "❌ لا يمكن حفظ مبلغ أكبر من إجمالي الطلب."
                )

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
                        selected_order_id
                    )
                )

                conn.commit()

                st.success(
                    "✅ تم تحديث بيانات الطلب بنجاح!"
                )

                st.rerun()

    else:

        st.info(
            "📭 لا توجد طلبات مسجلة حالياً."
        )

    conn.close()


# =========================================================
# FOOTER
# =========================================================

st.markdown(
    """
    <div class="footer">
        ZERO Advertising Management System
        <br>
        <span>PRINT • DESIGN • ADVERTISING</span>
    </div>
    """,
    unsafe_allow_html=True,
)
