"""Skill-gap analysis prompt template and keyword vocabulary."""

_PROMPT_TEMPLATE = """\
Role: Expert technical recruiter and market analyst.
Task: Perform a rigorous, evidence-based skill-gap analysis comparing the CV with market requirements.

INPUTS
[MARKET REQS]: {market_summary}
[CV]: {cv_text}

RULES
1. Ground every claim in the CV or market text. Do not invent dates, metrics, or roles.
2. You may infer underlying skills when the evidence supports the inference.
3. Assess technical, research/analytical, and soft/managerial skills.
4. Treat notebooks and complex algorithms as meaningful AI/R&D experience.
5. Return no more than three projects and five critical gaps.

GAP TYPES
- Articulation: The candidate has the skill but did not describe it clearly.
- Skill: The candidate appears to lack the required technical or soft skill.
- Experience: The candidate lacks the required professional seniority.
- Project: The candidate lacks portfolio evidence for a requirement.

OUTPUT RULES
Return only valid JSON in the following structure:
{
  "summary": {
    "role": "",
    "readiness": "Ready/Needs Development/Not Ready",
    "strength": "",
    "weakness": ""
  },
  "market": {
    "tech": [],
    "research": [],
    "soft": [],
    "exp_years": "",
    "seniority": ""
  },
  "candidate": {
    "exp_years": 0,
    "seniority": "",
    "skills": []
  },
  "projects": [
    {
      "name": "",
      "complexity": "Basic/Intermediate/Advanced",
      "tech_depth": "Brief R&D or algorithmic-depth evaluation",
      "techs": []
    }
  ],
  "gaps": [
    {
      "missing_req": "",
      "type": "Articulation/Skill/Experience/Project",
      "severity": "Low/Moderate/High/Critical",
      "evidence": "Why this gap exists",
      "fix": "Actionable fix"
    }
  ],
  "actions": {
    "priority_1": "",
    "cv_fixes": []
  }
}"""


KEYWORDS = (
    "python", "pytorch", "tensorflow", "docker", "aws", "azure", "gcp", "nlp",
    "natural language processing", "rag", "llm", "transformers", "machine learning",
    "deep learning", "computer vision", "opencv", "kubernetes", "spark", "sql",
    "mongodb", "postgresql", "redis", "fastapi", "flask", "django", "rest",
    "graphql", "kafka", "airflow", "mlflow", "wandb", "git", "ci/cd", "jenkins",
    "terraform", "langchain", "llamaindex", "huggingface", "openai", "scikit-learn",
    "pandas", "numpy", "scipy", "matplotlib", "seaborn", "tableau", "power bi",
    "excel", "statistics", "a/b testing",
)
