"""OpenAI Chat Completions and native Gemini generateContent adapters; injectable HTTP transport; no logs of payloads."""
import json
import math
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse
import httpx
from .schemas import TurnExtractionSchema, ExtractionResult, Usage
from .prompts import EXTRACTION_SYSTEM_PROMPT

@dataclass
class LLMSettings:
    api_key: str = field(repr=False)
    base_url: str = 'https://api.openai.com/v1'
    model: str = 'gpt-4o-mini'
    response_format: str = 'json_object'
    protocol: str = 'openai'
    timeout_seconds: float = 8.0
    max_output_tokens: int = 900
    max_session_tokens: int = 30000
    input_usd_per_million: float | None = None
    output_usd_per_million: float | None = None

    def __post_init__(self):
        url = urlparse(self.base_url)
        if url.scheme not in ('https','http') or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError('Invalid API base URL')
        if url.scheme=='http' and url.hostname not in ('localhost','127.0.0.1','::1'):
            raise ValueError('Use HTTPS except for a local gateway')
        if not self.api_key.strip() or not self.model.strip(): raise ValueError('API key and model required')
        if self.protocol not in ('openai','gemini'): raise ValueError('Invalid protocol')
        if self.protocol=='gemini' and not re.fullmatch(r'(?:models/)?gemini-[A-Za-z0-9._-]+',self.model):
            raise ValueError('Invalid Gemini model ID')
        if self.response_format not in ('json_object','json_schema','prompt_json'): raise ValueError('Invalid format')
        if not 1 <= self.timeout_seconds <= 30: raise ValueError('Invalid timeout')
        if not 100 <= self.max_output_tokens <= 3000 or self.max_session_tokens < 1000: raise ValueError('Invalid budget')
        for price in (self.input_usd_per_million,self.output_usd_per_million):
            if price is not None and (not isinstance(price,(int,float)) or not math.isfinite(price) or price<0): raise ValueError('Invalid unit price')

def strict_json_schema():
    schema = TurnExtractionSchema.model_json_schema()
    def clean(value):
        if isinstance(value,dict):
            value.pop('default',None)
            if value.get('type')=='object':
                value['additionalProperties']=False
                value['required']=list(value.get('properties',{}))
            for child in list(value.values()): clean(child)
        elif isinstance(value,list):
            for child in value: clean(child)
    clean(schema)
    return schema

def gemini_as_chat_response(obj):
    """Normalize native Gemini without treating thinking text as the extraction JSON."""
    candidates=obj.get('candidates') or []
    choice=candidates[0] if candidates else {}
    finish=choice.get('finishReason')
    parts=(choice.get('content') or {}).get('parts') or []
    text=''.join(p['text'] for p in parts if isinstance(p,dict) and not p.get('thought') and isinstance(p.get('text'),str))
    blocked=(obj.get('promptFeedback') or {}).get('blockReason') or finish in ('SAFETY','RECITATION','BLOCKLIST','PROHIBITED_CONTENT','SPII')
    result={'choices':[{'finish_reason':'stop' if finish=='STOP' else ('length' if finish=='MAX_TOKENS' else 'unknown'),
                        'message':{'content':text or None}}]}
    if blocked:result['choices'][0]['message']['refusal']='blocked'
    usage=obj.get('usageMetadata')
    if isinstance(usage,dict):
        a,b,t=usage.get('promptTokenCount'),usage.get('candidatesTokenCount'),usage.get('thoughtsTokenCount',0)
        if all(type(x) is int and x>=0 for x in (a,b,t)):
            result['usage']={'prompt_tokens':a,'completion_tokens':b+t}
            total=usage.get('totalTokenCount')
            if type(total) is int and total>=a+b+t:result['usage']['total_tokens']=total
    return result

class LLMClient:
    mode = 'api'
    def __init__(self, settings: LLMSettings, transport=None):
        self.settings = settings
        self.transport = transport

    def extract_turn_data(self, session, user_text, taxonomy):
        cfg = self.settings
        payload_data = {
            'state':session.current_state.value,
            'profile':session.slots.public().model_dump(),
            'latest_message':user_text,
            'roles':[{'id':r.id,'label':r.label,'aliases':r.aliases} for r in taxonomy.roles.values()],
            'concepts':[{'id':c.id,'label':c.label,'aliases':c.aliases} for c in taxonomy.concepts.values()],
        }
        schema = strict_json_schema()
        system = EXTRACTION_SYSTEM_PROMPT + '\nJSON schema:\n' + json.dumps(schema,ensure_ascii=False)
        messages = [{'role':'system','content':system},{'role':'user','content':json.dumps(payload_data,ensure_ascii=False)}]
        body = {'model':cfg.model,'messages':messages,'max_tokens':cfg.max_output_tokens}
        if cfg.response_format=='json_schema':
            body['response_format']={'type':'json_schema','json_schema':{'name':'turn_extraction','strict':True,'schema':schema}}
        elif cfg.response_format=='json_object':
            body['response_format']={'type':'json_object'}
        endpoint=cfg.base_url.rstrip('/')+'/chat/completions'
        headers={'Authorization':'Bearer '+cfg.api_key,'Content-Type':'application/json'}
        if cfg.protocol=='gemini':
            model=cfg.model.removeprefix('models/')
            base=cfg.base_url.rstrip('/')
            endpoint=(base if base.endswith('/v1beta') else base+'/v1beta')+'/models/'+model+':generateContent'
            headers={'x-goog-api-key':cfg.api_key,'Content-Type':'application/json'}
            generation={'maxOutputTokens':cfg.max_output_tokens}
            if cfg.response_format!='prompt_json':generation['responseMimeType']='application/json'
            if cfg.response_format=='json_schema':generation['responseJsonSchema']=schema
            body={'systemInstruction':{'parts':[{'text':system}]},
                  'contents':[{'role':'user','parts':[{'text':messages[1]['content']}]}],
                  'generationConfig':generation}
        # UTF-8 bytes + a fixed overhead is intentionally conservative, not measured tokenization.
        reservation = len(json.dumps(messages,ensure_ascii=False).encode()) + 256 + cfg.max_output_tokens
        if session.usage.budget_tokens + reservation > cfg.max_session_tokens:
            return ExtractionResult(error_code='budget_exceeded')
        usage = Usage(api_calls=1,budget_tokens=reservation,usage_missing_calls=1)
        start = time.perf_counter()
        error, data, warnings = None, None, []
        try:
            with httpx.Client(transport=self.transport,timeout=httpx.Timeout(cfg.timeout_seconds,connect=min(3,cfg.timeout_seconds)),follow_redirects=False) as client:
                response = client.post(endpoint,headers=headers,json=body)
            if response.status_code==400:
                error='bad_request'
            else:
                response.raise_for_status()
                obj = response.json()
                if cfg.protocol=='gemini':obj=gemini_as_chat_response(obj)
                raw_usage = obj.get('usage')
                if isinstance(raw_usage,dict):
                    a,b=raw_usage.get('prompt_tokens'),raw_usage.get('completion_tokens')
                    if type(a) is int and type(b) is int and a>=0 and b>=0:
                        usage.prompt_tokens=a;usage.completion_tokens=b
                        usage.budget_tokens=a+b;usage.usage_missing_calls=0
                        total=raw_usage.get('total_tokens')
                        if type(total) is int and total>=a+b:usage.budget_tokens=total
                        if cfg.input_usd_per_million is not None and cfg.output_usd_per_million is not None:
                            usage.estimated_cost_usd=(a*cfg.input_usd_per_million+b*cfg.output_usd_per_million)/1_000_000
                if usage.usage_missing_calls: warnings.append('usage_missing')
                choice=obj['choices'][0]
                message=choice['message']
                if message.get('refusal') or message.get('content') is None:
                    error='refusal'
                elif choice.get('finish_reason') not in ('stop',None):
                    error='invalid_output'
                else:
                    content=message['content']
                    if not isinstance(content,str) or len(content)>40000: raise ValueError('Invalid content')
                    data=TurnExtractionSchema.model_validate_json(content,strict=True)
        except httpx.TimeoutException:
            error='timeout'
        except httpx.HTTPError:
            error='api_error'
        except Exception:
            error='invalid_output'
        if error: usage.failed_calls=1
        usage.last_latency_ms=round((time.perf_counter()-start)*1000,2)
        return ExtractionResult(data=data,error_code=error,warning_codes=warnings,usage=usage)
