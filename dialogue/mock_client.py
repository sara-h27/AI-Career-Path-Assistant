"""Limited, offline rule-based demo. NOT an alternative to testing the real LLM."""
import re
from .schemas import TurnExtractionSchema, ConceptClaim, ExtractionResult, DialogueState

NEGATIVE = re.compile(r'بلد نیست|نمی.?دان|نمی.?دون|کار نکرد|فقط.*اسم|شنید|تسلط ندار|مسلط نیست|تجربه ندار|don.t know|only heard|not know',re.I)
REMOVE = re.compile(r'حذف|remove|اشتباه',re.I)

def claims_in_text(taxonomy,text):
    """Return exact skill occurrences, avoiding accidental substring aliases."""
    found=[]
    normalized=taxonomy._key(text)
    for alias,cid in sorted(taxonomy.concept_aliases.items(),key=lambda x:-len(x[0])):
        if re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',normalized):
            if cid not in found: found.append(cid)
    return found

class MockLLMClient:
    mode='mock'
    def extract_turn_data(self, session, user_text, taxonomy):
        text=taxonomy._key(user_text)
        out={}
        # Select the longest exact role alias; no semantic interpretation.
        for alias,cid in sorted(taxonomy.role_aliases.items(),key=lambda x:-len(x[0])):
            if re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',text):
                out['target_role']=cid;break
        levels={'جونیور':'junior','junior':'junior','میدلول':'mid','مید لول':'mid','mid':'mid','سنیور':'senior','senior':'senior','مبتدی':'beginner','beginner':'beginner'}
        for clause in re.split(r'[؛;،,.!?]',text):
            for alias,level in levels.items():
                if re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',clause):
                    if session.current_state==DialogueState.EXPERIENCE_AND_CURRENT_LEVEL or 'سطح فعلی' in clause or level=='beginner':
                        out['current_level']=level
                    elif level!='beginner': out['target_level']=level
        years=re.search(r'(\d+(?:[.٫]\d+)?)\s*سال',text)
        if years: out['experience_years']=float(years[1].replace('٫','.'))
        elif 'صفر سال' in text or 'سابقه ندارم' in text: out['experience_years']=0.0
        if session.current_state==DialogueState.EDUCATION or any(x in text for x in ('لیسانس','دانشجو','دیپلم','تحصیلات')):
            out['education']=user_text
        add,remove=[],[]
        for clause in re.split(r'[،,؛;.!؟\n]|\s+(?:ولی|اما)\s+',user_text):
            for cid in claims_in_text(taxonomy,clause):
                claim=ConceptClaim(concept_id=cid,evidence=clause.strip())
                if NEGATIVE.search(taxonomy._key(clause)) or REMOVE.search(clause): remove.append(claim)
                elif session.current_state==DialogueState.TOOLS_SKILLS or re.search('بلد|مسلط|کار می|کار کرد|استفاده|پروژه|know|use|worked',taxonomy._key(clause)):
                    add.append(claim)
        out['added_concepts']=add;out['removed_concepts']=remove
        if session.current_state==DialogueState.TOOLS_SKILLS or add or remove or 'هیچ مهارت' in text or 'هیچ کدام' in text or 'هیچکدام' in text:
            out['skills_assessed']=True
        return ExtractionResult(data=TurnExtractionSchema(**out))
