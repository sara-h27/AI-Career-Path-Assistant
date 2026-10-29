"""Runnable example; replace the reference call in TeamGraphAdapter with your team's engine."""
from pathlib import Path
from dialogue import ConversationManager, TaxonomyGuardrail, MockLLMClient, ReferenceGraphEngine

class TeamGraphAdapter:
    def __init__(self,taxonomy):
        self.reference=ReferenceGraphEngine(taxonomy)

    def build_roadmap(self,profile,revision):
        # DEMO implementation. A real adapter must return the same validated Roadmap contract.
        return self.reference.build_roadmap(profile,revision)

if __name__=='__main__':
    taxonomy=TaxonomyGuardrail(Path(__file__).resolve().parent/'data/demo_taxonomy.json')
    manager=ConversationManager(MockLLMClient(),taxonomy,graph_engine=TeamGraphAdapter(taxonomy))
    manager.start_session('synthetic-demo')
    for message in ['تحلیلگر داده','جونیور','دانشجو هستم','0 سال سابقه دارم و مبتدی هستم','هیچ مهارتی ندارم','تایید می‌کنم']:
        response=manager.handle_user_turn('synthetic-demo',message)
    print(response.model_dump_json(indent=2))
