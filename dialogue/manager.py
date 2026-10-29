"""Public UI/graph integration API. Six assistant questions, explicit confirmation, no fabricated success."""
import re
import time
from threading import RLock
from .schemas import (SessionData, TurnResponse, DialogueState, ProfileEdit, ExtractionResult, TurnExtractionSchema)
from .preprocessor import PersianTextPreprocessor
from .prompts import QUESTION_TEXT, LEVEL_LABELS, WARNING_TEXT
from .graph import ReferenceGraphEngine, validate_roadmap
from .summarizer import RoadmapSummarizer
from .mock_client import NEGATIVE, REMOVE, claims_in_text

class ConversationManager:
    MAX_TURNS = 6
    def __init__(self, llm_client, guardrail, graph_engine=None, preprocessor=None, *, max_sessions=100, ttl_seconds=7200):
        self.llm=llm_client
        self.guardrail=guardrail
        self.preprocessor=preprocessor or PersianTextPreprocessor()
        self.graph_engine=graph_engine if graph_engine is not None else ReferenceGraphEngine(guardrail)
        self.summarizer=RoadmapSummarizer(guardrail)
        self.sessions={}
        self._touched={}
        self._lock=RLock()
        self.max_sessions=max_sessions
        self.ttl_seconds=ttl_seconds

    def get_or_create_session(self, session_id):
        if not isinstance(session_id,str) or not 1<=len(session_id)<=128:
            raise ValueError('session_id must be a nonempty string up to 128 characters')
        now=time.monotonic()
        for sid in list(self.sessions):
            if now-self._touched[sid]>self.ttl_seconds:
                self.sessions.pop(sid);self._touched.pop(sid)
        if session_id not in self.sessions:
            if len(self.sessions)>=self.max_sessions:
                oldest=min(self._touched,key=self._touched.get)
                self.sessions.pop(oldest);self._touched.pop(oldest)
            self.sessions[session_id]=SessionData(session_id=session_id)
        self._touched[session_id]=now
        return self.sessions[session_id]

    def reset_session(self, session_id):
        with self._lock:
            self.sessions.pop(session_id,None);self._touched.pop(session_id,None)

    def _missing(self,s):
        p=s.slots
        if not p.target_role:return DialogueState.ROLE
        if not p.target_level:return DialogueState.TARGET_SENIORITY
        if not p.education or not p.education.strip():return DialogueState.EDUCATION
        if p.experience_years is None or not p.current_level:return DialogueState.EXPERIENCE_AND_CURRENT_LEVEL
        if not p.skills_assessed:return DialogueState.TOOLS_SKILLS
        return None

    def _invalidate(self,s):
        s.slots.is_confirmed=False
        s.roadmap=None;s.summary=None
        s.revision+=1

    def _is_yes(self,text):
        t=self.guardrail._key(text).strip(' .!؟،')
        return t in {'بله','آره','اره','تایید','تایید می کنم','بله تایید می کنم','بله درست است','درست است','تایید نهایی','yes','confirm','بله اطلاعات درست است'}

    def profile_description(self,s):
        p=s.slots;g=self.guardrail
        role=g.roles[p.target_role].label if p.target_role in g.roles else 'نامشخص'
        skills='، '.join(g.concepts[c].label for c in p.known_concepts) or ('هیچ‌کدام' if p.skills_assessed else 'نامشخص')
        return (f'نقش هدف: {role}\nسطح هدف: {LEVEL_LABELS.get(p.target_level,"نامشخص")}\n'
            f'سطح فعلی: {LEVEL_LABELS.get(p.current_level,"نامشخص")}\nتحصیلات: {p.education or "نامشخص"}\n'
            f'سابقه: {p.experience_years if p.experience_years is not None else "نامشخص"} سال\nمهارت‌های عملی: {skills}')

    def _response(self,s,message,warnings=(),error=False):
        complete=not self._missing(s) and s.slots.is_confirmed
        status='complete' if complete else ('awaiting_confirmation' if not self._missing(s) else ('incomplete' if s.assessment_finished else 'collecting'))
        if error:status='error'
        r=TurnResponse(message=message,is_complete=bool(complete),profile_json=s.slots.public().model_dump(),
            current_state=s.current_state,status=status,turn_count=s.turn_count,question_count=s.question_count,
            assessment_finished=s.assessment_finished,profile_revision=s.revision,
            warnings=list(dict.fromkeys(warnings)),roadmap=s.roadmap.model_copy(deep=True) if s.roadmap is not None else None,summary=s.summary,usage=s.usage.model_copy(deep=True))
        if message:
            s.history.append({'role':'assistant','content':message})
            s.history=s.history[-60:]
        return r

    def _ask_or_finish(self,s,warnings=()):
        state=self._missing(s)
        if state is None and s.slots.is_confirmed:return self._complete(s,warnings)
        if state is None:
            s.current_state=DialogueState.CONFIRMATION
            if s.question_count<self.MAX_TURNS and not s.assessment_finished:
                s.question_count+=1
                return self._response(s,self.profile_description(s)+'\nآیا این اطلاعات را تأیید می‌کنی؟',warnings)
            s.assessment_finished=True
            return self._response(s,'اطلاعات برای بررسی آماده است. آن را در پنل پروفایل ببین و با دکمهٔ تأیید نهایی ثبت کن.',warnings)
        s.current_state=state
        if s.question_count>=self.MAX_TURNS or s.assessment_finished:
            s.assessment_finished=True;s.current_state=DialogueState.INCOMPLETE
            return self._response(s,'سقف شش سؤال تمام شد، اما پروفایل هنوز کامل نیست. موارد نامشخص را در فرم پروفایل اصلاح کن؛ داده‌ای حدس زده نشده است.',warnings)
        s.question_count+=1
        return self._response(s,QUESTION_TEXT[state.value],warnings)

    def start_session(self,session_id):
        with self._lock:
            s=self.get_or_create_session(session_id)
            if s.history:
                return self._response(s,'نشست فعلی ادامه دارد.')
            return self._ask_or_finish(s)

    def _valid_claim(self,claim,text,remove=False,allow_bare=False):
        cid=self.guardrail.concept_id(claim.concept_id)
        if not cid:return None,'unknown_concept'
        evidence=self.preprocessor.preprocess(claim.evidence)
        if not evidence or evidence not in text or cid not in claims_in_text(self.guardrail,evidence):
            return None,'unverified_evidence'
        # Check enclosing user clause too: quoting just "SQL" cannot hide "only heard" or a denial.
        clauses=re.split(r'[،,؛;.!؟\n]|\s+(?:ولی|اما)\s+',text)
        contexts=[c for c in clauses if evidence in c] or [text]
        if not remove and any(NEGATIVE.search(self.guardrail._key(c)) or REMOVE.search(c) for c in contexts):
            return None,'negative_or_hearsay'
        if not remove:
            # Goals/questions do not establish practical ability, even for real ontology concepts.
            goals=re.compile(r'می خواهم.*یاد|می خوام.*یاد|یاد بگیر|هدف|want to learn|what is|چیست|چیه',re.I)
            positive=re.compile(r'بلد|مسلط|تسلط دار|کار می|کار کرد|استفاده می|استفاده کرد|پروژه|می دانم|می دونم|know|worked|use|built',re.I)
            if any(goals.search(self.guardrail._key(c)) for c in contexts):return None,'unverified_evidence'
            if not any(positive.search(self.guardrail._key(c)) for c in contexts):
                remainder=self.guardrail._key(text)
                for alias in sorted(self.guardrail.concept_aliases,key=len,reverse=True):
                    remainder=re.sub(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',' ',remainder)
                remainder=re.sub(r'[\s,،؛;]+|\bو\b','',remainder)
                if not allow_bare or remainder:return None,'unverified_evidence'
        if remove and not any(NEGATIVE.search(self.guardrail._key(c)) or REMOVE.search(c) for c in contexts):
            return None,'unverified_evidence'
        return cid,None

    def _update_slots(self,s,extracted,text):
        before=s.slots.model_dump()
        p=s.slots;warnings=[]
        if extracted.target_role:
            role=self.guardrail.validate_role(extracted.target_role)
            if role:p.target_role=role
            else:warnings.append('unknown_role')
        for name in ('target_level','current_level','education','experience_years'):
            value=getattr(extracted,name)
            if value is not None and (not isinstance(value,str) or value.strip()):setattr(p,name,value)
        added,removed=set(),set()
        for field,dest,is_remove in ((extracted.added_concepts,added,False),(extracted.removed_concepts,removed,True)):
            for claim in field:
                cid,warning=self._valid_claim(claim,text,is_remove,s.current_state==DialogueState.TOOLS_SKILLS)
                if warning:warnings.append(warning)
                if cid:dest.add(cid)
        p.known_concepts=sorted((set(p.known_concepts)|added)-removed)
        no_skills=re.search(r'هیچ.?مهارت|هیچ.?کدام|هیچکدام|چیزی بلد نیست|مهارتی ندار|هیچی بلد نیست|فقط.*اسم|شنید',self.guardrail._key(text))
        if extracted.skills_assessed and (added or removed or no_skills):p.skills_assessed=True
        if before!=p.model_dump():self._invalidate(s)
        return warnings

    @staticmethod
    def _accumulate(s,usage):
        previous_calls=s.usage.api_calls
        previous_cost=s.usage.estimated_cost_usd
        for field in ('api_calls','failed_calls','prompt_tokens','completion_tokens','budget_tokens','usage_missing_calls'):
            setattr(s.usage,field,getattr(s.usage,field)+getattr(usage,field))
        if usage.api_calls:
            if usage.estimated_cost_usd is None or (previous_calls and previous_cost is None):
                s.usage.estimated_cost_usd=None
            else:
                s.usage.estimated_cost_usd=(previous_cost or 0)+usage.estimated_cost_usd
        s.usage.last_latency_ms=usage.last_latency_ms

    def _complete(self,s,warnings=()):
        s.current_state=DialogueState.COMPLETED;s.assessment_finished=True
        warnings=list(warnings)
        try:
            graph=self.graph_engine.build_roadmap(s.slots.public(),s.revision)
            s.roadmap=validate_roadmap(graph,s.slots.public(),s.revision,self.guardrail)
            s.summary=self.summarizer.summarize(s.roadmap,s.slots.public(),s.revision)
        except Exception:
            s.roadmap=None;s.summary=None;warnings.append('graph_error')
        text='پروفایل تأیید شد و گراف و خلاصهٔ آن آماده است.' if s.roadmap is not None else 'پروفایل تأیید شد؛ گراف در دسترس نیست.'
        return self._response(s,text,warnings)

    def confirm_profile(self,session_id):
        with self._lock:
            s=self.get_or_create_session(session_id)
            if self._missing(s):
                return self._response(s,'پروفایل هنوز اطلاعات نامشخص دارد؛ ابتدا فرم را کامل کن.')
            s.slots.is_confirmed=True
            return self._complete(s)

    def apply_profile_update(self,session_id,edit):
        with self._lock:
            s=self.get_or_create_session(session_id)
            try:
                edit=ProfileEdit.model_validate(edit)
                role=self.guardrail.validate_role(edit.target_role)
                valid,unknown=self.guardrail.filter_concepts(edit.known_concepts)
                if not role or unknown or not edit.skills_assessed:raise ValueError('Invalid profile')
                values=edit.model_dump();values.update(target_role=role,known_concepts=valid)
                from .schemas import UserProfileSlots
                new=UserProfileSlots(**values)
            except Exception:
                return self._response(s,'فرم معتبر نیست؛ نقش، سطح‌ها و مهارت‌ها باید مطابق تاکسونومی باشند. اطلاعات قبلی حفظ شد.',error=True)
            if s.slots.model_dump(exclude={'is_confirmed'})!=new.model_dump(exclude={'is_confirmed'}):
                s.slots=new;self._invalidate(s)
            if s.slots.is_confirmed:return self._complete(s)
            s.current_state=DialogueState.CONFIRMATION
            return self._response(s,'تغییرات ثبت شد. پروفایل جدید برای تأیید نهایی آماده است.',['confirmation_required'])

    def handle_user_turn(self,session_id,user_text):
        with self._lock:
            s=self.get_or_create_session(session_id)
            if not isinstance(user_text,str) or not user_text.strip() or len(user_text)>8000:
                return self._response(s,WARNING_TEXT['input_invalid'],['input_invalid'],error=True)
            text=self.preprocessor.preprocess(user_text)
            if not text:return self._response(s,WARNING_TEXT['input_invalid'],['input_invalid'],error=True)
            if self.guardrail._key(text).strip(' .!؟،') in {'نه','خیر','تایید نمی کنم','نه تایید نمی کنم','اطلاعات درست نیست'} and s.current_state in (DialogueState.CONFIRMATION,DialogueState.COMPLETED):
                s.history.append({'role':'user','content':user_text})
                if s.slots.is_confirmed:self._invalidate(s)
                s.current_state=DialogueState.CONFIRMATION
                return self._response(s,'تأیید ثبت نشد. موارد نادرست را در فرم پروفایل یا همین گفتگو اصلاح کن.')
            # Exact affirmative messages are handled locally. No API charge for confirmation.
            if self._is_yes(text) and not self._missing(s):
                s.history.append({'role':'user','content':user_text})
                if not s.assessment_finished:s.turn_count=min(self.MAX_TURNS,s.turn_count+1)
                return self.confirm_profile(session_id)
            s.history.append({'role':'user','content':user_text})
            if not s.assessment_finished:s.turn_count=min(self.MAX_TURNS,s.turn_count+1)
            try:
                result=self.llm.extract_turn_data(s.model_copy(deep=True),text,self.guardrail)
                # Revalidate adapters too; None/raw dict/invalid instances never reach slot updates.
                result=ExtractionResult.model_validate(result)
                if result.data is None and not result.error_code:result.error_code='invalid_output'
            except Exception:
                result=ExtractionResult(error_code='invalid_output')
            self._accumulate(s,result.usage)
            if result.error_code:
                if s.turn_count>=self.MAX_TURNS and not s.slots.is_confirmed:s.assessment_finished=True
                return self._response(s,WARNING_TEXT.get(result.error_code,WARNING_TEXT['invalid_output']),
                    [*result.warning_codes,result.error_code],error=True)
            warnings=self._update_slots(s,result.data,text)
            if s.turn_count>=self.MAX_TURNS:s.assessment_finished=True
            return self._ask_or_finish(s,[*result.warning_codes,*warnings])
