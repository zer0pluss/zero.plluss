# ZERO Advertising — Cloud Edition

نسخة جديدة مبنية من الصفر بدون SQLite وبدون Google Drive Desktop.

## Architecture
- Streamlit: واجهة النظام.
- PostgreSQL: قاعدة البيانات الأساسية Online.
- Google Drive API: أرشيف ونسخ احتياطي.
- كل يوم: ملف PDF واحد + ملف JSON واحد.
- تعديل طلب يحدّث أرشيف نفس اليوم بدل إنشاء ملف جديد.

## أهم نقطة
التطبيق **لا يقرأ `print_shop.db` من جهاز المستخدم** ولا يبحث عن `G:\` أو `My Drive` على الجهاز.

## التشغيل
1. أنشئ PostgreSQL database على مزود Cloud يدعم PostgreSQL.
2. ضع `DATABASE_URL` في Environment Variables.
3. أنشئ Google Cloud Service Account وفَعّل Google Drive API.
4. شارك مجلد Google Drive المراد استخدامه مع بريد الـService Account بصلاحية Editor.
5. ضع محتوى JSON الخاص بالـService Account في `GOOGLE_SERVICE_ACCOUNT_JSON` كـEnvironment Variable.
6. ضع `zero.jpg` بجوار `app.py` على السيرفر إذا أردت ظهور اللوجو.
7. ثبّت المتطلبات: `pip install -r requirements.txt`
8. شغّل: `streamlit run app.py`

## الملفات السحابية
سيتم إنشاء:

ZERO Advertising/
- Daily Orders/YYYY/MM/YYYY-MM-DD.pdf
- Daily Data/YYYY/MM/YYYY-MM-DD.json
- Backups/

## ملاحظة مهمة
Google Drive ليس قاعدة بيانات تشغيلية. قاعدة البيانات PostgreSQL هي المصدر الأساسي، وDrive طبقة أرشفة واسترجاع إضافية.
