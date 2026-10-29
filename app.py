"""Streamlit presentation UI; conversation state stays private to each browser session."""
import json
import os
from html import escape
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
import streamlit as st

from dialogue import ConversationManager, TaxonomyGuardrail, MockLLMClient, LLMClient, LLMSettings
from dialogue.prompts import WARNING_TEXT, LEVEL_LABELS
from dialogue.resume import ResumeError, extract_resume_text
from dialogue.ui_helpers import graphviz_dot


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)

st.set_page_config(
    page_title="مسیر | دستیار مسیر شغلی",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
<style>
:root { --ink:#202235; --muted:#686A7C; --line:#E7E7EF; --surface:#FFFFFF; --canvas:#F7F8FC; --primary:#6D5BD0; --primary-soft:#EFEDFB; }
[data-testid="stAppViewContainer"], [data-testid="stSidebar"] { direction:rtl; }
[data-testid="stAppViewContainer"] { background:var(--canvas); }
[data-testid="stHeader"] { background:transparent; }
[data-testid="stSidebar"] { background:#FFF; border-left:1px solid var(--line); }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap:.65rem; }
.block-container { padding-top:1.35rem; padding-bottom:5rem; max-width:1320px; }
h1,h2,h3,p,label,[data-testid="stChatMessage"] { text-align:right; }
h1,h2,h3 { color:var(--ink); letter-spacing:-.025em; }
[data-testid="stCaptionContainer"] { color:var(--muted); }
[data-testid="stCode"],[data-testid="stJson"] { direction:ltr; text-align:left; }
[data-testid="stMetric"] { background:var(--surface); border:1px solid var(--line); border-radius:16px; padding:.85rem 1rem; box-shadow:0 8px 24px rgba(33,35,54,.035); }
[data-testid="stMetricLabel"] { color:var(--muted); }
[data-testid="stMetricValue"] { direction:ltr; text-align:right; color:var(--ink); }
[data-testid="stChatMessage"] { background:#FFF; border:1px solid var(--line); border-radius:18px; padding:.45rem .7rem; margin-bottom:.65rem; box-shadow:0 5px 18px rgba(33,35,54,.025); }
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) { background:#F1EFFB; border-color:#DED9F5; }
[data-testid="stChatInput"] { border-color:#D9D6EB; border-radius:16px; background:#FFF; }
[data-testid="stFileUploaderDropzone"] { background:#FAFAFD; border:1px dashed #C8C3E7; border-radius:16px; }
.stButton>button,.stDownloadButton>button { min-height:2.7rem; border-radius:12px; font-weight:650; }
.stButton>button[kind="primary"] { box-shadow:0 7px 18px rgba(109,91,208,.22); }
[data-baseweb="tab-list"] { gap:.35rem; background:#FFF; border:1px solid var(--line); border-radius:14px; padding:.3rem; }
[data-baseweb="tab"] { border-radius:10px; padding:.5rem .95rem; }
[aria-selected="true"][data-baseweb="tab"] { background:var(--primary-soft); }
[data-testid="stAlert"] { border-radius:14px; }
div[data-testid="stForm"] { background:#FFF; border:1px solid var(--line); border-radius:18px; padding:1.1rem; }
.brand { display:flex; align-items:center; gap:.75rem; margin:.15rem 0 .6rem; }
.brand-mark { width:42px; height:42px; border-radius:13px; display:grid; place-items:center; color:#FFF; font-size:1.35rem; background:linear-gradient(145deg,#7A67DD,#5442B8); box-shadow:0 8px 20px rgba(109,91,208,.22); }
.brand-title { color:var(--ink); font-weight:800; font-size:1.15rem; }
.brand-subtitle { color:var(--muted); font-size:.75rem; }
.hero { padding:.55rem .15rem .75rem; }
.eyebrow { color:var(--primary); font-weight:750; font-size:.82rem; margin-bottom:.5rem; }
.hero h1 { font-size:clamp(1.8rem,3.4vw,2.75rem); line-height:1.25; margin:0 0 .55rem; }
.hero p { color:var(--muted); max-width:760px; font-size:1.02rem; line-height:1.9; margin:0; }
.scope-note { color:#4E5062; background:#F3F2FA; border:1px solid #E2DFF4; border-radius:13px; padding:.72rem .9rem; font-size:.84rem; line-height:1.7; margin:.35rem 0 .8rem; }
.panel-title { color:var(--ink); font-weight:800; font-size:1.04rem; margin:.15rem 0 .15rem; }
.panel-copy { color:var(--muted); font-size:.82rem; line-height:1.7; margin-bottom:.8rem; }
.profile-card { background:#FFF; border:1px solid var(--line); border-radius:18px; padding:1rem 1.05rem; margin-top:.8rem; box-shadow:0 8px 24px rgba(33,35,54,.03); }
.profile-card .label { color:var(--muted); font-size:.75rem; margin-top:.65rem; }
.profile-card .value { color:var(--ink); font-weight:650; font-size:.9rem; margin-top:.14rem; }
.status-pill { display:inline-flex; align-items:center; gap:.35rem; border-radius:999px; padding:.28rem .65rem; color:#27615E; background:#E8F6F4; border:1px solid #CDE9E5; font-size:.74rem; font-weight:700; }
.soft-divider { height:1px; background:var(--line); margin:.75rem 0; }
@media(max-width:800px){ .block-container{padding-top:.8rem}.hero h1{font-size:1.85rem}[data-baseweb="tab"]{padding:.45rem .55rem} }
</style>
""",
    unsafe_allow_html=True,
)


def _unit_price(name):
    value = os.getenv(name, "").strip()
    return float(value) if value else None


def _role_label(manager, role_id):
    label = manager.guardrail.roles[role_id].label if role_id in manager.guardrail.roles else "هنوز مشخص نشده"
    return escape(label)


def _profile_progress(session):
    profile = session.slots
    completed = sum((
        bool(profile.target_role),
        bool(profile.target_level),
        bool(profile.education and profile.education.strip()),
        profile.experience_years is not None and bool(profile.current_level),
        profile.skills_assessed,
    ))
    return completed, 5


with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="brand-mark">✦</div><div><div class="brand-title">مسیر</div>'
        '<div class="brand-subtitle">دستیار ارزیابی مسیر شغلی</div></div></div>',
        unsafe_allow_html=True,
    )
    st.caption("همراه شما برای ساختن یک مسیر شغلی روشن‌تر")
    if "manager" in st.session_state:
        sidebar_session = st.session_state.manager.get_or_create_session(st.session_state.session_id)
        sidebar_completed, sidebar_total = _profile_progress(sidebar_session)
        st.markdown("**پیشرفت شما**")
        st.progress(sidebar_completed / sidebar_total, text=f"{sidebar_completed} از {sidebar_total} بخش کامل شده")

    reset = st.button("شروع یک گفت‌وگوی جدید", width="stretch", key="reset")
    st.markdown('<div class="soft-divider"></div>', unsafe_allow_html=True)
    st.markdown("**حریم خصوصی شما**")
    st.caption("گفت‌وگو و رزومه فقط در حافظهٔ همین نشست می‌ماند و خودکار ذخیره نمی‌شود.")

    mode, use_demo = "دموی آفلاین", True
    uploaded = None
    taxonomy_path = ""
    api_key = base_url = model = ""
    fmt, protocol, budget = "json_object", "openai", 30000
    start = False
    with st.expander("تنظیمات پیشرفته", expanded=False):
        st.caption("این بخش برای مدیر سامانه و تیم توسعه است.")
        mode = st.selectbox("موتور پردازش", ["دموی آفلاین", "API واقعی"], key="mode")
        use_demo = st.checkbox("استفاده از دادهٔ نمونه", value=True, key="demo_taxonomy")
        if not use_demo:
            uploaded = st.file_uploader("فایل دادهٔ مسیرهای شغلی", type=["json"], key="taxonomy_upload")
            taxonomy_path = st.text_input("یا مسیر فایل داده", value=os.getenv("TAXONOMY_PATH", ""), key="taxonomy_path")
        if mode == "API واقعی":
            st.caption("متن گفت‌وگو و رزومه برای استخراج به سرویس انتخابی ارسال می‌شود.")
            protocol = st.selectbox(
                "پروتکل اتصال", ["openai", "gemini"],
                index=1 if os.getenv("LLM_PROTOCOL", "openai") == "gemini" else 0,
                format_func=lambda x: "Gemini native (متیس)" if x == "gemini" else "OpenAI compatible", key="protocol",
            )
            api_key = st.text_input("API key (فقط همین نشست)", type="password", value="", help="اگر خالی باشد از OPENAI_API_KEY در فایل .env خوانده می‌شود.", key="api_key") or os.getenv("OPENAI_API_KEY", "")
            base_url = st.text_input("Base URL", value=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"), key="base_url")
            model = st.text_input("نام دقیق مدل", value=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), key="model")
            formats = ["json_object", "json_schema", "prompt_json"]
            default_fmt = os.getenv("LLM_RESPONSE_FORMAT", "json_object")
            fmt = st.selectbox("قالب خروجی", formats, index=formats.index(default_fmt) if default_fmt in formats else 0, key="format")
            budget = st.number_input("سقف توکن نشست", min_value=1000, value=int(os.getenv("MAX_SESSION_TOKENS", "30000")), step=1000, key="budget")
        start = st.button("ذخیره و شروع", type="primary", width="stretch", key="start")
        if mode == "دموی آفلاین":
            st.caption("برای ارائهٔ سریع می‌توانی یک نمونهٔ تکمیل‌شده بسازی.")
            run_demo = st.button("نمایش نمونهٔ تکمیل‌شده", key="run_demo", width="stretch")
        else:
            run_demo = False

if reset:
    for key in ("manager", "session_id", "latest", "active_mode", "active_demo", "resume_notice", "edit_synced"):
        st.session_state.pop(key, None)
    st.rerun()

if start or ("manager" not in st.session_state and use_demo and mode == "دموی آفلاین"):
    try:
        if use_demo:
            guardrail = TaxonomyGuardrail(ROOT / "data/demo_taxonomy.json")
        elif uploaded is not None:
            if uploaded.size > 2_000_000:
                raise ValueError("File too large")
            guardrail = TaxonomyGuardrail(data=json.loads(uploaded.getvalue().decode("utf-8-sig")))
        elif taxonomy_path:
            guardrail = TaxonomyGuardrail(Path(taxonomy_path).expanduser())
        else:
            raise ValueError("Taxonomy required")
        if not use_demo and guardrail.taxonomy.is_demo:
            raise ValueError("Team taxonomy is still marked as demo")
        client = MockLLMClient() if mode == "دموی آفلاین" else LLMClient(LLMSettings(
            api_key=api_key, base_url=base_url, model=model, response_format=fmt, protocol=protocol,
            max_session_tokens=int(budget), input_usd_per_million=_unit_price("INPUT_USD_PER_MILLION"),
            output_usd_per_million=_unit_price("OUTPUT_USD_PER_MILLION"),
        ))
        manager = ConversationManager(client, guardrail)
        session_id = str(uuid4())
        st.session_state.update(
            manager=manager, session_id=session_id, latest=manager.start_session(session_id),
            active_mode=mode, active_demo=guardrail.taxonomy.is_demo,
        )
    except Exception:
        st.error("تنظیمات معتبر نیست. کلید، آدرس، مدل و ساختار تاکسونومی را بررسی کن؛ نشست قبلی حفظ شد.")

st.markdown(
    '<section class="hero"><div class="eyebrow">دستیار هوشمند توسعهٔ شغلی</div>'
    '<h1>مسیر بعدی شغلی‌ات را شفاف‌تر ببین</h1>'
    '<p>در یک گفت‌وگوی کوتاه، تجربه‌ها و هدف تو را به یک پروفایل قابل‌ویرایش و نقشهٔ راه مهارتی تبدیل می‌کنیم.</p></section>',
    unsafe_allow_html=True,
)
if "manager" not in st.session_state:
    st.info("برای شروع، تنظیمات پیشرفته را از نوار کناری باز کن و «ذخیره و شروع» را بزن.")
    st.stop()

manager = st.session_state.manager
sid = st.session_state.session_id
session = manager.get_or_create_session(sid)
if not session.history:
    st.session_state.latest = manager.start_session(sid)
latest = st.session_state.latest
completed_fields, total_fields = _profile_progress(session)

st.markdown(
    '<div class="scope-note">◈ برای حفظ دقت، این گفت‌وگو فقط روی هدف شغلی، تجربه‌ها و مهارت‌های شما تمرکز دارد. '
    'هیچ مهارت یا سابقه‌ای بدون تأیید شما به پروفایل اضافه نمی‌شود.</div>',
    unsafe_allow_html=True,
)
if st.session_state.active_demo:
    st.caption("نسخهٔ آزمایشی · نتیجه‌ها بر پایهٔ داده‌های نمونه ساخته می‌شوند.")

progress_col, progress_status = st.columns([4, 1])
with progress_col:
    st.progress(completed_fields / total_fields, text=f"پروفایل شما · {completed_fields} از {total_fields} بخش کامل شده")
with progress_status:
    st.markdown(
        f'<div class="status-pill">● {"آماده" if latest.is_complete else "در حال تکمیل"}</div>',
        unsafe_allow_html=True,
    )

chat_tab, graph_tab, profile_tab, team_tab = st.tabs(["گفت‌وگو", "مسیر پیشنهادی", "پروفایل من", "دربارهٔ مسیر"])

with chat_tab:
    conversation_col, context_col = st.columns([1.7, .8], gap="large")
    with conversation_col:
        st.markdown('<div class="panel-title">مشاور مسیر شغلی</div>', unsafe_allow_html=True)
        st.markdown('<div class="panel-copy">با چند پاسخ کوتاه، تصویر دقیق‌تری از نقطهٔ فعلی و مقصد شغلی‌ات می‌سازیم.</div>', unsafe_allow_html=True)
        if run_demo:
            manager.reset_session(sid)
            manager.start_session(sid)
            for message in ["تحلیلگر داده", "جونیور", "دانشجوی مهندسی کامپیوتر هستم", "0 سال سابقه دارم و مبتدی هستم", "هیچ مهارتی ندارم", "تایید می‌کنم"]:
                st.session_state.latest = manager.handle_user_turn(sid, message)
            st.rerun()
        for message in session.history:
            with st.chat_message(message["role"]):
                st.write(message["content"])
        for code in latest.warnings:
            st.warning(WARNING_TEXT.get(code, "خروجی به بررسی نیاز دارد."))
        if session.assessment_finished and not latest.is_complete:
            st.info("ارزیابی پرسشی تمام شده است؛ موارد باقی‌مانده را در تب پروفایل کامل کن.")
        prompt = st.chat_input("پاسخت را بنویس…", key="chat")
        if prompt:
            with st.spinner("در حال بررسی پاسخ…"):
                st.session_state.latest = manager.handle_user_turn(sid, prompt)
            st.rerun()

    with context_col:
        st.markdown('<div class="panel-title">رزومه داری؟</div>', unsafe_allow_html=True)
        st.markdown('<div class="panel-copy">با بارگذاری رزومه، بخشی از اطلاعات اولیه سریع‌تر تکمیل می‌شود. قبل از ساخت مسیر می‌توانی همه‌چیز را بازبینی کنی.</div>', unsafe_allow_html=True)
        resume_upload = st.file_uploader("رزومه", type=["pdf", "docx", "txt"], label_visibility="collapsed", key="resume_upload")
        process_resume = st.button("بررسی رزومه", type="primary", width="stretch", disabled=resume_upload is None, key="process_resume")
        if process_resume and resume_upload is not None:
            try:
                document = extract_resume_text(resume_upload.name, resume_upload.getvalue())
                with st.spinner("در حال استخراج اطلاعات مرتبط…"):
                    st.session_state.latest = manager.handle_user_turn(sid, document.text)
                st.session_state.resume_notice = f"رزومهٔ {document.file_type} بررسی شد. " + ("به‌دلیل طول فایل، ۸۰۰۰ نویسهٔ نخست پردازش شد." if document.truncated else "اطلاعات استخراج‌شده را بررسی کن.")
                st.rerun()
            except ResumeError as exc:
                st.error(str(exc))
        if st.session_state.get("resume_notice"):
            st.success(st.session_state.resume_notice)

        profile = session.slots
        skill_labels = [escape(manager.guardrail.concepts[item].label) for item in profile.known_concepts]
        st.markdown(
            f'<div class="profile-card"><span class="status-pill">● خلاصهٔ شما</span>'
            f'<div class="label">نقش هدف</div><div class="value">{_role_label(manager, profile.target_role)}</div>'
            f'<div class="label">سطح هدف</div><div class="value">{LEVEL_LABELS.get(profile.target_level, "هنوز مشخص نشده")}</div>'
            f'<div class="label">سطح فعلی</div><div class="value">{LEVEL_LABELS.get(profile.current_level, "هنوز مشخص نشده")}</div>'
            f'<div class="label">مهارت‌های عملی</div><div class="value">{"، ".join(skill_labels) if skill_labels else ("موردی ثبت نشده" if profile.skills_assessed else "هنوز بررسی نشده")}</div></div>',
            unsafe_allow_html=True,
        )

with graph_tab:
    if latest.roadmap is None:
        st.info("وقتی پروفایل را کامل و تأیید کنی، مسیر پیشنهادی یادگیری اینجا آماده می‌شود.")
        if latest.is_complete and st.button("تلاش دوباره برای ساخت نقشه", key="retry_graph"):
            st.session_state.latest = manager.confirm_profile(sid)
            st.rerun()
    else:
        graph = latest.roadmap
        graph_col, summary_col = st.columns([1.25, 1], gap="large")
        with graph_col:
            st.subheader("گام‌های پیشنهادی یادگیری")
            if graph.nodes:
                st.graphviz_chart(graphviz_dot(graph), width="stretch")
            else:
                st.success("مفهومی برای یادگیری باقی نمانده است.")
            st.caption("شماره‌ها ترتیب پیشنهادی را نشان می‌دهند؛ هر پیکان یک پیش‌نیاز را به گام بعدی وصل می‌کند.")
        with summary_col:
            st.subheader("خلاصهٔ مسیر")
            st.write(latest.summary)
            st.caption("این خلاصه بر اساس اطلاعات تأییدشدهٔ پروفایل شما ساخته شده است.")
            st.download_button("دریافت نقشهٔ راه JSON", graph.model_dump_json(indent=2), "roadmap.json", "application/json", key="download_graph", width="stretch")
            st.download_button("دریافت خلاصهٔ فارسی", latest.summary, "summary_fa.txt", "text/plain", key="download_summary", width="stretch")

with profile_tab:
    st.subheader("پروفایل شغلی من")
    st.caption("اطلاعات استخراج‌شده را مرور و در صورت نیاز اصلاح کن. مسیر پیشنهادی فقط بعد از تأیید نهایی ساخته می‌شود.")
    guardrail, profile = manager.guardrail, session.slots
    roles = list(guardrail.roles)
    levels, currents = ["junior", "mid", "senior"], ["beginner", "junior", "mid", "senior"]
    sync_key = (sid, session.revision)
    if st.session_state.get("edit_synced") != sync_key:
        st.session_state.update(
            edit_role=profile.target_role if profile.target_role in roles else None,
            edit_level=profile.target_level, edit_current=profile.current_level,
            edit_experience=float(profile.experience_years) if profile.experience_years is not None else None,
            edit_education=profile.education or "", edit_skills=list(profile.known_concepts),
            edit_assessed=profile.skills_assessed, edit_synced=sync_key,
        )
    with st.form("profile_edit"):
        first, second = st.columns(2)
        role = first.selectbox("نقش هدف", roles, index=None, placeholder="انتخاب کن…", format_func=lambda x: guardrail.roles[x].label, key="edit_role")
        level = second.selectbox("سطح هدف", levels, index=None, placeholder="انتخاب کن…", format_func=lambda x: LEVEL_LABELS[x], key="edit_level")
        current = first.selectbox("سطح فعلی", currents, index=None, placeholder="انتخاب کن…", format_func=lambda x: LEVEL_LABELS[x], key="edit_current")
        experience = second.number_input("سال سابقهٔ عملی", min_value=0.0, max_value=80.0, value=None, step=.5, key="edit_experience")
        education = st.text_input("تحصیلات یا دوره‌های مرتبط", key="edit_education")
        skills = st.multiselect("مهارت‌هایی که تجربهٔ عملی داری", list(guardrail.concepts), format_func=lambda x: guardrail.concepts[x].label, key="edit_skills")
        assessed = st.checkbox("فهرست مهارت‌ها را بررسی کردم؛ خالی‌بودن یعنی هیچ‌کدام.", key="edit_assessed")
        save = st.form_submit_button("ثبت اصلاحات", type="primary", width="stretch")
    if save:
        st.session_state.latest = manager.apply_profile_update(sid, dict(
            target_role=role, target_level=level, current_level=current, education=education,
            experience_years=experience, known_concepts=skills, skills_assessed=assessed,
        ))
        st.rerun()
    if st.button("تأیید نهایی و ساخت نقشهٔ راه", type="primary", key="confirm", width="stretch"):
        st.session_state.latest = manager.confirm_profile(sid)
        st.rerun()
    with st.expander("دریافت نسخهٔ پروفایل"):
        st.json(latest.profile_json)
        st.download_button("دریافت پروفایل JSON", json.dumps(latest.profile_json, ensure_ascii=False, indent=2), "profile.json", "application/json", key="download_profile")

with team_tab:
    privacy_col, guide_col = st.columns(2, gap="large")
    with privacy_col:
        st.subheader("حریم خصوصی شما")
        st.markdown("""
- گفت‌وگو و رزومه فقط در حافظهٔ نشست نگه‌داری می‌شوند.
- در حالت آنلاین، متن برای تحلیل به سرویس تنظیم‌شدهٔ سامانه ارسال می‌شود.
- رزومه روی دیسک نوشته نمی‌شود و فایل‌های اسکن‌شده بدون متن پشتیبانی نمی‌شوند.
- این دستیار فقط پروفایل شغلی، فاصلهٔ مهارتی و مسیر یادگیری را پوشش می‌دهد.
""")
    with guide_col:
        st.subheader("چطور کار می‌کند؟")
        st.markdown("""
1. دربارهٔ هدف، تجربه و مهارت‌هایت گفت‌وگو می‌کنیم.
2. تو پروفایل ساخته‌شده را مرور و تأیید می‌کنی.
3. فاصلهٔ مهارتی و ترتیب پیشنهادی یادگیری نمایش داده می‌شود.

هر زمان اطلاعاتت را اصلاح کنی، مسیر نیز بر اساس نسخهٔ تازه دوباره ساخته خواهد شد.
""")
    with st.expander("اطلاعات فنی برای تیم توسعه"):
        st.caption(f"موتور فعال: {st.session_state.active_mode} · نسخهٔ داده: {manager.guardrail.taxonomy.version}")
        st.code("response = manager.handle_user_turn(session_id, user_text)\nresponse.profile_json\nresponse.roadmap\nresponse.summary", language="python")
        st.write("رابط کاربری فقط TurnResponse را مصرف می‌کند. موتور گراف با build_roadmap(profile, revision) متصل می‌شود و خروجی پیش از نمایش اعتبارسنجی خواهد شد.")
        st.caption("آمار فنی نشست")
        st.json(session.usage.model_dump())
        st.download_button("دریافت TurnResponse برای هماهنگی تیم", latest.model_dump_json(indent=2), "turn_response.json", "application/json", key="download_response", width="stretch")
