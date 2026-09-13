import base64
import os
import streamlit as st


def apply():
    logo_css = ""
    if os.path.exists("zero.jpg"):
        try:
            b64 = base64.b64encode(open("zero.jpg", "rb").read()).decode()
            logo_css = f""".stApp::before{{content:\"\";position:fixed;inset:0;background:url('data:image/jpeg;base64,{b64}') center 35%/min(900px,55vw) no-repeat;opacity:.045;pointer-events:none;z-index:0;}}"""
        except Exception:
            pass
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&display=swap');
:root{{--red:#e21b22;--navy:#0f172a;--panel:#111c2d;--muted:#8794a8;}}
html,body,[class*='css']{{font-family:'Cairo',sans-serif;direction:rtl;}}
.stApp{{background:radial-gradient(circle at 10% 10%,rgba(226,27,34,.08),transparent 28%),linear-gradient(135deg,#070b12,#0b1320 55%,#070b12);color:#f8fafc;}}
{logo_css}
.main .block-container{{max-width:1480px;padding-top:1.2rem;position:relative;z-index:1;}}
#MainMenu,footer{{visibility:hidden;}}
section[data-testid='stSidebar']{{background:#080d16!important;border-left:1px solid rgba(226,27,34,.35);}}
section[data-testid='stSidebar']>div{{padding:.9rem .8rem;}}
.brand{{text-align:center;padding:10px 0 18px;}}
.brand img{{width:94px;height:94px;border-radius:18px;object-fit:cover;box-shadow:0 14px 35px #0008;border:1px solid #ffffff18;}}
.brand h2{{font-size:20px;margin:10px 0 0;font-weight:800;}}
.brand p{{font-size:10px;color:#718096;margin:2px 0 0;letter-spacing:.6px;}}
.hero{{display:flex;justify-content:space-between;align-items:center;gap:20px;background:linear-gradient(135deg,#121d30e8,#0b1423e8);border:1px solid #ffffff12;border-radius:18px;padding:18px 22px;margin-bottom:16px;box-shadow:0 15px 40px #0004;}}
.hero h1{{font-size:24px;margin:0;font-weight:800;}} .hero p{{margin:3px 0 0;color:#7f8da3;font-size:11px;}}
.badge{{padding:7px 12px;border-radius:999px;background:#22c55e12;border:1px solid #22c55e30;color:#86efac;font-size:11px;white-space:nowrap;}}
.stat{{background:linear-gradient(145deg,#142036,#0c1524);border:1px solid #ffffff10;border-radius:16px;padding:17px 18px;min-height:105px;position:relative;overflow:hidden;}}
.stat:after{{content:'';position:absolute;right:0;top:0;width:3px;height:100%;background:#e21b22;}}
.stat .label{{color:#7f8da3;font-size:11px;}} .stat .value{{font-size:24px;font-weight:800;margin-top:5px;}}
.panel{{background:linear-gradient(145deg,#121e31e8,#09111ee8);border:1px solid #ffffff10;border-radius:17px;padding:20px;margin-bottom:16px;box-shadow:0 14px 40px #0003;}}
.panel h2{{font-size:19px;margin:0;font-weight:800;}} .panel .sub{{color:#77869b;font-size:11px;margin:3px 0 15px;}}
div[data-baseweb='input']>div,div[data-baseweb='textarea']>div,div[data-baseweb='select']>div{{background:#0d1728!important;border:1px solid #253550!important;border-radius:10px!important;}}
input,textarea{{color:#f8fafc!important;}} label{{color:#cbd5e1!important;font-size:12px!important;}}
.stButton>button,.stFormSubmitButton>button{{border:0!important;border-radius:10px!important;min-height:43px;background:linear-gradient(135deg,#ed2535,#bd101f)!important;color:white!important;font-weight:800!important;}}
.stButton>button:hover,.stFormSubmitButton>button:hover{{filter:brightness(1.08);box-shadow:0 10px 25px #e21b2233;}}
[data-testid='stDataFrame']{{border:1px solid #ffffff12;border-radius:12px;overflow:hidden;}}
.footer{{text-align:center;color:#465267;font-size:10px;padding:20px;}}
</style>""", unsafe_allow_html=True)
