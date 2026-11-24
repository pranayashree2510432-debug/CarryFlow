from __future__ import annotations

import logging
import re
from typing import Optional

from .canonical import CANONICAL_FIELDS, CanonicalFieldDefinition
from .providers import BaseMappingProvider, LLMMappingProvider, MockMappingProvider
from .schema import MappingResult, RawLLMResponse, TranslationRequest

logger = logging.getLogger(__name__)

# Minimum confidence required before auto-approval can be proposed
CONFIDENCE_THRESHOLD = 0.70


class FieldTranslator:
    """
    Intelligent Field Translator that delegates to an AI/rule-based provider
    and applies strict deterministic safety and validation checks.
    """

    def __init__(self, provider: Optional[BaseMappingProvider] = None):
        self.provider = provider or LLMMappingProvider()

    def translate(self, label: str, description: Optional[str] = None) -> MappingResult:
        request = TranslationRequest(
            label=label,
            description=description,
            canonical_fields=list(CANONICAL_FIELDS.keys()),
        )

        try:
            raw: RawLLMResponse = self.provider.translate(request)
        except Exception as e:
            logger.error(f"Provider translation error: {e}")
            raw = RawLLMResponse(
                canonical_field=None,
                confidence=0.0,
                explanation=f"Error translating field: {e}",
                requires_user_confirmation=True,
            )

        return self.validate_and_sanitize(label, raw)

    def validate_and_sanitize(self, original_label: str, raw: RawLLMResponse) -> MappingResult:
        canonical_name = (raw.canonical_field or "").strip().lower()
        confidence = float(raw.confidence)
        requires_confirmation = bool(raw.requires_user_confirmation)
        explanation = raw.explanation or ""

        # 1. Reject invalid or hallucinated canonical fields
        if canonical_name and canonical_name not in CANONICAL_FIELDS:
            logger.warning(f"Rejected invalid canonical field '{canonical_name}' for label '{original_label}'.")
            return MappingResult(
                original_label=original_label,
                canonical_field=None,
                semantic_type="unknown",
                fact_id=None,
                confidence=0.0,
                explanation=f"Rejected unrecognized canonical field '{canonical_name}'.",
                requires_user_confirmation=False,
            )

        # 2. Unknown / unmapped field
        if not canonical_name:
            # Check if this was an ambiguous location
            norm_label = original_label.casefold()
            is_address_word = any(w in norm_label for w in ["location", "address", "city"])
            is_specific = any(w in norm_label for w in ["current", "present", "permanent", "hometown", "native"])

            sem = "address.unknown" if (is_address_word and not is_specific) else "unknown"
            return MappingResult(
                original_label=original_label,
                canonical_field=None,
                semantic_type=sem,
                fact_id=None,
                confidence=min(confidence, 0.45) if is_address_word else 0.0,
                explanation=explanation or f"No canonical profile field matches '{original_label}'.",
                requires_user_confirmation=requires_confirmation or (sem == "address.unknown"),
            )

        # 3. Guard against Address Confusion & Ambiguity
        norm = original_label.casefold()
        has_perm_keyword = any(w in norm for w in ["permanent", "hometown", "native"])
        has_curr_keyword = any(w in norm for w in ["current", "present", "living", "local"])
        is_generic_address = any(w in norm for w in ["location", "address"]) and not has_perm_keyword and not has_curr_keyword

        # If generic location was mapped to either address, require confirmation and clamp confidence
        if is_generic_address and canonical_name in {"current_address", "permanent_address"}:
            canonical_name = None
            requires_confirmation = True
            confidence = min(confidence, 0.45)
            explanation = f"'{original_label}' is ambiguous between current and permanent address; user confirmation required."

        # If label asked for permanent address, never map to current_address without confirmation
        elif has_perm_keyword and canonical_name == "current_address":
            requires_confirmation = True
            confidence = min(confidence, 0.40)
            explanation = f"'{original_label}' indicates permanent address, but was mapped to current address; review required."

        # If label asked for current address, never map to permanent_address without confirmation
        elif has_curr_keyword and canonical_name == "permanent_address":
            requires_confirmation = True
            confidence = min(confidence, 0.40)
            explanation = f"'{original_label}' indicates current address, but was mapped to permanent address; review required."

        # 4. Enforce low-confidence threshold requirement
        if confidence < CONFIDENCE_THRESHOLD:
            requires_confirmation = True
            if canonical_name:
                explanation = f"{explanation} (Low confidence: {int(confidence*100)}% requires confirmation.)".strip()

        # 5. Populate semantic_type and fact_id
        cf_def: Optional[CanonicalFieldDefinition] = CANONICAL_FIELDS.get(canonical_name)
        semantic_type = cf_def.semantic_type if cf_def else "unknown"
        fact_id = cf_def.fact_id if cf_def else None

        return MappingResult(
            original_label=original_label,
            canonical_field=canonical_name or None,
            semantic_type=semantic_type,
            fact_id=fact_id,
            confidence=confidence,
            explanation=explanation,
            requires_user_confirmation=requires_confirmation,
        )


_default_translator: Optional[FieldTranslator] = None


def get_translator() -> FieldTranslator:
    global _default_translator
    if _default_translator is None:
        _default_translator = FieldTranslator()
    return _default_translator
