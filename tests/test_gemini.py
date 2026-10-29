import json
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from dialogue import ConversationManager, LLMClient, LLMSettings, TaxonomyGuardrail
from dialogue.schemas import SessionData
ROOT=Path(__file__).resolve().parents[1]

def reply(data=None,**kwargs):
    result={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(data or {})}]}}],
            'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':20,'thoughtsTokenCount':5,'totalTokenCount':125}}
    result.update(kwargs)
    return result

class GeminiTests(unittest.TestCase):
    def client(self,handler,**kwargs):
        cfg=LLMSettings(api_key='SYNTHETIC_METIS_KEY',base_url='https://api.metisai.ir',model='gemini-2.5-flash-lite',protocol='gemini',**kwargs)
        return LLMClient(cfg,httpx.MockTransport(handler))
    def call(self,client):return client.extract_turn_data(SessionData(session_id='x'),'هیچ مهارتی ندارم',TaxonomyGuardrail(ROOT/'data/demo_taxonomy.json'))

    def test_native_request_and_usage(self):
        def handler(request):
            self.assertEqual(str(request.url),'https://api.metisai.ir/v1beta/models/gemini-2.5-flash-lite:generateContent')
            self.assertEqual(request.headers['x-goog-api-key'],'SYNTHETIC_METIS_KEY')
            self.assertNotIn('authorization',request.headers)
            self.assertNotIn('SYNTHETIC_METIS_KEY',str(request.url))
            body=json.loads(request.content)
            self.assertIn('systemInstruction',body);self.assertNotIn('messages',body)
            self.assertEqual(body['generationConfig']['responseMimeType'],'application/json')
            self.assertEqual(body['generationConfig']['maxOutputTokens'],900)
            return httpx.Response(200,json=reply({'skills_assessed':True}))
        r=self.call(self.client(handler,input_usd_per_million=1,output_usd_per_million=2))
        self.assertIsNone(r.error_code);self.assertTrue(r.data.skills_assessed)
        self.assertEqual(r.usage.completion_tokens,25);self.assertEqual(r.usage.budget_tokens,125)
        self.assertAlmostEqual(r.usage.estimated_cost_usd,0.00015)

    def test_thinking_text_not_parsed(self):
        obj=reply();obj['candidates'][0]['content']['parts']=[{'thought':True,'text':'NOT_JSON'}, {'text':'{"education":"دانشجو"}'}]
        r=self.call(self.client(lambda req:httpx.Response(200,json=obj)))
        self.assertIsNone(r.error_code);self.assertEqual(r.data.education,'دانشجو')

    def test_refusal_and_truncation(self):
        for obj,code in [({'promptFeedback':{'blockReason':'SAFETY'}},'refusal'),
                         ({'candidates':[]},'refusal'),
                         (reply(candidates=[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'{}'}]}}]),'invalid_output')]:
            with self.subTest(code=code):
                r=self.call(self.client(lambda req:httpx.Response(200,json=obj)))
                self.assertEqual(r.error_code,code)

    def test_malformed_and_bad_schema(self):
        for text in ['not json','null','{"experience_years":-2}']:
            obj=reply();obj['candidates'][0]['content']['parts'][0]['text']=text
            r=self.call(self.client(lambda req:httpx.Response(200,json=obj)))
            self.assertEqual(r.error_code,'invalid_output')

    def test_schema_and_prompt_modes(self):
        for fmt in ['json_schema','prompt_json']:
            def handler(req):
                generation=json.loads(req.content)['generationConfig']
                if fmt=='json_schema':self.assertIn('responseJsonSchema',generation)
                else:self.assertNotIn('responseMimeType',generation)
                return httpx.Response(200,json=reply())
            r=self.call(self.client(handler,response_format=fmt))
            self.assertIsNone(r.error_code)

    def test_model_and_protocol_validation(self):
        for kw in ({'protocol':'invalid'}, {'protocol':'gemini','model':'../../bad'},{'protocol':'gemini','model':'gemini-x?key=oops'}):
            with self.assertRaises(ValueError):LLMSettings(api_key='synthetic',**kw)

    def test_base_v1beta_not_duplicated(self):
        cfg=LLMSettings(api_key='synthetic',base_url='https://api.metisai.ir/v1beta/',model='models/gemini-2.5-flash-lite',protocol='gemini')
        def handler(req):
            self.assertEqual(req.url.path,'/v1beta/models/gemini-2.5-flash-lite:generateContent')
            return httpx.Response(200,json=reply())
        self.assertIsNone(self.call(LLMClient(cfg,httpx.MockTransport(handler))).error_code)

    def test_native_roundtrip_to_graph(self):
        data={'target_role':'data_analyst','target_level':'junior','current_level':'beginner','education':'دانشجو','experience_years':0,'skills_assessed':True}
        m=ConversationManager(self.client(lambda req:httpx.Response(200,json=reply(data))),TaxonomyGuardrail(ROOT/'data/demo_taxonomy.json'))
        m.start_session('x')
        r=m.handle_user_turn('x','من تحلیلگر داده جونیور می‌خواهم؛ دانشجو و مبتدی هستم؛ صفر سال سابقه دارم و هیچ مهارتی ندارم')
        self.assertEqual(r.status,'awaiting_confirmation')
        r=m.handle_user_turn('x','تایید می‌کنم')
        self.assertTrue(r.is_complete);self.assertIsNotNone(r.roadmap)
        self.assertEqual(r.usage.api_calls,1)

if __name__=='__main__':unittest.main()
