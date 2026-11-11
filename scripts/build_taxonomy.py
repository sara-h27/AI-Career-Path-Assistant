"""Build data/taxonomy.json (single source of truth for every module).

Usage:  python scripts/build_taxonomy.py

Inputs:  data/categories.json, data/resources/concept_seeds.json, data/taxonomy_aliases.json
Output:  data/taxonomy.json  (roles with cumulative-ready levels, concepts with prerequisites
         and aliases). Fails on unknown ids, cycles (A-03) or ambiguous aliases.
Original prerequisite table and level derivation: Track 2 (Hemo).
"""
import json
import re
import sys
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))
from dialogue.preprocessor import PersianTextPreprocessor  # noqa: E402

# 1. Load existing categories and concept seeds
with open(DATA / "categories.json", "r", encoding="utf-8") as f:
    categories_data = json.load(f)

with open(DATA / "resources" / "concept_seeds.json", "r", encoding="utf-8") as f:
    seeds_data = json.load(f)["concepts"]

with open(DATA / "taxonomy_aliases.json", "r", encoding="utf-8") as f:
    aliases_data = json.load(f)

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
    "oop": [],  # language-neutral: frontend/mobile/BA must not inherit Python
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
    "data_visualization": [],  # Power BI / Excel users chart without Python
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
    "risk_management": [],  # PMs and investment analysts must not inherit auditing
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
    "negotiation": ["communication_skills"],  # recruiters/PMs must not inherit sales
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
    "product_analytics": ["product_management_fundamentals", "data_visualization", "statistics_basics"],
    "product_strategy": ["product_management_fundamentals", "business_model", "product_analytics"],
    "requirements_engineering": [],
    "bpmn_process_modeling": ["requirements_engineering"],
    "uml": ["oop", "requirements_engineering"],
    "business_model": ["marketing_fundamentals"]
}

# Explicit levels for roles whose seed-derived levels were thin or mixed several stacks.
# Levels are listed incrementally; the engine treats them cumulatively (mid = junior + mid).
ROLE_LEVEL_OVERRIDES = {
    # Hemo's original senior promotions
    "accountant": {
        "junior": ["excel_basics", "accounting_principles", "financial_accounting", "accounting_software",
                   "payroll_insurance", "labor_law"],
        "mid": ["excel_advanced", "cost_accounting", "direct_tax_law", "vat", "tax_returns"],
        "senior": ["accounting_standards", "internal_control", "budgeting_forecasting", "risk_management"],
    },
    "bi_developer": {
        "junior": ["sql_basics", "excel_basics", "data_visualization", "power_bi"],
        "mid": ["sql_advanced", "database_design", "excel_advanced", "dax", "data_modeling"],
        "senior": ["data_warehousing", "etl_pipelines", "tableau"],
    },
    "data_analyst": {
        "junior": ["excel_basics", "sql_basics", "statistics_basics", "data_cleaning", "data_visualization",
                   "power_bi", "python_basics", "pandas_numpy"],
        "mid": ["sql_advanced", "excel_advanced", "tableau", "hypothesis_testing"],
        "senior": ["ab_testing", "time_series", "data_modeling"],
    },
    "backend_developer": {
        "junior": ["git", "linux_basics", "python_basics", "oop", "http_rest_api", "sql_basics", "django"],
        "mid": ["networking_basics", "database_design", "unit_testing", "api_testing", "web_security",
                "docker", "caching_redis", "design_patterns", "ci_cd", "nosql_mongodb", "agile_scrum"],
        "senior": ["data_structures_algorithms", "nginx", "message_queues", "kubernetes",
                   "system_design", "microservices", "distributed_systems"],
    },
    "mobile_developer": {
        "junior": ["git", "oop", "http_rest_api", "kotlin", "android_development"],
        "mid": ["jetpack_compose", "flutter_dart", "unit_testing", "design_patterns", "ci_cd"],
        "senior": ["mobile_architecture", "swift_ios", "data_structures_algorithms"],
    },
    "devops_engineer": {
        "junior": ["git", "linux_basics", "networking_basics", "bash_scripting"],
        "mid": ["python_basics", "docker", "ci_cd", "nginx", "cloud_basics", "web_security"],
        "senior": ["kubernetes", "infrastructure_as_code", "monitoring_observability", "system_design"],
    },
    "tax_specialist": {
        "junior": ["excel_basics", "accounting_principles", "financial_accounting", "direct_tax_law"],
        "mid": ["vat", "tax_returns", "accounting_software", "payroll_insurance"],
        "senior": ["accounting_standards", "internal_control", "labor_law"],
    },
    "seo_specialist": {
        "junior": ["digital_marketing_fundamentals", "seo_basics", "keyword_research", "wordpress", "html_css"],
        "mid": ["google_analytics", "copywriting", "technical_seo", "content_strategy"],
        "senior": ["link_building", "growth_marketing"],
    },
    "sales_specialist": {
        "junior": ["excel_basics", "communication_skills", "sales_techniques", "crm", "presentation_skills"],
        "mid": ["marketing_fundamentals", "negotiation", "b2b_sales", "market_research"],
        "senior": ["digital_marketing_fundamentals", "leadership"],
    },
    "auditor": {
        "junior": ["excel_basics", "accounting_principles", "financial_accounting", "auditing_fundamentals"],
        "mid": ["excel_advanced", "direct_tax_law", "accounting_standards", "internal_control",
                "financial_statement_analysis"],
        "senior": ["risk_management", "accounting_software", "data_visualization"],
    },
    "qa_engineer": {
        "junior": ["git", "software_testing_fundamentals", "http_rest_api", "api_testing", "agile_scrum",
                   "requirements_engineering", "sql_basics"],
        "mid": ["python_basics", "oop", "test_automation", "unit_testing", "docker"],
        "senior": ["ci_cd", "performance_testing"],
    },
}


# Verify all concepts have prerequisites defined and references are valid
for cid in all_concept_ids:
    if cid not in PREREQUISITES:
        raise ValueError(f"Concept {cid} missing from PREREQUISITES table!")
for cid, prereqs in PREREQUISITES.items():
    if cid not in all_concept_ids:
        raise ValueError(f"Prerequisite key {cid} does not exist in concept seeds!")
    for p in prereqs:
        if p not in all_concept_ids:
            raise ValueError(f"Prerequisite target {p} for {cid} not found in concept seeds!")

# A-03: no cycles
G = nx.DiGraph()
G.add_nodes_from(all_concept_ids)
for cid, prereqs in PREREQUISITES.items():
    for p in prereqs:
        G.add_edge(p, cid)  # prerequisite -> concept (learning flow)
if not nx.is_directed_acyclic_graph(G):
    raise RuntimeError(f"Cycles detected in concept graph: {list(nx.simple_cycles(G))}")

# Aliases: must be unambiguous under the same normalisation the dialogue guardrail uses.
_norm = PersianTextPreprocessor(normalize_tech_terms=False)


def alias_key(text):
    text = _norm.preprocess(text).lower().replace("\u200c", " ")
    return " ".join(text.replace("_", " ").replace("-", " ").split())


def collect_aliases(kind, items):
    """items: {id: (title_fa, title_en)} -> {id: [aliases]} ; raises on ambiguity."""
    extra = aliases_data[kind]
    unknown = set(extra) - set(items)
    if unknown:
        raise ValueError(f"taxonomy_aliases.json has unknown {kind}: {sorted(unknown)}")
    owner, out = {}, {}
    for item_id, (title_fa, title_en) in items.items():
        names = [title_en] + extra.get(item_id, [])
        kept = []
        for name in [item_id, title_fa] + names:
            key = alias_key(name)
            if not key:
                continue
            if owner.get(key, item_id) != item_id:
                raise ValueError(f"Ambiguous {kind} alias '{name}': {owner[key]} vs {item_id}")
            owner[key] = item_id
            if name not in (item_id, title_fa) and name not in kept:
                kept.append(name)
        out[item_id] = kept
    return out


concept_aliases = collect_aliases(
    "concepts", {cid: (seed_map[cid]["title_fa"], seed_map[cid]["title_en"]) for cid in all_concept_ids})

concepts_dict = {}
for cid in sorted(all_concept_ids):
    seed = seed_map[cid]
    concepts_dict[cid] = {
        "concept_id": cid,
        "title_fa": seed["title_fa"],
        "title_en": seed["title_en"],
        "level": seed.get("level", "junior"),
        "prerequisites": PREREQUISITES[cid],
        "roles": seed.get("roles", []),
        "aliases": concept_aliases[cid],
    }

roles_dict = {}
role_titles = {}
for domain in categories_data["domains"]:
    for role in domain["roles"]:
        rid = role["role_id"]
        role_titles[rid] = (role["title_fa"], role["title_en"])
        levels = {lvl: [c["concept_id"] for c in seeds_data if rid in c.get("roles", []) and c.get("level") == lvl]
                  for lvl in ("junior", "mid", "senior")}
        levels = ROLE_LEVEL_OVERRIDES.get(rid, levels)
        seen = set()
        for lvl in ("junior", "mid", "senior"):
            levels[lvl] = [c for c in levels[lvl] if c not in seen]
            seen.update(levels[lvl])
            if not levels[lvl]:
                raise ValueError(f"Role {rid} has no concepts at level {lvl}")
            for c in levels[lvl]:
                if c not in concepts_dict:
                    raise ValueError(f"Role {rid} references unknown concept {c}")
        roles_dict[rid] = {
            "role_id": rid,
            "title_fa": role["title_fa"],
            "title_en": role["title_en"],
            "domain_id": domain["domain_id"],
            "domain_title_fa": domain["title_fa"],
            "domain_title_en": domain["title_en"],
            "levels": levels,
        }
role_aliases = collect_aliases("roles", role_titles)
for rid in roles_dict:
    roles_dict[rid]["aliases"] = role_aliases[rid]

final_taxonomy = {
    "version": "1.1",
    "description": "Deterministic skill taxonomy for the AI Career Path Assistant. Levels are incremental; "
                   "a target level requires its own concepts plus all lower levels.",
    "domains": categories_data["domains"],
    "roles": roles_dict,
    "concepts": concepts_dict,
}
(DATA / "taxonomy.json").write_text(json.dumps(final_taxonomy, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"taxonomy.json: {len(roles_dict)} roles, {len(concepts_dict)} concepts, "
      f"{G.number_of_edges()} prerequisite edges, "
      f"{sum(len(c['aliases']) for c in concepts_dict.values())} concept aliases. DAG valid.")
