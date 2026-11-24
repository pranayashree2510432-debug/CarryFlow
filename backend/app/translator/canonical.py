from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CanonicalFieldDefinition:
    name: str
    semantic_type: str
    fact_id: str
    label: str
    description: str
    example: str


CANONICAL_FIELDS: dict[str, CanonicalFieldDefinition] = {
    "full_name": CanonicalFieldDefinition(
        name="full_name",
        semantic_type="person.name",
        fact_id="full_name",
        label="Full name",
        description="Legal name or candidate full name",
        example="Aarav Mehta",
    ),
    "email": CanonicalFieldDefinition(
        name="email",
        semantic_type="person.email",
        fact_id="email",
        label="Email address",
        description="Primary contact email address",
        example="aarav.mehta@example.test",
    ),
    "phone": CanonicalFieldDefinition(
        name="phone",
        semantic_type="person.phone",
        fact_id="phone",
        label="Phone number",
        description="Mobile or primary contact telephone number",
        example="9876543210",
    ),
    "degree": CanonicalFieldDefinition(
        name="degree",
        semantic_type="education.degree",
        fact_id="education",
        label="Degree",
        description="Highest academic qualification or degree program",
        example="B.Tech Information Technology",
    ),
    "graduation_year": CanonicalFieldDefinition(
        name="graduation_year",
        semantic_type="education.graduation_year",
        fact_id="graduation_year",
        label="Graduation year",
        description="Year of graduation, passing year, or expected completion year",
        example="2027",
    ),
    "skills": CanonicalFieldDefinition(
        name="skills",
        semantic_type="skills.technical",
        fact_id="skills",
        label="Technical skills",
        description="Technical competencies, programming skills, or core abilities",
        example="Python, React, SQL",
    ),
    "current_address": CanonicalFieldDefinition(
        name="current_address",
        semantic_type="address.current",
        fact_id="current_address",
        label="Current address",
        description="Present residential address, current city or location of residence",
        example="12 Lake View Road, Bengaluru",
    ),
    "permanent_address": CanonicalFieldDefinition(
        name="permanent_address",
        semantic_type="address.permanent",
        fact_id="permanent_address",
        label="Permanent address",
        description="Permanent hometown address or permanent legal residence",
        example="44 Park Street, Mysuru",
    ),
}

# Reverse index: semantic_type -> CanonicalFieldDefinition
SEMANTIC_TO_CANONICAL: dict[str, CanonicalFieldDefinition] = {
    cf.semantic_type: cf for cf in CANONICAL_FIELDS.values()
}

# Reverse index: fact_id -> CanonicalFieldDefinition
FACT_ID_TO_CANONICAL: dict[str, CanonicalFieldDefinition] = {
    cf.fact_id: cf for cf in CANONICAL_FIELDS.values()
}
