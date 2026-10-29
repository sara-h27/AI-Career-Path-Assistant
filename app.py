"""Streamlit presentation UI for Member 3; state is private to each browser session."""
import json
import os
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
import streamlit as st
from dialogue import ConversationManager, TaxonomyGuardrail, MockLLMClient, LLMClient, LLMSettings
from dialogue.schemas import ProfileEdit
from dialogue.prompts import WARNING_TEXT, LEVEL_LABELS
from dialogue.ui_helpers import graphviz_dot

ROOT=Path(__file__).resolve().parent
load_dotenv(ROOT/'.env',override=False)
st.set_page_config(page_title='مسیر | دستیار مسیر شغلی',page_icon='🌱',layout='wide')
st.markdown('''<style>
[data-testid="stAppViewContainer"] {direction:rtl;}
[data-testid="stSidebar"] {direction:rtl;}
h1,h2,h3,p,label,[data-testid="stChatMessage"] {text-align:right;}
[data-testid="stCode"],[data-testid="stJson"] {direction:ltr;text-align:left;}
[data-testid="stMetricValue"] {direction:ltr;text-align:right;}
.block-container {padding-top:2.3rem;padding-bottom:3rem;max-width:1500px;}
[data-testid="stChatMessage"] {border:1px solid #24434a;border-radius:16px;}
.stButton>button {border-radius:10px;}
</style>''',unsafe_allow_html=True)

with st.sidebar:
    st.title('مسیر')
    st.caption('Dialogue AI · Step 3 · نسخهٔ ۱٫۰٫۱')
    mode=st.selectbox('نوع اجرا',['دموی آفلاین','API واقعی'],key='mode')
    use_demo=st.checkbox('استفادهٔ صریح از تاکسونومی نمونه',value=True,key='demo_taxonomy')
    uploaded=None
    taxonomy_path=''
    if not use_demo:
        uploaded=st.file_uploader('تاکسونومی تیم گراف (JSON)',type=['json'],key='taxonomy_upload')
        taxonomy_path=st.text_input('یا مسیر فایل تاکسونومی',value=os.getenv('TAXONOMY_PATH',''),key='taxonomy_path')
    api_key='';base_url='';model='';fmt='json_object';protocol='openai';budget=30000
    if mode=='API واقعی':
        st.caption('متن و پروفایل برای استخراج به درگاه انتخابی ارسال می‌شوند. گفتگو و پروفایل در این برنامه روی دیسک ذخیره نمی‌شوند.')
        protocol=st.selectbox('پروتکل اتصال',['openai','gemini'],index=1 if os.getenv('LLM_PROTOCOL','openai')=='gemini' else 0,
            format_func=lambda x:'Gemini native (متیس)' if x=='gemini' else 'OpenAI compatible',key='protocol')
        st.caption('برای Gemini در متیس: پروتکل gemini و Base URL برابر https://api.metisai.ir است.')
        api_key=st.text_input('API key (در همین نشست)',type='password',value='',help='اگر خالی باشد از OPENAI_API_KEY در فایل .env خوانده می‌شود.',key='api_key') or os.getenv('OPENAI_API_KEY','')
        base_url=st.text_input('Base URL',value=os.getenv('OPENAI_BASE_URL','https://api.openai.com/v1'),key='base_url')
        model=st.text_input('نام دقیق مدل در درگاه',value=os.getenv('OPENAI_MODEL','gpt-4o-mini'),key='model')
        formats=['json_object','json_schema','prompt_json']
        default_fmt=os.getenv('LLM_RESPONSE_FORMAT','json_object')
        fmt=st.selectbox('قالب خروجی',formats,index=formats.index(default_fmt) if default_fmt in formats else 0,key='format')
        budget=st.number_input('سقف توکن برای هر نشست',min_value=1000,value=int(os.getenv('MAX_SESSION_TOKENS','30000')),step=1000,key='budget')
        st.caption('json_schema برای مدل‌های پشتیبان؛ json_object برای درگاه‌های سازگار؛ prompt_json فقط در صورت نبود پشتیبانی. همهٔ خروجی‌ها اعتبارسنجی می‌شوند.')
    start=st.button('شروع / اعمال تنظیمات',type='primary',width='stretch',key='start')
    reset=st.button('پاک‌کردن نشست',width='stretch',key='reset')
    st.caption('برای تغییر مدل، کلید یا تاکسونومی، «شروع / اعمال تنظیمات» را بزن. این کار نشست فعلی را پاک می‌کند.')

if reset:
    for key in ('manager','session_id','latest','active_mode','active_demo'):
        st.session_state.pop(key,None)
    st.rerun()

if start or ('manager' not in st.session_state and use_demo and mode=='دموی آفلاین'):
    try:
        if use_demo:g=TaxonomyGuardrail(ROOT/'data/demo_taxonomy.json')
        elif uploaded is not None:
            if uploaded.size>2_000_000:raise ValueError('File too large')
            g=TaxonomyGuardrail(data=json.loads(uploaded.getvalue().decode('utf-8-sig')))
        elif taxonomy_path:g=TaxonomyGuardrail(Path(taxonomy_path).expanduser())
        else:raise ValueError('Taxonomy required')
        if not use_demo and g.taxonomy.is_demo:raise ValueError('Team taxonomy is still marked as demo')
        def unit_price(name):
            value=os.getenv(name,'').strip()
            return float(value) if value else None
        client=MockLLMClient() if mode=='دموی آفلاین' else LLMClient(LLMSettings(api_key=api_key,base_url=base_url,model=model,response_format=fmt,protocol=protocol,max_session_tokens=int(budget),
            input_usd_per_million=unit_price('INPUT_USD_PER_MILLION'),output_usd_per_million=unit_price('OUTPUT_USD_PER_MILLION')))
        manager=ConversationManager(client,g)
        sid=str(uuid4())
        st.session_state.update(manager=manager,session_id=sid,latest=manager.start_session(sid),active_mode=mode,active_demo=g.taxonomy.is_demo)
    except Exception:
        st.error('تنظیمات معتبر نیست. کلید، آدرس، مدل و ساختار تاکسونومی را بررسی کن. نشست قبلی حفظ شده است.')

st.title('از تجربهٔ امروز تا مسیر یادگیری فردا')
st.caption('ارزیابی کوتاه فارسی، پروفایل قابل‌اصلاح و نقشهٔ راهی که توضیحش از خود گراف ساخته می‌شود.')
if 'manager' not in st.session_state:
    st.info('تنظیمات را در نوار کناری وارد کن و «شروع / اعمال تنظیمات» را بزن.')
    st.stop()
manager=st.session_state.manager
sid=st.session_state.session_id
session=manager.get_or_create_session(sid)
if not session.history:
    st.session_state.latest=manager.start_session(sid)
latest=st.session_state.latest
if st.session_state.active_demo:
    st.warning('این اجرا از تاکسونومی نمونه و موتور مرجع گراف استفاده می‌کند. منابع آموزشی به آن متصل نیستند. برای تحویل نهایی، تاکسونومی و موتور تیم را متصل کنید.')
st.caption(f'حالت فعال: {st.session_state.active_mode} · تاکسونومی: {manager.guardrail.taxonomy.version}')
col1,col2,col3,col4=st.columns(4)
col1.metric('سؤال‌های ارزیابی',f'{session.question_count} / 6')
col2.metric('مهارت عملی ثبت‌شده',len(session.slots.known_concepts))
col3.metric('درخواست API',session.usage.api_calls)
col4.metric('آخرین تأخیر',f'{session.usage.last_latency_ms:.0f} ms')
chat_tab,graph_tab,profile_tab,team_tab=st.tabs(['گفتگو','نقشهٔ راه و خلاصه','پروفایل و اصلاح','قرارداد تیم'])
with chat_tab:
    if st.session_state.active_mode=='دموی آفلاین':
        st.info('استخراج این حالت محدود و مبتنی بر قواعد است. برای ارزیابی مدل، API واقعی را انتخاب کن.')
        with st.expander('نمونهٔ گفتگوی شش‌مرحله‌ای برای ارائه'):
            st.code('تحلیلگر داده\nجونیور\nدانشجوی مهندسی کامپیوتر هستم\n0 سال سابقه دارم و مبتدی هستم\nهیچ مهارتی ندارم\nتایید می‌کنم',language='text')
            if st.button('اجرای نمونهٔ کامل (آفلاین و بدون هزینه)',key='run_demo'):
                manager.reset_session(sid)
                manager.start_session(sid)
                for message in ['تحلیلگر داده','جونیور','دانشجوی مهندسی کامپیوتر هستم','0 سال سابقه دارم و مبتدی هستم','هیچ مهارتی ندارم','تایید می‌کنم']:
                    st.session_state.latest=manager.handle_user_turn(sid,message)
                st.rerun()
    for message in session.history:
        with st.chat_message(message['role']):st.text(message['content'])
    for code in latest.warnings:st.warning(WARNING_TEXT.get(code,'خروجی به بررسی نیاز دارد.'))
    if session.assessment_finished and not latest.is_complete:
        st.info('ارزیابی پرسشی تمام شده است. برای تکمیل اطلاعات از فرم پروفایل استفاده کن؛ اصلاح متنی هم در همین گفتگو پذیرفته می‌شود.')
    prompt=st.chat_input('پاسخ، تأیید یا اصلاح مهارت‌ها…',key='chat')
    if prompt:
        with st.spinner('در حال بررسی پیام…'):
            st.session_state.latest=manager.handle_user_turn(sid,prompt)
        st.rerun()
with graph_tab:
    if latest.roadmap is None:
        st.info('پس از تکمیل و تأیید پروفایل، گراف معتبر و خلاصهٔ فارسی اینجا نمایش داده می‌شوند.')
        if latest.is_complete and st.button('تلاش دوباره برای ساخت گراف',key='retry_graph'):
            st.session_state.latest=manager.confirm_profile(sid);st.rerun()
    else:
        graph=latest.roadmap
        left,right=st.columns([1.2,1],gap='large')
        with left:
            st.subheader('گراف مفاهیم باقی‌مانده')
            if graph.nodes:st.graphviz_chart(graphviz_dot(graph),width='stretch')
            else:st.success('مفهومی برای یادگیری باقی نمانده است.')
            st.caption('پیکان از پیش‌نیاز به مفهوم وابسته است. شماره‌ها با ترتیب مطالعهٔ خلاصه یکسان‌اند.')
        with right:
            st.subheader('توضیح فارسی منطبق با گراف')
            st.text(latest.summary)
            st.caption('این متن با قالب قطعی از همان گراف ساخته شده؛ مهارت، لینک یا زمان یادگیری اضافه تولید نمی‌کند.')
            st.download_button('دریافت خروجی گراف JSON',graph.model_dump_json(indent=2),'roadmap.json','application/json',key='download_graph')
            st.download_button('دریافت خلاصهٔ فارسی',latest.summary,'summary_fa.txt','text/plain',key='download_summary')
with profile_tab:
    st.subheader('پروفایل فعلی')
    st.text(manager.profile_description(session))
    st.caption('فرم زیر مسیر دستیِ معتبر برای اصلاح داده‌ها و بازیابی پس از خطای API است. تغییر داده‌ها تأیید قبلی و گراف قبلی را باطل می‌کند.')
    g=manager.guardrail;p=session.slots
    roles=list(g.roles);levels=['junior','mid','senior'];currents=['beginner','junior','mid','senior']
    sync_key=(sid,session.revision)
    if st.session_state.get('edit_synced')!=sync_key:
        st.session_state.update(edit_role=p.target_role if p.target_role in roles else None,
            edit_level=p.target_level,edit_current=p.current_level,
            edit_experience=float(p.experience_years) if p.experience_years is not None else None,edit_education=p.education or '',
            edit_skills=list(p.known_concepts),edit_assessed=p.skills_assessed,edit_synced=sync_key)
    with st.form('profile_edit'):
        a,b=st.columns(2)
        role=a.selectbox('نقش هدف',roles,index=None,placeholder='انتخاب کن…',format_func=lambda x:g.roles[x].label,key='edit_role')
        level=b.selectbox('سطح هدف',levels,index=None,placeholder='انتخاب کن…',format_func=lambda x:LEVEL_LABELS[x],key='edit_level')
        current=a.selectbox('سطح فعلی',currents,index=None,placeholder='انتخاب کن…',format_func=lambda x:LEVEL_LABELS[x],key='edit_current')
        experience=b.number_input('سال سابقه',min_value=0.0,max_value=80.0,value=None,step=0.5,key='edit_experience')
        education=st.text_input('تحصیلات / دوره‌ها (یا توضیح نبود مدرک)',key='edit_education')
        skills=st.multiselect('مهارت‌های دارای تجربهٔ عملی',list(g.concepts),format_func=lambda x:g.concepts[x].label,key='edit_skills')
        assessed=st.checkbox('فهرست مهارت‌ها را بررسی کردم؛ خالی‌بودن یعنی هیچ‌کدام.',key='edit_assessed')
        save=st.form_submit_button('ثبت اصلاحات',type='primary')
    if save:
        st.session_state.latest=manager.apply_profile_update(sid,dict(target_role=role,target_level=level,current_level=current,education=education,experience_years=experience,known_concepts=skills,skills_assessed=assessed))
        st.rerun()
    if st.button('تأیید نهایی پروفایل و ساخت گراف',key='confirm'):
        st.session_state.latest=manager.confirm_profile(sid);st.rerun()
    st.json(latest.profile_json)
    st.download_button('دریافت پروفایل JSON',json.dumps(latest.profile_json,ensure_ascii=False,indent=2),'profile.json','application/json',key='download_profile')
with team_tab:
    st.subheader('مرز اتصال تیم‌ها')
    st.code('response = manager.handle_user_turn(session_id, user_text)\nresponse.message\nresponse.is_complete\nresponse.profile_json\nresponse.roadmap  # validated, current revision only\nresponse.summary  # generated from this exact roadmap',language='python')
    st.write('تیم UI از TurnResponse استفاده می‌کند. تیم گراف، build_roadmap(profile, revision) را مطابق docs/CONTRACTS_FA.md پیاده می‌کند. شناسه‌ها و نسخهٔ تاکسونومی باید بین تیم‌ها یکسان باشند.')
    st.write('موتور مرجع، بستار پیش‌نیازها را محاسبه می‌کند، دانسته‌ها را کم می‌کند و ترتیب توپولوژیک می‌سازد. منابع آموزشی و ماژول رزومه/کاریابی جزو این بستهٔ Step 3 نیستند.')
    st.json(session.usage.model_dump())
    if session.usage.estimated_cost_usd is None:st.caption('هزینهٔ دلاری نامشخص است؛ نرخ واقعی درگاه را در .env تنظیم کن. توکنِ گزارش‌نشده نیز به‌عنوان مصرف واقعی نمایش داده نمی‌شود.')
    st.download_button('دریافت TurnResponse برای هماهنگی تیم',latest.model_dump_json(indent=2),'turn_response.json','application/json',key='download_response')
