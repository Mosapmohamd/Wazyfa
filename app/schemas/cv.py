"""CV extraction request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MatchedSignals(BaseModel):
    role: dict[str, int] = Field(default_factory=dict)
    seniority: dict[str, int] = Field(default_factory=dict)


class CVProfileResponse(BaseModel):
    upload_id: str
    role: str
    target_level: str
    skills: list[str]
    matched_signals: MatchedSignals
    extracted_chars: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "upload_id": "3f2a1b",
                "role": "Machine Learning Engineer",
                "target_level": "Junior",
                "skills": ["python", "pytorch", "docker"],
                "matched_signals": {
                    "role": {"Machine Learning Engineer": 4},
                    "seniority": {"Junior": 1},
                },
                "extracted_chars": 2450,
            }
        }
    }
