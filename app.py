import pandas as pd
from psycopg2 import pool
import streamlit as st

# ضبط إعدادات الصفحة
st.set_page_config(
    page_title="ZERO Advertising ",
    page_icon="🖨️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# تصميم الواجهة واللوجو خلفية
def set_custom_design():
  st.markdown(
      """
    <style>
    html, body, [class*="css"]  {
        direction: rtl;
        text-align: right;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    /* اللوجو في الخلفية بـ Opacity خفيفة */
    .stApp {
        background: linear-gradient(rgba(15, 23, 42, 0.88), rgba(15, 23, 42, 0.88)), 
                    url("https://raw.githubusercontent.com/zer0pluss/zero.pluss/main/logo.jpg");
        background-size: contain;
        background-repeat: no-repeat;
        background-position: center;
        background-attachment: fixed;
    }

    section[data-testid="stSidebar"] {
        background-color: #1e293b !important;
        border-left: 2px solid #e21b22;
    }
    
    section[data-testid="stSidebar"] * {
        color: #ffffff !important;
        text-align: right;
    }

    h1, h2, h3 {
        color: #f8fafc !important;
        font-weight: 700;
    }

    .stTextInput input, .stTextArea textarea, .stSelectbox select, .stNumberInput input {
        background-color: #334155 !important;
        color: #ffffff !important;
        border-radius: 8px !important;
        border: 1px solid #475569 !important;
        text-align: right;
    }

    .stButton>button {
        width: 100%;
        background-color: #e21b22 !important;
        color: white !important;
        font-weight: bold !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 10px 20px !important;
        transition: 0.3s;
    }

    .stButton>button:hover {
        background-color: #b91c1c !important;
        box-shadow: 0 4px 12px rgba(226, 27, 34, 0.4);
    }
    </style>
    """,
      unsafe_allow_html=True,
  )


set_custom_design()


# الاتصال بقاعدة بيانات Supabase الدائمة
@st.cache_resource
def init_connection():
  return pool.SimpleConnectionPool(1, 10, st.secrets["postgres"]["url"])


def run_query(query, params=None, fetch=False):
  conn_pool = init_connection()
  conn = conn_pool.getconn()
  cursor = conn.cursor()
  cursor.execute(query, params)
  result = None
  if fetch:
    result = cursor.fetchall()
  conn.commit()
  cursor.close()
  conn_pool.putconn(conn)
  return result


# إنشاء الجداول إن لم تكن موجودة
def init_db():
  run_query("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT
        );
    """)
  run_query("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id SERIAL PRIMARY KEY,
            customer_id INTEGER REFERENCES customers(customer_id),
            order_details TEXT NOT NULL,
            order_date DATE DEFAULT CURRENT_DATE,
            total_cost REAL,
            deposit REAL,
            payment_status TEXT,
            order_status TEXT
        );
    """)


try:
  init_db()
except Exception as e:
  st.warning("برجاء إضافه رابط قاعدة بيانات Supabase في الـ Secrets للبدء.")

st.title("🎯 ZERO Advertising - إدارة الطلبات")

menu = ["تسجيل طلب جديد", "عرض واستعلام الطلبات", "تحديث حالة طلب"]
choice = st.sidebar.selectbox("📌 القائمة الرئيسية", menu)

if choice == "تسجيل طلب جديد":
  st.subheader("📝 إضافة عميل وطلب جديد")

  with st.form("add_order_form", clear_on_submit=True):
    col1, col2 = st.columns(2)

    with col1:
      customer_name = st.text_input("اسم العميل *")
      customer_phone = st.text_input("رقم التليفون")
      order_details = st.text_area("تفاصيل الطلب *")

    with col2:
      total_cost = st.number_input(
          "التكلفة الإجمالية (جنيه)", min_value=0.0, step=10.0
      )
      deposit = st.number_input(
          "المبلغ المدفوع / العربون (جنيه)", min_value=0.0, step=10.0
      )
      order_status = st.selectbox(
          "حالة الطلب", ["قيد التنفيذ", "جاهز للتسليم", "تم التسليم"]
      )

    submit_button = st.form_submit_button("حفظ الطلب")

    if submit_button:
      if not customer_name or not order_details:
        st.error("يرجى إدخال اسم العميل وتفاصيل الطلب!")
      else:
        remaining = total_cost - deposit
        if remaining <= 0 and total_cost > 0:
          payment_status = "تم الدفع بالكامل"
        elif deposit > 0:
          payment_status = f"تم دفع عربون (المتبقي: {remaining:.2f})"
        else:
          payment_status = "لم يدفع"

        # إضافة العميل والطلب
        res = run_query(
            "INSERT INTO customers (name, phone) VALUES (%s, %s) RETURNING"
            " customer_id;",
            (customer_name, customer_phone),
            fetch=True,
        )
        customer_id = res[0][0]

        run_query(
            """
            INSERT INTO orders (customer_id, order_details, total_cost, deposit, payment_status, order_status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """,
            (
                customer_id,
                order_details,
                total_cost,
                deposit,
                payment_status,
                order_status,
            ),
        )

        st.success(f"تم حفظ طلب العميل '{customer_name}' بنجاح!")

elif choice == "عرض واستعلام الطلبات":
  st.subheader("📋 قائمة الطلبات المسجلة")

  data = run_query(
      """
        SELECT 
            o.order_id AS "رقم الطلب",
            c.name AS "اسم العميل",
            c.phone AS "التليفون",
            o.order_details AS "التفاصيل",
            o.total_cost AS "الإجمالي",
            o.deposit AS "العربون",
            o.payment_status AS "حالة الدفع",
            o.order_status AS "حالة الطلب",
            o.order_date AS "تاريخ الطلب"
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        ORDER BY o.order_id DESC
    """,
      fetch=True,
  )

  if data:
    df = pd.DataFrame(
        data,
        columns=[
            "رقم الطلب",
            "اسم العميل",
            "التليفون",
            "التفاصيل",
            "الإجمالي",
            "العربون",
            "حالة الدفع",
            "حالة الطلب",
            "تاريخ الطلب",
        ],
    )
    search_name = st.text_input("🔍 بحث باسم العميل:")
    if search_name:
      df = df[df["اسم العميل"].str.contains(search_name, case=False, na=False)]
    st.dataframe(df, use_container_width=True)
  else:
    st.info("لا توجد طلبات مسجلة.")

elif choice == "تحديث حالة طلب":
  st.subheader("⚙️ تعديل وتحديث الطلبات")

  orders_list = run_query(
      "SELECT o.order_id, c.name FROM orders o JOIN customers c ON"
      " o.customer_id = c.customer_id",
      fetch=True,
  )

  if orders_list:
    options = {f"طلب رقم {o[0]} - العميل: {o[1]}": o[0] for o in orders_list}
    selected_option = st.selectbox("اختر الطلب للتعديل", list(options.keys()))
    selected_order_id = options[selected_option]

    current_order = run_query(
        "SELECT total_cost, deposit, payment_status, order_status FROM orders"
        " WHERE order_id = %s",
        (selected_order_id,),
        fetch=True,
    )[0]

    col1, col2 = st.columns(2)
    with col1:
      new_deposit = st.number_input(
          "المبلغ المدفوع الحالي/الجديد",
          value=float(current_order[1]),
          step=10.0,
      )
      total_cost = current_order[0]
      remaining = total_cost - new_deposit

      if remaining <= 0 and total_cost > 0:
        new_payment_status = "تم الدفع بالكامل"
      elif new_deposit > 0:
        new_payment_status = f"تم دفع عربون (المتبقي: {remaining:.2f})"
      else:
        new_payment_status = "لم يدفع"

      st.info(f"حالة الدفع الجديدة: {new_payment_status}")

    with col2:
      new_order_status = st.selectbox(
          "حالة الطلب الجديدة",
          ["قيد التنفيذ", "جاهز للتسليم", "تم التسليم"],
          index=["قيد التنفيذ", "جاهز للتسليم", "تم التسليم"].index(
              current_order[3]
          ),
      )

    if st.button("تحديث البيانات"):
      run_query(
          """
            UPDATE orders 
            SET deposit = %s, payment_status = %s, order_status = %s
            WHERE order_id = %s
        """,
          (
              new_deposit,
              new_payment_status,
              new_order_status,
              selected_order_id,
          ),
      )
      st.success("تم تحديث حالة الطلب بنجاح!")
  else:
    st.info("لا توجد طلبات مسجلة حالياً.")
