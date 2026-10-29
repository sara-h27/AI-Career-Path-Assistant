"""Streamlit interaction tests without a network call or API key."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1]

class StreamlitTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()

    def test_initial_no_guesses(self):
        at=self.app()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['latest'].question_count,1)
        self.assertIsNone(at.selectbox(key='edit_role').value)
        self.assertIsNone(at.selectbox(key='edit_current').value)
        self.assertIsNone(at.number_input(key='edit_experience').value)

    def test_demo_graph_then_add_remove_reconfirm(self):
        at=self.app();at.button(key='run_demo').click().run()
        self.assertFalse(at.exception);self.assertTrue(at.session_state['latest'].is_complete)
        self.assertEqual(at.session_state['latest'].question_count,6)
        at.chat_input[0].set_value('من با اکسل کار می‌کنم').run()
        self.assertFalse(at.exception)
        self.assertFalse(at.session_state['latest'].is_complete)
        self.assertIsNone(at.session_state['latest'].roadmap)
        self.assertIn('excel',at.multiselect(key='edit_skills').value)
        at.button(key='confirm').click().run()
        self.assertNotIn('excel',at.session_state['latest'].roadmap.study_order)
        at.chat_input[0].set_value('من اکسل بلد نیستم').run()
        self.assertIsNone(at.session_state['latest'].roadmap)
        self.assertNotIn('excel',at.multiselect(key='edit_skills').value)
        at.button(key='confirm').click().run()
        self.assertIn('excel',at.session_state['latest'].roadmap.study_order)
        self.assertFalse(at.exception)

    def test_manual_edit_after_limit(self):
        at=self.app()
        for _ in range(6):at.chat_input[0].set_value('نمی‌دانم').run()
        self.assertFalse(at.session_state['latest'].is_complete)
        at.selectbox(key='edit_role').select('data_analyst')
        at.selectbox(key='edit_level').select('junior')
        at.selectbox(key='edit_current').select('beginner')
        at.number_input(key='edit_experience').set_value(0.0)
        at.text_input(key='edit_education').set_value('دانشجو')
        at.checkbox(key='edit_assessed').check()
        at.button(key='FormSubmitter:profile_edit-ثبت اصلاحات').click().run()
        self.assertFalse(at.exception)
        at.button(key='confirm').click().run()
        self.assertTrue(at.session_state['latest'].is_complete)
        self.assertLessEqual(at.session_state['latest'].question_count,6)

    def test_missing_api_key_graceful(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            at=self.app()
            at.selectbox(key='mode').select('API واقعی').run()
            at.button(key='start').click().run()
            self.assertFalse(at.exception)
            self.assertTrue(at.error)

    def test_reset_is_private_fresh_session(self):
        at=self.app();at.button(key='run_demo').click().run()
        sid=at.session_state['session_id']
        at.button(key='reset').click().run()
        self.assertFalse(at.exception)
        self.assertNotEqual(at.session_state['session_id'],sid)
        self.assertIsNone(at.session_state['latest'].profile_json['target_role'])

if __name__=='__main__':unittest.main()
