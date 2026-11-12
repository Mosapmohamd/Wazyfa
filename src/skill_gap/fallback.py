"""Deterministic keyword-based skill-gap report (no LLM required)."""

from __future__ import annotations

import json

from src.skill_gap.prompts import KEYWORDS


def _fallback_analysis(cv_text: str, market_summary: str) -> str:
    """Return a deterministic JSON report based on keyword comparison."""

    cv_lower = cv_text.lower()
    market_lower = market_summary.lower()
    candidate_skills = [keyword for keyword in KEYWORDS if keyword in cv_lower]
    market_skills = [keyword for keyword in KEYWORDS if keyword in market_lower]
    missing = [keyword for keyword in market_skills if keyword not in candidate_skills]
    matching = [keyword for keyword in candidate_skills if keyword in market_skills]

    report = {
        "summary": {
            "role": "Inferred from CV and market text",
            "readiness": "Needs Development" if missing else "Ready",
            "strength": ", ".join(matching) if matching else "No matching skills found",
            "weakness": ", ".join(missing) if missing else "No major keyword gaps found",
        },
        "market": {"tech": market_skills, "research": [], "soft": [], "exp_years": "", "seniority": ""},
        "candidate": {"exp_years": 0, "seniority": "", "skills": candidate_skills},
        "projects": [],
        "gaps": [
            {
                "missing_req": skill,
                "type": "Skill",
                "severity": "High",
                "evidence": "The skill appears in the market text but not in the CV text.",
                "fix": f"Build and document a project demonstrating {skill}.",
            }
            for skill in missing[:5]
        ],
        "actions": {
            "priority_1": (
                f"Focus on learning: {', '.join(missing[:5])}."
                if missing
                else "Deepen existing skills and add measurable project evidence."
            ),
            "cv_fixes": [],
        },
    }
    return json.dumps(report, ensure_ascii=False)
