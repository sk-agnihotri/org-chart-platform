from __future__ import annotations

import re
from typing import Any

ALIASES = {"swe": "software engineer", "eng manager": "engineering manager", "eng director": "director of engineering", "ae": "account executive", "hrbp": "hr business partner", "cto": "chief technology officer", "ceo": "chief executive officer", "cfo": "chief financial officer", "coo": "chief operating officer"}
SENIORITY = {"executive": 6, "chief": 6, "president": 6, "director": 5, "vp": 5, "vice president": 5, "head of": 5, "manager": 4, "lead": 3, "principal": 3, "senior": 2, "sr ": 2, "junior": 0, "intern": 0}
FUNCTIONS = {
    "engineering": ("engineer", "developer", "software", "technical", "technology"),
    "sales": ("sales", "account executive", "business development", "revenue"),
    "marketing": ("marketing", "brand", "content", "communications"),
    "people": ("people", "human resources", "hr ", "talent", "recruit"),
    "finance": ("finance", "accountant", "financial", "controller"),
    "operations": ("operations", "logistics", "procurement"),
    "product": ("product", "ux", "design"),
    "customer success": ("customer success", "support", "client service"),
}


def normalize_title(raw_title: Any, taxonomy: Any = None) -> dict[str, Any]:
    raw = "" if raw_title is None else str(raw_title).strip()
    text = re.sub(r"\s+", " ", raw.lower())
    text = ALIASES.get(text, text)
    if taxonomy is not None and not getattr(taxonomy, "empty", True):
        for row in taxonomy.itertuples(index=False):
            canonical, aliases = str(getattr(row, "canonical_title", "")), str(getattr(row, "aliases", ""))
            if text == canonical.lower() or text in [item.strip().lower() for item in aliases.split("|") if item.strip()]:
                text = canonical.lower()
                break
    if not text:
        return {"raw_title": raw_title, "canonical_title": None, "seniority_rank": None, "function": None, "is_management": False, "is_executive": False}
    rank = max((value for token, value in SENIORITY.items() if token in text), default=1)
    function = next((name for name, tokens in FUNCTIONS.items() if any(token in text for token in tokens)), None)
    return {"raw_title": raw_title, "canonical_title": text.title(), "seniority_rank": rank, "function": function, "is_management": rank >= 4, "is_executive": rank >= 6}
