import os
import json
import pytest
from backend.app.translator import (
    CANONICAL_FIELDS,
    BaseMappingProvider,
    FieldTranslator,
    LLMMappingProvider,
    MappingResult,
    MockMappingProvider,
    RawLLMResponse,
    TranslationRequest,
    get_translator,
)
from backend.app.main import translate_field, TranslateBody


def test_canonical_fields_defined():
    expected_fields = {
        "full_name",
        "email",
        "phone",
        "degree",
        "graduation_year",
        "skills",
        "current_address",
        "permanent_address",
    }
    assert expected_fields.issubset(set(CANONICAL_FIELDS.keys()))
    for name in expected_fields:
        cf = CANONICAL_FIELDS[name]
        assert cf.name == name
        assert cf.semantic_type
        assert cf.fact_id
        assert cf.label


def test_different_labels_map_to_same_canonical_field():
    translator = FieldTranslator(provider=MockMappingProvider())

    name_labels = ["Full Name", "Applicant's Legal Name", "Name of Candidate", "candidate_name"]
    for label in name_labels:
        res = translator.translate(label)
        assert res.canonical_field == "full_name", f"Failed for label: {label}"
        assert res.semantic_type == "person.name"
        assert res.confidence >= 0.90
        assert not res.requires_user_confirmation

    degree_labels = ["Highest qualification", "Degree", "Academic background"]
    for label in degree_labels:
        res = translator.translate(label)
        assert res.canonical_field == "degree", f"Failed for label: {label}"
        assert res.semantic_type == "education.degree"
        assert not res.requires_user_confirmation

    grad_labels = ["Passing year", "Expected completion", "Graduation year"]
    for label in grad_labels:
        res = translator.translate(label)
        assert res.canonical_field == "graduation_year", f"Failed for label: {label}"
        assert res.semantic_type == "education.graduation_year"
        assert not res.requires_user_confirmation


def test_unknown_labels_return_none():
    translator = FieldTranslator(provider=MockMappingProvider())
    unknown_labels = ["Favorite color", "Shoe size", "Unknown random field", "Hobbies and interests"]
    for label in unknown_labels:
        res = translator.translate(label)
        assert res.canonical_field is None
        assert res.confidence == 0.0


def test_current_versus_permanent_address_ambiguity():
    translator = FieldTranslator(provider=MockMappingProvider())

    # Generic location must be flagged as ambiguous and require user confirmation
    ambiguous_res = translator.translate("Location")
    assert ambiguous_res.canonical_field is None
    assert ambiguous_res.requires_user_confirmation is True
    assert ambiguous_res.confidence <= 0.50
    assert ambiguous_res.semantic_type == "address.unknown"

    # Explicit current address
    current_res = translator.translate("Current location")
    assert current_res.canonical_field == "current_address"
    assert current_res.semantic_type == "address.current"
    assert not current_res.requires_user_confirmation

    # Explicit permanent address
    permanent_res = translator.translate("Permanent address")
    assert permanent_res.canonical_field == "permanent_address"
    assert permanent_res.semantic_type == "address.permanent"
    assert not permanent_res.requires_user_confirmation


def test_adversarial_address_mismatch_requires_confirmation():
    # Simulate a buggy or adversarial model that tries to map permanent address to current_address
    class MismatchProvider(BaseMappingProvider):
        def translate(self, request: TranslationRequest) -> RawLLMResponse:
            return RawLLMResponse(
                canonical_field="current_address",
                confidence=0.95,
                explanation="Model confused permanent with current address",
                requires_user_confirmation=False,
            )

    translator = FieldTranslator(provider=MismatchProvider())
    res = translator.translate("Permanent hometown address")
    # Validator must intercept and require user confirmation
    assert res.requires_user_confirmation is True
    assert res.confidence <= 0.50


def test_invalid_model_output_rejected():
    class HallucinatingProvider(BaseMappingProvider):
        def translate(self, request: TranslationRequest) -> RawLLMResponse:
            return RawLLMResponse(
                canonical_field="non_existent_invented_field",
                confidence=0.99,
                explanation="Hallucinated field",
                requires_user_confirmation=False,
            )

    translator = FieldTranslator(provider=HallucinatingProvider())
    res = translator.translate("Candidate badge number")
    # Non-canonical field must be completely rejected
    assert res.canonical_field is None
    assert res.confidence == 0.0
    assert "Rejected" in res.explanation


def test_low_confidence_requires_user_confirmation():
    class LowConfidenceProvider(BaseMappingProvider):
        def translate(self, request: TranslationRequest) -> RawLLMResponse:
            return RawLLMResponse(
                canonical_field="skills",
                confidence=0.55,
                explanation="Weak match",
                requires_user_confirmation=False,
            )

    translator = FieldTranslator(provider=LowConfidenceProvider())
    res = translator.translate("Tools and other things")
    assert res.canonical_field == "skills"
    # Even if provider said False, confidence < 0.70 must force requires_user_confirmation = True
    assert res.requires_user_confirmation is True


def test_mock_mode_without_api_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    llm_provider = LLMMappingProvider()
    assert not llm_provider.is_available()

    # Translating should cleanly use the fallback MockMappingProvider
    res = llm_provider.translate(TranslationRequest(label="Applicant's Legal Name"))
    assert res.canonical_field == "full_name"


def test_llm_timeout_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-mock-key-12345")
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    llm_provider = LLMMappingProvider()
    assert llm_provider.is_available()

    # Force _call_llm to simulate a network timeout
    def raise_timeout(request):
        raise TimeoutError("Connection timed out after 5.0 seconds")

    monkeypatch.setattr(llm_provider, "_call_llm", raise_timeout)

    res = llm_provider.translate(TranslationRequest(label="Applicant's Legal Name"))
    # Must cleanly fall back to mock without raising
    assert res.canonical_field == "full_name"
    assert "[LLM fallback]" in res.explanation


def test_llm_http_error_falls_back_to_mock(monkeypatch):
    import urllib.error

    monkeypatch.setenv("LLM_API_KEY", "sk-invalid-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    llm_provider = LLMMappingProvider()

    def raise_http_error(request):
        raise urllib.error.HTTPError(
            url="https://api.openai.com/v1/chat/completions",
            code=401,
            msg="Unauthorized: Invalid API Key",
            hdrs={},
            fp=None,
        )

    monkeypatch.setattr(llm_provider, "_call_llm", raise_http_error)

    res = llm_provider.translate(TranslationRequest(label="Contact Email"))
    assert res.canonical_field == "email"
    assert "[LLM fallback]" in res.explanation


def test_llm_markdown_code_block_stripping(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-mock-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    llm_provider = LLMMappingProvider()

    # Simulate an LLM returning json wrapped in markdown backticks
    raw_json_in_markdown = '```json\n{"canonical_field": "degree", "confidence": 0.98, "explanation": "Academic qualification", "requires_user_confirmation": false}\n```'

    class MockHTTPResponse:
        def read(self):
            return json.dumps({
                "choices": [{
                    "message": {
                        "content": raw_json_in_markdown
                    }
                }]
            }).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=5.0: MockHTTPResponse())

    res = llm_provider._call_llm(TranslationRequest(label="Highest Qualification"))
    assert res.canonical_field == "degree"
    assert res.confidence == 0.98


def test_api_translate_endpoint():
    res = translate_field(TranslateBody(label="Candidate Name", description="Full name of applicant"))
    assert res.canonical_field == "full_name"
    assert res.semantic_type == "person.name"
    assert res.confidence >= 0.90
    assert not res.requires_user_confirmation
