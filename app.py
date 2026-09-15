import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# ضبط إعدادات الصفحة
st.set_page_config(
    page_title="ZERO Advertising - لوحة التحكّم",
    page_icon="🖨️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# تصميم الواجهة واللوجو خلفية
def inject_custom_css():
  st.markdown(
      """
    <style>
    html, body, [class*="css"], .stApp {
        direction: rtl;
        text-align: right;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background-color: #0f172a;
    }

    .stApp::before {
        content: "";
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background-image: url("https://raw.githubusercontent.com/zer0pluss/zero.pluss/main/logo.jpg");
        background-size: 350px auto;
        background-repeat: no-repeat;
        background-position: center;
        opacity: 0.08;
        z-index: 0;
        pointer-events: none;
    }

    header, footer, #MainMenu { visibility: hidden; }

    section[data-testid="stSidebar"] {
        background-color: #1e293b !important;
        border-left: 2px solid #e21b22;
    }
    section[data-testid="stSidebar"] * {
        color: #f8fafc !important;
        text-align: right;
    }

    h1, h2, h3, label {
        color: #ffffff !important;
        font-weight: 700 !important;
    }

    .stTextInput input, .stTextArea textarea, div[data-baseweb="select"] > div, .stNumberInput input {
        background-color: #334155 !important;
        color: #ffffff !important;
        border-radius: 8px !important;
        border: 1px solid #475569 !important;
        text-align: right !important;
    }

    .stButton>button {
        width: 100%;
        background-color: #e21b22 !important;
        color: #ffffff !important;
        font-weight: bold !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 12px 20px !important;
    }
    .stButton>button:hover { background-color: #b91c1c !important; }
    </style>
    """,
      unsafe_allow_html=True,
  )


inject_custom_css()

# الاتصال بجداول جوجل (Google Sheets)
conn = st.connection("gsheets", type=GSheetsConnection)

st.title("🎯 ZERO Advertising - لوحة التحكّم (Google Drive)")
st.markdown("---")

menu = ["تسجيل طلب جديد", "استعلام وعرض الطلبات"]
navigation = st.sidebar.selectbox("📌 القائمة الرئيسية", menu)

if navigation == "تسجيل طلب جديد":
  st.subheader("📝 تسجيل طلب جديد في جوجل درايف")

  with st.form("new_order_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
      c_name = st.text_input("اسم العميل *")
      c_phone = st.text_input("رقم التليفون")
      o_details = st.text_area("تفاصيل الطلب *")
    with col2:
      t_cost = st.number_input(
          "إجمالي التكلفة (جنيه)", min_value=0.0, step=50.0
      )
      dep = st.number_input(
          "المدفوع / العربون (جنيه)", min_value=0.0, step=50.0
      )
      o_status = st.selectbox(
          "حالة الطلب", ["قيد التنفيذ", "جاهز للتسليم", "تم التسليم"]
      )

    submit = st.form_submit_button("حفظ الطلب على جوجل درايف")

    if submit:
      if not c_name or not o_details:
        st.error("يرجى كتابة اسم العميل والتفاصيل!")
      else:
        rem = t_cost - dep
        p_status = (
            "تم الدفع بالكامل"
            if rem <= 0 and t_cost > 0
            else (
                f"تم دفع عربون (المتبقي: {rem:.2f})" if dep > 0 else "لم يدفع"
            )
        )

        # قراءة البيانات الحالية وإضافة السطر الجديد
        existing_data = conn.read(ttl=0)
        new_row = pd.DataFrame([{
            "اسم العميل": c_name,
            "التليفون": c_phone,
            "التفاصيل": o_details,
            "الإجمالي": t_cost,
            "العربون": dep,
            "حالة الدفع": p_status,
            "حالة الطلب": o_status,
            "التاريخ": pd.Timestamp.now().strftime("%Y-%m-%d"),
        }])

        updated_df = pd.concat([existing_data, new_row], ignore_index=True)
        conn.update(data=updated_df)

        st.success(f"تم حفظ طلب العميل '{c_name}' بنجاح على Google Drive!")

elif navigation == "استعلام وعرض الطلبات":
  st.subheader("📋 قائمة الطلبات المسجلة من Google Sheets")

  df = conn.read(ttl=0)
  if not df.empty:
    s_query = st.text_input("🔍 بحث باسم العميل:")
    if s_query:
      df = df[df["اسم العميل"].str.contains(s_query, case=False, na=False)]
    st.dataframe(df, use_container_width=True)
  else:
    st.info("لا توجد طلبات مسجلة حتى الآن.")
