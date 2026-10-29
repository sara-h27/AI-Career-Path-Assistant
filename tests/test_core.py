import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import httpx
from pydantic import ValidationError
from dialogue import *
from dialogue.schemas import *
from dialogue.graph import GraphContractError
from dialogue.preprocessor import PersianTextPreprocessor
from dialogue.summarizer import RoadmapSummarizer

ROOT=Path(__file__).resolve().parents[1]
DEMO=['تحلیلگر داده','جونیور','دانشجوی مهندسی کامپیوتر هستم','0 سال سابقه دارم و مبتدی هستم','هیچ مهارتی ندارم','تایید می‌کنم']
EDIT=dict(target_role='data_analyst',target_level='junior',current_level='beginner',education='دانشجو',experience_years=0,known_concepts=['excel'],skills_assessed=True)

def taxonomy():return TaxonomyGuardrail(ROOT/'data/demo_taxonomy.json')
def manager(client=None,engine=None):return ConversationManager(client or MockLLMClient(),taxonomy(),engine)
def complete(m,sid='x'):
    m.start_session(sid)
    for text in DEMO:r=m.handle_user_turn(sid,text)
    return r

class CoreTests(unittest.TestCase):
    def test_six_question_path_and_empty_skills(self):
        m=manager();r=complete(m)
        self.assertTrue(r.is_complete);self.assertEqual(r.question_count,6)
        self.assertEqual(r.turn_count,6);self.assertEqual(r.profile_json['known_concepts'],[])
        self.assertTrue(r.roadmap);self.assertTrue(r.summary)

    def test_no_data_is_not_success_and_no_invented_level(self):
        m=manager();m.start_session('x')
        for _ in range(12):r=m.handle_user_turn('x','اطلاعی ندارم')
        self.assertFalse(r.is_complete);self.assertTrue(r.assessment_finished)
        self.assertLessEqual(r.question_count,6);self.assertLessEqual(r.turn_count,6)
        self.assertIsNone(r.profile_json['current_level']);self.assertIsNone(r.roadmap)
        self.assertNotIn('؟',r.message)

    def test_slot_skip(self):
        m=manager();m.start_session('x')
        r=m.handle_user_turn('x','می‌خواهم تحلیلگر داده جونیور شوم؛ دانشجو هستم؛ 0 سال سابقه دارم؛ سطح فعلی مبتدی است؛ هیچ مهارتی ندارم')
        self.assertEqual(r.current_state,DialogueState.CONFIRMATION)
        self.assertEqual(r.question_count,2)

    def test_prune_and_aliases(self):
        g=taxonomy()
        self.assertEqual(g.validate_role('بک‌اند'),'backend_developer')
        self.assertIsNone(g.validate_role('من نمی‌خواهم بک‌اند باشم'))
        self.assertEqual(g.filter_concepts(['پایتون','telepathy','Python'])[0],['python'])

    def test_unknowns_not_public(self):
        class Fake:
            def extract_turn_data(self,*args):return ExtractionResult(data=TurnExtractionSchema(added_concepts=[ConceptClaim(concept_id='telepathy',evidence='telepathy')]))
        r=manager(Fake()).handle_user_turn('x','telepathy بلدم')
        self.assertNotIn('telepathy',json.dumps(r.profile_json))
        self.assertNotIn('discarded_concepts',r.profile_json)
        self.assertIn('unknown_concept',r.warnings)

    def test_evidence_cannot_hide_hearsay(self):
        class Fake:
            def extract_turn_data(self,*args):return ExtractionResult(data=TurnExtractionSchema(added_concepts=[ConceptClaim(concept_id='sql',evidence='sql')],skills_assessed=True))
        r=manager(Fake()).handle_user_turn('x','فقط اسم sql را شنیده‌ام')
        self.assertEqual(r.profile_json['known_concepts'],[])
        self.assertIn('negative_or_hearsay',r.warnings)

    def test_evidence_must_match_message_and_concept(self):
        class Fake:
            def extract_turn_data(self,*args):return ExtractionResult(data=TurnExtractionSchema(added_concepts=[ConceptClaim(concept_id='sql',evidence='python بلدم')]))
        r=manager(Fake()).handle_user_turn('x','python بلدم')
        self.assertEqual(r.profile_json['known_concepts'],[])
        self.assertIn('unverified_evidence',r.warnings)

    def test_add_then_remove_and_regenerate(self):
        m=manager();m.apply_profile_update('x',EDIT);old=m.confirm_profile('x')
        self.assertNotIn('excel',old.roadmap.study_order)
        r=m.handle_user_turn('x','من اکسل بلد نیستم')
        self.assertEqual(r.profile_json['known_concepts'],[])
        self.assertFalse(r.profile_json['is_confirmed']);self.assertIsNone(r.roadmap)
        self.assertIsNone(r.summary)
        new=m.confirm_profile('x')
        self.assertIn('excel',new.roadmap.study_order)
        self.assertGreater(new.profile_revision,old.profile_revision)

    def test_edit_role_invalidates_confirmation(self):
        m=manager();complete(m)
        r=m.apply_profile_update('x',{**EDIT,'target_role':'backend_developer'})
        self.assertFalse(r.is_complete);self.assertIsNone(r.roadmap)
        self.assertIn('confirmation_required',r.warnings)

    def test_negative_confirmation_not_accepted(self):
        m=manager();m.start_session('x')
        for t in DEMO[:-1]:m.handle_user_turn('x',t)
        r=m.handle_user_turn('x','نه، تایید نمی‌کنم')
        self.assertFalse(r.is_complete);self.assertFalse(r.profile_json['is_confirmed'])

    def test_confirmation_can_be_withdrawn(self):
        m=manager();complete(m)
        r=m.handle_user_turn('x','تایید نمی‌کنم')
        self.assertFalse(r.is_complete)
        self.assertIsNone(r.roadmap)
        self.assertFalse(r.profile_json['is_confirmed'])

    def test_confirm_cannot_fill_missing(self):
        r=manager().confirm_profile('x')
        self.assertFalse(r.is_complete);self.assertIsNone(r.roadmap)

    def test_session_isolation(self):
        m=manager();complete(m,'a')
        b=m.start_session('b')
        self.assertIsNone(b.profile_json['target_role']);self.assertFalse(b.is_complete)

    def test_expiry(self):
        m=manager();m.start_session('x');m._touched['x']-=8000
        self.assertEqual(m.get_or_create_session('x').question_count,0)

    def test_contract(self):
        r=manager().start_session('x')
        obj=json.loads(r.model_dump_json())
        for k in ('message','is_complete','profile_json'):self.assertIn(k,obj)
        self.assertEqual(r.bot_message,r.message)

    def test_schema_constraints(self):
        for kw in ({'target_level':'wizard'},{'current_level':'expert'},{'experience_years':-1},{'experience_years':float('nan')},{'experience_years':float('inf')},{'invented':True}):
            with self.subTest(kw=kw),self.assertRaises(ValidationError):TurnExtractionSchema(**kw)

    def test_invalid_manual_edit_atomic(self):
        m=manager();complete(m);before=m.sessions['x'].slots.model_dump()
        r=m.apply_profile_update('x',{**EDIT,'known_concepts':['telepathy']})
        self.assertEqual(r.status,'error');self.assertEqual(before,m.sessions['x'].slots.model_dump())

    def test_no_implicit_taxonomy(self):
        with self.assertRaises(TaxonomyError):TaxonomyGuardrail()
        with self.assertRaises(TaxonomyError):TaxonomyGuardrail('/does/not/exist')

    def test_corrupt_or_partial_taxonomy_rejected(self):
        for obj in ({'roles':[]},{'roles':[{'id':'r'}],'concepts':['python']},{}):
            with self.subTest(obj=obj),self.assertRaises(TaxonomyError):TaxonomyGuardrail(data=obj)

    def test_custom_file_alias(self):
        obj=json.loads((ROOT/'data/demo_taxonomy.json').read_text());obj['roles'][0]['aliases'].append('نقش سفارشی')
        g=TaxonomyGuardrail(data=obj)
        self.assertEqual(g.validate_role('نقش سفارشی'),'backend_developer')

    def test_cycle_and_unknown_ref(self):
        obj=json.loads((ROOT/'data/demo_taxonomy.json').read_text())
        for pre in ('python','missing'):
            item=copy.deepcopy(obj);item['concepts'][0]['prerequisites']=[pre]
            with self.assertRaises(TaxonomyError):TaxonomyGuardrail(data=item)

    def test_taxonomy_alias_collision(self):
        obj=json.loads((ROOT/'data/demo_taxonomy.json').read_text())
        obj['concepts'][0]['aliases']=['sql']
        with self.assertRaises(TaxonomyError):TaxonomyGuardrail(data=obj)

    def test_fallback_normalization(self):
        p=PersianTextPreprocessor()
        self.assertEqual(p.preprocess('  پايتون و اكسل ٢ ۳ می کنم  '),'python و excel 2 3 می‌کنم')
        self.assertEqual(p.preprocess(None),'')
        self.assertEqual(p.preprocess('مهارت ها'),'مهارت‌ها')

    def test_hazm_runtime_failure(self):
        class Broken:
            def normalize(self,t):raise RuntimeError('private detail')
        p=PersianTextPreprocessor();p.hazm_normalizer=Broken()
        self.assertEqual(p.preprocess('می روم'),'می‌روم')

    def test_bad_adapter_never_crashes(self):
        for value in (None,{},'invalid'):
            class Fake:
                def extract_turn_data(self,*args):return value
            r=manager(Fake()).handle_user_turn('x','سلام')
            self.assertEqual(r.status,'error');self.assertFalse(r.is_complete)

    def test_failed_graph_no_stale_summary(self):
        class Bad:
            def build_roadmap(self,*args):raise RuntimeError('secret payload')
        m=manager(engine=Bad());m.apply_profile_update('x',EDIT);r=m.confirm_profile('x')
        self.assertIsNone(r.roadmap);self.assertIsNone(r.summary);self.assertIn('graph_error',r.warnings)

    def test_graph_validation_and_summary(self):
        g=taxonomy();m=manager();r=complete(m);graph=r.roadmap
        profile=UserProfile.model_validate(r.profile_json)
        self.assertEqual(validate_roadmap(graph,profile,r.profile_revision,g),graph)
        labels={n.id:n.label for n in graph.nodes}
        for i,cid in enumerate(graph.study_order,1):self.assertIn(f'{i}. {labels[cid]}',r.summary)
        self.assertNotIn('http',r.summary)
        for change in ('unknown','order','revision','label','missing_edge','missing_node'):
            bad=graph.model_copy(deep=True)
            if change=='unknown':bad.nodes[0].id='telepathy'
            if change=='order':bad.study_order=list(reversed(bad.study_order))
            if change=='revision':bad.profile_revision+=1
            if change=='label':bad.nodes[0].label='INVENTED'
            if change=='missing_edge':bad.edges=[]
            if change=='missing_node':bad.nodes=bad.nodes[1:];bad.study_order=bad.study_order[1:]
            with self.subTest(change=change),self.assertRaises(GraphContractError):RoadmapSummarizer(g).summarize(bad,profile,r.profile_revision)

    def test_zero_gap_summary(self):
        m=manager();g=m.guardrail
        edit={**EDIT,'known_concepts':sorted(g.closure('data_analyst','junior'))}
        m.apply_profile_update('x',edit);r=m.confirm_profile('x')
        self.assertEqual(r.roadmap.nodes,[]);self.assertIn('باقی نمانده',r.summary)

    def test_goals_are_not_practical_skills(self):
        class Fake:
            def extract_turn_data(self,*args):return ExtractionResult(data=TurnExtractionSchema(added_concepts=[ConceptClaim(concept_id='sql',evidence='sql')],skills_assessed=True))
        m=manager(Fake())
        r=m.handle_user_turn('x','می خواهم sql یاد بگیرم')
        self.assertEqual(r.profile_json['known_concepts'],[])
        self.assertIn('unverified_evidence',r.warnings)

    def test_entire_taxonomy_graphs(self):
        g=taxonomy()
        for role in g.roles:
            for level in ('junior','mid','senior'):
                with self.subTest(role=role,level=level):
                    profile=UserProfile(target_role=role,target_level=level,known_concepts=['python'])
                    graph=ReferenceGraphEngine(g).build_roadmap(profile,1)
                    validate_roadmap(graph,profile,1,g)
                    RoadmapSummarizer(g).summarize(graph,profile,1)

    def test_response_mutation_cannot_corrupt_session(self):
        m=manager();r=complete(m)
        original=m.sessions['x'].roadmap.nodes[0].id
        r.roadmap.nodes[0].id='mutated'
        self.assertEqual(m.sessions['x'].roadmap.nodes[0].id,original)

    def test_unknown_usage_does_not_show_partial_cost_as_total(self):
        s=SessionData(session_id='x')
        m=manager()
        m._accumulate(s,Usage(api_calls=1,estimated_cost_usd=0.1))
        self.assertEqual(s.usage.estimated_cost_usd,0.1)
        m._accumulate(s,Usage(api_calls=1,usage_missing_calls=1))
        self.assertIsNone(s.usage.estimated_cost_usd)
        m._accumulate(s,Usage(api_calls=1,estimated_cost_usd=0.1))
        self.assertIsNone(s.usage.estimated_cost_usd)

    def test_input_limit(self):
        m=manager()
        for text in ('',None,'x'*8001):
            r=m.handle_user_turn('x',text);self.assertEqual(r.status,'error')
        self.assertEqual(m.sessions['x'].turn_count,0)

class APITests(unittest.TestCase):
    def client(self,handler,**kwargs):return LLMClient(LLMSettings(api_key='TEST_NOT_REAL',**kwargs),httpx.MockTransport(handler))
    def run_call(self,client):return client.extract_turn_data(SessionData(session_id='x'),'sql بلدم',taxonomy())
    def answer(self,data,usage=True):
        obj={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(data)}}]}
        if usage:obj['usage']={'prompt_tokens':100,'completion_tokens':20}
        return httpx.Response(200,json=obj)

    def test_valid_request_and_usage(self):
        def handler(req):
            self.assertTrue(str(req.url).endswith('/v1/chat/completions'))
            body=json.loads(req.content);self.assertEqual(body['response_format']['type'],'json_object')
            return self.answer({'experience_years':2,'current_level':'junior'})
        r=self.run_call(self.client(handler,input_usd_per_million=1,output_usd_per_million=2))
        self.assertIsNone(r.error_code);self.assertEqual(r.data.experience_years,2)
        self.assertEqual(r.usage.budget_tokens,120);self.assertAlmostEqual(r.usage.estimated_cost_usd,0.00014)

    def test_schema_format(self):
        def handler(req):
            schema=json.loads(req.content)['response_format']['json_schema']['schema']
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(set(schema['required']),set(schema['properties']))
            return self.answer({})
        self.assertIsNone(self.run_call(self.client(handler,response_format='json_schema')).error_code)

    def test_malformed_refusal_truncation(self):
        cases=[{'choices':[{'message':{'content':None}}]},
               {'choices':[{'message':{'refusal':'private','content':None}}]},
               {'choices':[{'finish_reason':'length','message':{'content':'{}'}}]},
               {'choices':[{'message':{'content':'{bad'}}]},
               {'choices':[]}, {'choices':[{'message':{'content':'{"experience_years":-2}'}}]}]
        for obj in cases:
            with self.subTest(obj=obj):
                r=self.run_call(self.client(lambda req:httpx.Response(200,json=obj)))
                self.assertIsNotNone(r.error_code);self.assertIsNone(r.data)

    def test_timeout_auth_and_no_logging(self):
        def timeout(req):raise httpx.ReadTimeout('API_KEY_AND_PRIVATE_TEXT',request=req)
        captured=io.StringIO()
        with redirect_stdout(captured),redirect_stderr(captured):
            r=self.run_call(self.client(timeout));self.assertEqual(r.error_code,'timeout')
            r=self.run_call(self.client(lambda req:httpx.Response(401,text='API_KEY_AND_PRIVATE_TEXT')))
            self.assertEqual(r.error_code,'api_error')
        self.assertEqual(captured.getvalue(),'')

    def test_format_rejection_no_auto_retry(self):
        count=[]
        def handler(req):count.append(1);return httpx.Response(400,json={'error':'unsupported'})
        r=self.run_call(self.client(handler))
        self.assertEqual(r.error_code,'bad_request');self.assertEqual(len(count),1)

    def test_missing_usage_conservative_budget(self):
        r=self.run_call(self.client(lambda req:self.answer({},False)))
        self.assertEqual(r.usage.prompt_tokens,0)
        self.assertEqual(r.usage.usage_missing_calls,1)
        self.assertGreater(r.usage.budget_tokens,0)
        self.assertIn('usage_missing',r.warning_codes)

    def test_budget_blocks_network(self):
        def handler(req):raise AssertionError('Must not be called')
        r=self.run_call(self.client(handler,max_session_tokens=1000))
        self.assertEqual(r.error_code,'budget_exceeded');self.assertEqual(r.usage.api_calls,0)

    def test_api_confirmation_local(self):
        def handler(req):raise AssertionError('No API for confirmation')
        m=manager(self.client(handler));m.apply_profile_update('x',EDIT)
        r=m.handle_user_turn('x','تایید می‌کنم')
        self.assertTrue(r.is_complete);self.assertEqual(r.usage.api_calls,0)

    def test_key_not_in_repr_or_outputs(self):
        cfg=LLMSettings(api_key='TEST_NOT_REAL')
        self.assertNotIn('TEST_NOT_REAL',repr(cfg))

if __name__=='__main__':unittest.main()
