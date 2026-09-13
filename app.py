import os
from datetime import date, datetime

import pandas as pd
import streamlit as st

import db
import drive
from archive import make_json, make_pdf
from styles import apply

st.set_page_config(page_title="ZERO Advertising | Management System", page_icon="🖨️", layout="wide", initial_sidebar_state="expanded")
apply()

def sync_day(day):
    orders = db.list_orders(order_date=day.isoformat())
    note = db.get_note(day)
    pdf = make_pdf(orders, note, day)
    js = make_json(orders, note, day)
    drive.upload_daily(pdf, js, day.year, day.month, f"{day.isoformat()}.pdf", f"{day.isoformat()}.json")
    return len(orders)

def safe_sync(day):
    try:
        sync_day(day)
        return True, None
    except Exception as exc:
        return False, str(exc)

try:
    db.init_db()
    db_ok = True
    db_error = None
except Exception as exc:
    db_ok = False
    db_error = str(exc)

if not db_ok:
    st.error("قاعدة البيانات غير متصلة")
    st.code(db_error)
    st.info("راجع DATABASE_URL في إعدادات السيرفر.")
    st.stop()

stats = db.statistics()

today = date.today()
with st.sidebar:
    if os.path.exists("zero.jpg"):
        import base64
        b64 = base64.b64encode(open("zero.jpg","rb").read()).decode()
        st.markdown(f"<div class='brand'><img src='data:image/jpeg;base64,{b64}'><h2>ZERO PLUS</h2><p>PRINT • DESIGN • ADVERTISING</p></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='brand'><h2>ZERO PLUS</h2><p>PRINT • DESIGN • ADVERTISING</p></div>", unsafe_allow_html=True)
    st.divider()
    choice = st.radio("القائمة", ["الرئيسية", "➕ تسجيل طلب", "📋 الطلبات", "⚙️ تحديث طلب", "📝 المفكرة اليومية", "☁️ النسخ السحابية"], label_visibility="collapsed")
    st.divider()
    note_preview = db.get_note(today)
    if note_preview:
        st.caption(f"ملاحظة اليوم • {today.isoformat()}")
        st.write(note_preview[:180] + ("…" if len(note_preview)>180 else ""))
    ok, _ = drive.status()
    st.caption("● Cloud Connected" if ok else "● Cloud Backup يحتاج إعداد")

st.markdown(f"<div class='hero'><div><h1>ZERO Advertising</h1><p>نظام إدارة الطلبات والعملاء • {today.strftime('%Y-%m-%d')}</p></div><div class='badge'>● النظام متصل</div></div>", unsafe_allow_html=True)

c1,c2,c3,c4,c5=st.columns(5)
for col,label,value in zip([c1,c2,c3,c4,c5], ["إجمالي الطلبات","قيد التنفيذ","تم التسليم","إجمالي المبيعات","المتبقي"], [stats[0],stats[2],stats[1],f"{float(stats[3]):,.0f} ج",f"{float(stats[5]):,.0f} ج"]):
    with col:
        st.markdown(f"<div class='stat'><div class='label'>{label}</div><div class='value'>{value}</div></div>", unsafe_allow_html=True)
st.write("")

if choice == "الرئيسية":
    today_orders = db.list_orders(order_date=today.isoformat())
    st.markdown("<div class='panel'><h2>ملخص اليوم</h2><div class='sub'>الطلبات المسجلة اليوم تظهر هنا بشكل سريع.</div></div>", unsafe_allow_html=True)
    if today_orders:
        df=pd.DataFrame(today_orders)
        df=df[["order_id","name","phone","order_details","total_cost","deposit","payment_status","order_status"]]
        df.columns=["رقم الطلب","العميل","التليفون","التفاصيل","الإجمالي","العربون","حالة الدفع","حالة الطلب"]
        st.dataframe(df,use_container_width=True,hide_index=True,height=430)
    else: st.info("لا توجد طلبات مسجلة اليوم.")

elif choice == "➕ تسجيل طلب":
    st.markdown("<div class='panel'><h2>تسجيل طلب جديد</h2><div class='sub'>أدخل بيانات العميل والطلب. بعد الحفظ يتم تحديث أرشيف اليوم تلقائياً.</div></div>", unsafe_allow_html=True)
    with st.form("new_order", clear_on_submit=True):
        a,b,c=st.columns([1,1.5,1])
        with a:
            name=st.text_input("اسم العميل *",placeholder="مثال: أحمد محمد")
            phone=st.text_input("رقم التليفون",placeholder="01XXXXXXXXX")
            order_date=st.date_input("تاريخ الطلب",value=today)
        with b:
            details=st.text_area("تفاصيل الطلب *",height=170,placeholder="500 فلاير — A5 — وجهين — ألوان...")
        with c:
            total=st.number_input("إجمالي الطلب (جنيه)",min_value=0.0,value=0.0,step=10.0,format="%.2f")
            deposit=st.number_input("المدفوع / العربون",min_value=0.0,value=0.0,step=10.0,format="%.2f")
            status=st.selectbox("حالة الطلب",["قيد التنفيذ","جاهز للتسليم","تم التسليم"])
            if total>0: st.info(f"المتبقي: {max(total-deposit,0):,.2f} ج")
        submitted=st.form_submit_button("💾 حفظ الطلب",use_container_width=True)
    if submitted:
        if not name.strip(): st.error("اكتب اسم العميل.")
        elif not details.strip(): st.error("اكتب تفاصيل الطلب.")
        elif deposit>total and total>0: st.error("العربون لا يمكن أن يكون أكبر من الإجمالي.")
        else:
            try:
                oid=db.create_order(name.strip(),phone.strip(),details.strip(),total,deposit,status,order_date)
                ok,err=safe_sync(order_date)
                st.success(f"تم حفظ الطلب #{oid}.")
                if not ok: st.warning(f"الداتا محفوظة في قاعدة البيانات، لكن أرشيف Google Drive لم يتحدث: {err}")
                st.rerun()
            except Exception as exc: st.error(str(exc))

elif choice == "📋 الطلبات":
    st.markdown("<div class='panel'><h2>الطلبات</h2><div class='sub'>بحث سريع وتصفية بدون تحميل ملفات من جهازك.</div></div>", unsafe_allow_html=True)
    a,b,c=st.columns([2,1,1])
    with a: search=st.text_input("بحث",placeholder="اسم العميل أو الهاتف أو تفاصيل الطلب")
    with b: status_filter=st.selectbox("الحالة",["الكل","قيد التنفيذ","جاهز للتسليم","تم التسليم"])
    with c: date_filter=st.date_input("التاريخ",value=None)
    rows=db.list_orders(search,status_filter,date_filter.isoformat() if date_filter else None)
    if rows:
        df=pd.DataFrame(rows)
        df=df[["order_id","name","phone","order_details","order_date","total_cost","deposit","payment_status","order_status"]]
        df.columns=["رقم الطلب","اسم العميل","التليفون","التفاصيل","التاريخ","الإجمالي","العربون","حالة الدفع","حالة الطلب"]
        st.dataframe(df,use_container_width=True,hide_index=True,height=550)
        st.caption(f"عدد النتائج: {len(df)}")
    else: st.info("لا توجد نتائج.")

elif choice == "⚙️ تحديث طلب":
    st.markdown("<div class='panel'><h2>تحديث طلب</h2><div class='sub'>غيّر العربون أو حالة التنفيذ وسيتم تحديث حالة الدفع والأرشيف.</div></div>", unsafe_allow_html=True)
    rows=db.list_orders()
    if not rows: st.info("لا توجد طلبات.")
    else:
        opts={f"#{r['order_id']} — {r['name']} — {r['order_date']}":r['order_id'] for r in rows}
        label=st.selectbox("اختر الطلب",list(opts))
        current=db.get_order(opts[label])
        a,b=st.columns(2)
        with a:
            st.metric("الإجمالي",f"{float(current['total_cost']):,.2f} ج")
            dep=st.number_input("المدفوع",min_value=0.0,value=float(current['deposit']),step=10.0,format="%.2f")
        with b:
            statuses=["قيد التنفيذ","جاهز للتسليم","تم التسليم"]
            stat=st.selectbox("حالة الطلب",statuses,index=statuses.index(current['order_status']) if current['order_status'] in statuses else 0)
            st.info(f"المتبقي: {max(float(current['total_cost'])-dep,0):,.2f} ج")
        if st.button("🔄 حفظ التعديل",use_container_width=True):
            if dep>float(current['total_cost']) and float(current['total_cost'])>0: st.error("المبلغ المدفوع أكبر من قيمة الطلب.")
            else:
                try:
                    db.update_order(current['order_id'],dep,stat)
                    ok,err=safe_sync(current['order_date'])
                    st.success("تم تحديث الطلب.")
                    if not ok: st.warning(f"التعديل محفوظ، لكن الـCloud Backup لم يتحدث: {err}")
                    st.rerun()
                except Exception as exc: st.error(str(exc))

elif choice == "📝 المفكرة اليومية":
    st.markdown("<div class='panel'><h2>المفكرة اليومية</h2><div class='sub'>ملاحظة مستقلة لكل تاريخ.</div></div>", unsafe_allow_html=True)
    note_date=st.date_input("اليوم",value=today)
    note=db.get_note(note_date)
    text=st.text_area("الملاحظة",value=note,height=260,placeholder="مواعيد تسليم، خامات، اتصالات، تعليمات...")
    if st.button("💾 حفظ الملاحظة",use_container_width=True):
        try:
            db.save_note(note_date,text.strip())
            ok,err=safe_sync(note_date)
            st.success("تم حفظ الملاحظة.")
            if not ok: st.warning(f"الملاحظة محفوظة، لكن أرشيف اليوم لم يتحدث: {err}")
            st.rerun()
        except Exception as exc: st.error(str(exc))
    st.markdown("<div class='panel'><h2>آخر الملاحظات</h2></div>",unsafe_allow_html=True)
    for n in db.recent_notes(10):
        with st.expander(str(n['note_date'])): st.write(n['note_text'])

elif choice == "☁️ النسخ السحابية":
    st.markdown("<div class='panel'><h2>النسخ السحابية</h2><div class='sub'>Google Drive هنا للأرشفة والاسترجاع، وليس لتشغيل قاعدة البيانات.</div></div>", unsafe_allow_html=True)
    ok,msg=drive.status()
    if ok: st.success("Google Drive متصل.")
    else:
        st.error("Google Drive غير متصل")
        st.code(msg)
        st.info("ضع بيانات Service Account في GOOGLE_SERVICE_ACCOUNT_JSON وشارك مجلد Drive مع بريد الـService Account.")
    st.divider()
    day=st.date_input("إعادة إنشاء أرشيف يوم",value=today)
    if st.button("☁️ مزامنة أرشيف اليوم",use_container_width=True):
        ok,err=safe_sync(day)
        if ok: st.success(f"تم تحديث {day.isoformat()}.pdf و {day.isoformat()}.json")
        else: st.error(err)
    if st.button("☁️ مزامنة آخر 7 أيام",use_container_width=True):
        errors=[]
        for i in range(7):
            from datetime import timedelta
            d=today-timedelta(days=i)
            ok,err=safe_sync(d)
            if not ok: errors.append(f"{d}: {err}")
        if errors: st.warning("تمت المحاولة مع وجود أخطاء:\n"+"\n".join(errors))
        else: st.success("تم تحديث أرشيف آخر 7 أيام.")

st.markdown("<div class='footer'>ZERO Advertising Management System<br><strong>PRINT • DESIGN • ADVERTISING</strong></div>",unsafe_allow_html=True)
