"""Fail-closed taxonomy and exact aliases; no implicit fallback ontology."""
import json
from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator
from .schemas import StrictModel, Level
from .preprocessor import PersianTextPreprocessor

class TaxonomyError(ValueError):
    pass

class Concept(StrictModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]*$')
    label: str = Field(min_length=1, max_length=160, pattern=r'^[^\n\r<>]+$')
    aliases: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)

class Role(StrictModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]*$')
    label: str = Field(min_length=1, max_length=160, pattern=r'^[^\n\r<>]+$')
    domain: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    requirements: dict[Level, list[str]]

    @model_validator(mode='after')
    def all_levels(self):
        if set(self.requirements) != {'junior','mid','senior'}:
            raise ValueError('All three seniority levels must have explicit requirements')
        if any(not ids for ids in self.requirements.values()):
            raise ValueError('Each seniority needs at least one required concept')
        return self

class Taxonomy(StrictModel):
    schema_version: Literal['1.0'] = '1.0'
    version: str = Field(min_length=1)
    is_demo: bool = False
    roles: list[Role] = Field(min_length=1)
    concepts: list[Concept] = Field(min_length=1)

class TaxonomyGuardrail:
    def __init__(self, taxonomy_path=None, *, data=None):
        if (taxonomy_path is None) == (data is None):
            raise TaxonomyError('Provide exactly one explicit taxonomy path or data object')
        try:
            obj = json.loads(Path(taxonomy_path).read_text(encoding='utf-8-sig')) if taxonomy_path else data
            self.taxonomy = Taxonomy.model_validate(obj)
            self.concepts = {c.id:c for c in self.taxonomy.concepts}
            self.roles = {r.id:r for r in self.taxonomy.roles}
            if len(self.concepts) != len(self.taxonomy.concepts) or len(self.roles) != len(self.taxonomy.roles):
                raise ValueError('Duplicate IDs')
            for c in self.concepts.values():
                if len(c.prerequisites) != len(set(c.prerequisites)) or any(p not in self.concepts for p in c.prerequisites):
                    raise ValueError('Invalid prerequisites')
            for r in self.roles.values():
                if any(c not in self.concepts for ids in r.requirements.values() for c in ids):
                    raise ValueError('Unknown required concept')
            self._validate_dag()
            self._normalizer = PersianTextPreprocessor(normalize_tech_terms=False)
            self.role_aliases = self._aliases(self.roles)
            self.concept_aliases = self._aliases(self.concepts)
        except Exception:
            # Do not include raw taxonomy / validation values in errors or logs.
            raise TaxonomyError('Invalid taxonomy: check schema, IDs, aliases, references and cycles') from None

    def _key(self, text):
        text = self._normalizer.preprocess(text).lower().replace('\u200c',' ')
        return ' '.join(text.replace('_',' ').replace('-',' ').split())

    def _aliases(self, items):
        out = {}
        for item in items.values():
            for name in [item.id,item.label,*item.aliases]:
                key = self._key(name)
                if key in out and out[key] != item.id:
                    raise ValueError('Ambiguous alias')
                out[key] = item.id
        return out

    def _validate_dag(self):
        visited, active = set(), set()
        def visit(cid):
            if cid in active: raise ValueError('Cycle')
            if cid in visited: return
            active.add(cid)
            for pre in self.concepts[cid].prerequisites: visit(pre)
            active.remove(cid);visited.add(cid)
        for cid in self.concepts: visit(cid)

    def validate_role(self, raw):
        return self.role_aliases.get(self._key(raw)) if isinstance(raw,str) else None

    def concept_id(self, raw):
        return self.concept_aliases.get(self._key(raw)) if isinstance(raw,str) else None

    def filter_concepts(self, raw):
        valid, discarded = set(), []
        for item in raw:
            cid = self.concept_id(item)
            if cid: valid.add(cid)
            else: discarded.append(item)
        return sorted(valid), discarded

    def closure(self, role, level):
        if role not in self.roles or level not in self.roles[role].requirements:
            raise TaxonomyError('Invalid role or level')
        found = set()
        def add(cid):
            if cid in found: return
            found.add(cid)
            for pre in self.concepts[cid].prerequisites: add(pre)
        for cid in self.roles[role].requirements[level]: add(cid)
        return found
