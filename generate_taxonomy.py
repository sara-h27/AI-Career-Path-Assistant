import json
import networkx as nx

# 1. Load existing categories and concept seeds
with open("categories.json", "r", encoding="utf-8") as f:
    categories_data = json.load(f)

with open("resources/concept_seeds.json", "r", encoding="utf-8") as f:
    seeds_data = json.load(f)["concepts"]

# Map concept_id to seed data
seed_map = {c["concept_id"]: c for c in seeds_data}
all_concept_ids = set(seed_map.keys())

# Define pedagogical prerequisites for all 145 concepts
PREREQUISITES = {
    # Software Foundation & Core
    "git": [],
    "linux_basics": [],
    "networking_basics": [],
    "python_basics": [],
    "oop": ["python_basics"],
    "data_structures_algorithms": ["oop"],
    "design_patterns": ["oop", "data_structures_algorithms"],
    "http_rest_api": ["networking_basics"],
    "sql_basics": [],
    "sql_advanced": ["sql_basics"],
    "database_design": ["sql_basics"],
    "nosql_mongodb": ["database_design"],
    "django": ["python_basics", "http_rest_api", "sql_basics"],
    "nodejs": ["javascript", "http_rest_api"],
    "unit_testing": ["oop"],
    "web_security": ["http_rest_api"],
    "caching_redis": ["database_design", "networking_basics"],
    "message_queues": ["networking_basics"],
    "docker": ["linux_basics"],
    "kubernetes": ["docker", "networking_basics"],
    "ci_cd": ["git", "docker"],
    "system_design": ["database_design", "networking_basics", "caching_redis"],
    "microservices": ["docker", "http_rest_api", "message_queues"],
    "distributed_systems": ["system_design", "microservices"],
    "nginx": ["linux_basics", "networking_basics"],
    "cloud_basics": ["networking_basics", "linux_basics"],
    "infrastructure_as_code": ["cloud_basics", "linux_basics"],
    "monitoring_observability": ["linux_basics", "docker"],
    "bash_scripting": ["linux_basics"],

    # Frontend
    "html_css": [],
    "javascript": ["html_css"],
    "typescript": ["javascript"],
    "responsive_design": ["html_css"],
    "react": ["javascript", "html_css", "responsive_design"],
    "state_management": ["react"],
    "nextjs": ["react", "typescript"],
    "web_performance": ["javascript", "html_css"],

    # Mobile
    "kotlin": ["oop"],
    "android_development": ["kotlin"],
    "jetpack_compose": ["android_development", "kotlin"],
    "flutter_dart": ["oop"],
    "swift_ios": ["oop"],
    "mobile_architecture": ["oop"],

    # QA & Testing
    "software_testing_fundamentals": [],
    "test_automation": ["software_testing_fundamentals", "python_basics"],
    "api_testing": ["http_rest_api", "software_testing_fundamentals"],
    "performance_testing": ["software_testing_fundamentals", "networking_basics"],
    "agile_scrum": [],

    # Data & AI Foundations
    "excel_basics": [],
    "excel_advanced": ["excel_basics"],
    "statistics_basics": [],
    "probability": [],
    "linear_algebra": [],
    "pandas_numpy": ["python_basics"],
    "data_cleaning": ["pandas_numpy"],
    "data_visualization": ["pandas_numpy"],
    "power_bi": ["excel_basics"],
    "tableau": ["data_visualization"],
    "dax": ["power_bi"],
    "data_modeling": ["sql_basics"],
    "data_warehousing": ["sql_advanced", "data_modeling"],
    "etl_pipelines": ["python_basics", "sql_basics"],
    "airflow": ["etl_pipelines", "python_basics"],
    "spark": ["etl_pipelines", "python_basics"],
    "kafka_streaming": ["message_queues"],
    "hypothesis_testing": ["statistics_basics", "probability"],
    "ab_testing": ["hypothesis_testing"],
    "machine_learning_basics": ["python_basics", "linear_algebra", "statistics_basics"],
    "scikit_learn": ["machine_learning_basics", "pandas_numpy"],
    "feature_engineering": ["scikit_learn", "data_cleaning"],
    "deep_learning": ["machine_learning_basics", "linear_algebra"],
    "pytorch": ["deep_learning"],
    "nlp": ["deep_learning", "pytorch"],
    "computer_vision": ["deep_learning", "pytorch"],
    "time_series": ["statistics_basics", "pandas_numpy"],
    "mlops": ["machine_learning_basics", "docker", "ci_cd"],
    "llm_applications": ["nlp", "python_basics"],

    # Finance & Accounting
    "accounting_principles": [],
    "financial_accounting": ["accounting_principles"],
    "cost_accounting": ["accounting_principles", "financial_accounting"],
    "accounting_software": ["accounting_principles"],
    "payroll_insurance": ["accounting_principles", "labor_law"],
    "direct_tax_law": ["accounting_principles"],
    "vat": ["accounting_principles"],
    "tax_returns": ["direct_tax_law", "vat", "financial_accounting"],
    "accounting_standards": ["financial_accounting"],
    "auditing_fundamentals": ["accounting_principles", "financial_accounting"],
    "internal_control": ["auditing_fundamentals"],
    "risk_management": ["internal_control"],
    "financial_statement_analysis": ["financial_accounting"],
    "financial_modeling": ["excel_advanced", "financial_statement_analysis"],
    "budgeting_forecasting": ["cost_accounting", "excel_advanced"],
    "corporate_valuation": ["financial_modeling", "financial_statement_analysis"],
    "financial_math": [],
    "capital_markets_basics": [],
    "fundamental_analysis": ["financial_statement_analysis", "capital_markets_basics"],
    "technical_analysis": ["capital_markets_basics"],
    "portfolio_management": ["fundamental_analysis", "technical_analysis", "risk_management"],

    # Marketing & Sales
    "marketing_fundamentals": [],
    "digital_marketing_fundamentals": ["marketing_fundamentals"],
    "seo_basics": ["digital_marketing_fundamentals", "html_css"],
    "technical_seo": ["seo_basics"],
    "keyword_research": ["seo_basics"],
    "link_building": ["seo_basics"],
    "wordpress": ["html_css"],
    "copywriting": ["marketing_fundamentals"],
    "content_strategy": ["copywriting", "marketing_fundamentals"],
    "social_media_marketing": ["digital_marketing_fundamentals"],
    "instagram_marketing": ["social_media_marketing"],
    "graphic_design_basics": [],
    "video_editing": ["graphic_design_basics"],
    "google_ads": ["digital_marketing_fundamentals"],
    "google_analytics": ["digital_marketing_fundamentals"],
    "email_marketing": ["digital_marketing_fundamentals", "copywriting"],
    "branding": ["marketing_fundamentals"],
    "growth_marketing": ["digital_marketing_fundamentals", "google_analytics", "ab_testing"],
    "sales_techniques": ["communication_skills"],
    "b2b_sales": ["sales_techniques"],
    "crm": ["sales_techniques"],
    "negotiation": ["communication_skills", "sales_techniques"],
    "market_research": ["marketing_fundamentals", "statistics_basics"],
    "communication_skills": [],
    "presentation_skills": [],

    # Management & HR
    "hrm_fundamentals": [],
    "recruitment_selection": ["hrm_fundamentals"],
    "interviewing_techniques": ["recruitment_selection", "communication_skills"],
    "talent_sourcing": ["recruitment_selection"],
    "employer_branding": ["hrm_fundamentals", "branding"],
    "labor_law": [],
    "performance_management": ["hrm_fundamentals"],
    "compensation_benefits": ["hrm_fundamentals", "payroll_insurance"],
    "hr_analytics": ["hrm_fundamentals", "excel_advanced", "statistics_basics"],
    "project_management_fundamentals": [],
    "project_tools": ["project_management_fundamentals"],
    "project_control": ["project_management_fundamentals", "project_tools"],
    "stakeholder_management": ["project_management_fundamentals", "communication_skills"],
    "leadership": ["communication_skills", "stakeholder_management"],
    "product_management_fundamentals": [],
    "ux_user_research": ["product_management_fundamentals"],
    "product_analytics": ["product_management_fundamentals", "data_visualization"],
    "product_strategy": ["product_management_fundamentals", "business_model", "product_analytics"],
    "requirements_engineering": [],
    "bpmn_process_modeling": ["requirements_engineering"],
    "uml": ["oop", "requirements_engineering"],
    "business_model": ["marketing_fundamentals"]
}

# Verify all 145 concepts have prerequisites defined and references are valid
for cid in all_concept_ids:
    if cid not in PREREQUISITES:
        raise ValueError(f"Concept {cid} missing from PREREQUISITES table!")

for cid, prereqs in PREREQUISITES.items():
    if cid not in all_concept_ids:
        raise ValueError(f"Prerequisite key {cid} does not exist in 145 concept seeds!")
    for p in prereqs:
        if p not in all_concept_ids:
            raise ValueError(f"Prerequisite target {p} for {cid} not found in concept seeds!")

# Build NetworkX graph and verify A-03 (NO CYCLES!)
G = nx.DiGraph()
for cid in all_concept_ids:
    G.add_node(cid)
for cid, prereqs in PREREQUISITES.items():
    for p in prereqs:
        # Edge from prerequisite -> concept (learning flow)
        G.add_edge(p, cid)

if not nx.is_directed_acyclic_graph(G):
    cycles = list(nx.simple_cycles(G))
    raise RuntimeError(f"Cycles detected in concept graph: {cycles}")
else:
    print("SUCCESS: Graph is a strict Directed Acyclic Graph (DAG) with 0 cycles!")

# Prepare structured concept dictionary
concepts_dict = {}
for cid in sorted(all_concept_ids):
    seed = seed_map[cid]
    concepts_dict[cid] = {
        "concept_id": cid,
        "title_fa": seed.get("title_fa", cid),
        "title_en": seed.get("title_en", cid),
        "level": seed.get("level", "junior"),
        "prerequisites": PREREQUISITES[cid],
        "roles": seed.get("roles", [])
    }

# Build Roles dictionary with Junior, Mid, Senior concept levels
# We'll populate each role's levels cleanly from seed mapping, ensuring all 3 levels exist
roles_dict = {}
for domain in categories_data["domains"]:
    for role in domain["roles"]:
        rid = role["role_id"]
        
        # Collect concepts where role is mentioned
        jr_concepts = [c["concept_id"] for c in seeds_data if rid in c.get("roles", []) and c.get("level") == "junior"]
        mid_concepts = [c["concept_id"] for c in seeds_data if rid in c.get("roles", []) and c.get("level") == "mid"]
        sr_concepts = [c["concept_id"] for c in seeds_data if rid in c.get("roles", []) and c.get("level") == "senior"]

        # Ensure balanced distribution for roles where senior concepts were 0 in seed
        # (e.g. promote advanced mid concepts or add domain advanced concepts to senior)
        if rid == "accountant":
            # mid had 8 concepts, promote advanced ones to senior
            sr_concepts = ["accounting_standards", "internal_control", "budgeting_forecasting", "risk_management"]
            mid_concepts = [c for c in mid_concepts if c not in sr_concepts]
        elif rid == "bi_developer":
            sr_concepts = ["data_warehousing", "etl_pipelines", "tableau"]
            mid_concepts = [c for c in mid_concepts if c not in sr_concepts]
        elif rid == "data_analyst":
            sr_concepts = ["ab_testing", "hypothesis_testing", "time_series"]
            mid_concepts = [c for c in mid_concepts if c not in sr_concepts]
        elif rid == "seo_specialist":
            sr_concepts = ["technical_seo", "link_building"]
            mid_concepts = [c for c in mid_concepts if c not in sr_concepts]
        elif rid == "sales_specialist":
            sr_concepts = ["b2b_sales", "negotiation"]
            mid_concepts = [c for c in mid_concepts if c not in sr_concepts]
        elif rid == "tax_specialist":
            sr_concepts = ["tax_returns", "risk_management", "accounting_standards"]
            mid_concepts = [c for c in mid_concepts if c not in sr_concepts]
        elif rid == "qa_engineer":
            if not sr_concepts:
                sr_concepts = ["performance_testing"]

        roles_dict[rid] = {
            "role_id": rid,
            "title_fa": role.get("title_fa", rid),
            "title_en": role.get("title_en", rid),
            "domain_id": domain["domain_id"],
            "domain_title_fa": domain["title_fa"],
            "domain_title_en": domain["title_en"],
            "keywords_fa": role.get("keywords_fa", []),
            "keywords_en": role.get("keywords_en", []),
            "levels": {
                "junior": jr_concepts,
                "mid": mid_concepts,
                "senior": sr_concepts
            }
        }

final_taxonomy = {
    "version": "1.0",
    "description": "Deterministic Skill Taxonomy and Knowledge Graph for AI Career Path Assistant",
    "domains": categories_data["domains"],
    "roles": roles_dict,
    "concepts": concepts_dict
}

with open("taxonomy.json", "w", encoding="utf-8") as out:
    json.dump(final_taxonomy, out, indent=2, ensure_ascii=False)

print(f"taxonomy.json created successfully with {len(roles_dict)} roles and {len(concepts_dict)} concepts.")
