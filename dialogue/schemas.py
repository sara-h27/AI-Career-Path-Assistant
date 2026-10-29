"""Versioned, validated contracts. No unknown concepts in public profiles."""
from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Level = Literal['junior', 'mid', 'senior']
CurrentLevel = Literal['beginner', 'junior', 'mid', 'senior']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, validate_assignment=True)

class DialogueState(str, Enum):
    ROLE = 'ROLE'
    TARGET_SENIORITY = 'TARGET_SENIORITY'
    EDUCATION = 'EDUCATION'
    EXPERIENCE_AND_CURRENT_LEVEL = 'EXPERIENCE_AND_CURRENT_LEVEL'
    TOOLS_SKILLS = 'TOOLS_SKILLS'
    CONFIRMATION = 'CONFIRMATION'
    COMPLETED = 'COMPLETED'
    INCOMPLETE = 'INCOMPLETE'

class ConceptClaim(StrictModel):
    concept_id: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=1, max_length=1000, description='Exact quote from latest normalized user message')

class TurnExtractionSchema(StrictModel):
    target_role: str | None = Field(default=None, max_length=120)
    target_level: Level | None = None
    current_level: CurrentLevel | None = None
    education: str | None = Field(default=None, max_length=1000)
    experience_years: float | None = Field(default=None, ge=0, le=80, strict=True)
    added_concepts: list[ConceptClaim] = Field(default_factory=list, max_length=100)
    removed_concepts: list[ConceptClaim] = Field(default_factory=list, max_length=100)
    skills_assessed: bool = False
    user_confirmed_final: bool = False

class UserProfile(StrictModel):
    target_role: str | None = None
    target_level: Level | None = None
    current_level: CurrentLevel | None = None
    education: str | None = Field(default=None, max_length=1000)
    experience_years: float | None = Field(default=None, ge=0, le=80, strict=True)
    known_concepts: list[str] = Field(default_factory=list)
    is_confirmed: bool = False

class UserProfileSlots(UserProfile):
    skills_assessed: bool = False

    def public(self) -> UserProfile:
        return UserProfile.model_validate(self.model_dump(exclude={'skills_assessed'}))

class ProfileEdit(StrictModel):
    target_role: str
    target_level: Level
    current_level: CurrentLevel
    education: str = Field(min_length=1, max_length=1000)
    experience_years: float = Field(ge=0, le=80, strict=True)
    known_concepts: list[str]
    skills_assessed: bool = True

class Usage(StrictModel):
    api_calls: int = 0
    failed_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    budget_tokens: int = 0
    usage_missing_calls: int = 0
    estimated_cost_usd: float | None = None
    last_latency_ms: float = 0

class ExtractionResult(StrictModel):
    data: TurnExtractionSchema | None = None
    error_code: str | None = None
    warning_codes: list[str] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)

class RoadmapNode(StrictModel):
    id: str
    label: str

class RoadmapEdge(StrictModel):
    source: str
    target: str

class Roadmap(StrictModel):
    schema_version: Literal['1.0'] = '1.0'
    taxonomy_version: str
    profile_revision: int
    profile_fingerprint: str
    target_role: str
    target_level: Level
    nodes: list[RoadmapNode]
    edges: list[RoadmapEdge]
    study_order: list[str]

class TurnResponse(StrictModel):
    schema_version: Literal['1.0'] = '1.0'
    message: str
    is_complete: bool
    profile_json: dict
    current_state: DialogueState
    status: Literal['collecting', 'awaiting_confirmation', 'complete', 'incomplete', 'error']
    turn_count: int
    question_count: int
    assessment_finished: bool
    profile_revision: int
    warnings: list[str] = Field(default_factory=list)
    roadmap: Roadmap | None = None
    summary: str | None = None
    usage: Usage = Field(default_factory=Usage)

    @property
    def bot_message(self):
        """Read-only backwards compatibility. JSON contract uses message."""
        return self.message

class SessionData(StrictModel):
    session_id: str
    turn_count: int = 0
    question_count: int = 0
    current_state: DialogueState = DialogueState.ROLE
    slots: UserProfileSlots = Field(default_factory=UserProfileSlots)
    history: list[dict[str, str]] = Field(default_factory=list)
    revision: int = 0
    assessment_finished: bool = False
    roadmap: Roadmap | None = None
    summary: str | None = None
    usage: Usage = Field(default_factory=Usage)
