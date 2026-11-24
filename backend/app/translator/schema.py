from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class TranslationRequest(BaseModel):
    label: str
    description: Optional[str] = None
    canonical_fields: list[str] = Field(default_factory=list)


class MappingResult(BaseModel):
    original_label: str
    canonical_field: Optional[str] = None
    semantic_type: Optional[str] = None
    fact_id: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    requires_user_confirmation: bool = False

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, round(float(v), 4)))


class RawLLMResponse(BaseModel):
    """Schema expected from LLM JSON generation."""
    canonical_field: Optional[str] = None
    confidence: float = 0.0
    explanation: str = ""
    requires_user_confirmation: bool = False
