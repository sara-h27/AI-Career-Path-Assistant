"""Explicit ONE paid API extraction using synthetic data. Run only after configuring .env."""
import os
from pathlib import Path
from dotenv import load_dotenv
from dialogue import LLMClient, LLMSettings, TaxonomyGuardrail
from dialogue.schemas import SessionData

if __name__=='__main__':
    root=Path(__file__).resolve().parent
    load_dotenv(root/'.env')
    try:
        settings=LLMSettings(api_key=os.getenv('OPENAI_API_KEY',''),base_url=os.getenv('OPENAI_BASE_URL','https://api.openai.com/v1'),
            model=os.getenv('OPENAI_MODEL','gpt-4o-mini'),response_format=os.getenv('LLM_RESPONSE_FORMAT','json_object'),protocol=os.getenv('LLM_PROTOCOL','openai'),
            max_session_tokens=int(os.getenv('MAX_SESSION_TOKENS','30000')))
        taxonomy=TaxonomyGuardrail(root/'data/demo_taxonomy.json')
    except Exception:
        print('Configuration invalid. Check .env; no request sent.')
        raise SystemExit(2)
    result=LLMClient(settings).extract_turn_data(SessionData(session_id='synthetic-api-smoke'),
        'می‌خواهم تحلیلگر داده جونیور شوم. دانشجوی کامپیوترم؛ صفر سال سابقه دارم و مبتدی هستم. فقط اسم SQL را شنیده‌ام.',taxonomy)
    print('Status:',result.error_code or 'OK')
    print('Warnings:',','.join(result.warning_codes) or 'none')
    print('Usage:',result.usage.model_dump_json())
    print('Schema-valid extraction:',result.data is not None)
    raise SystemExit(0 if result.data is not None else 1)
