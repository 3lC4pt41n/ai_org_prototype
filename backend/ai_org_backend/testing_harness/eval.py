from __future__ import annotations

from pydantic import BaseModel, Field


class RubricScore(BaseModel):
    criterion: str
    score: float = Field(ge=0.0, le=1.0)
    rationale: str


class RubricScorer:
    def __init__(self, criteria: list[str]):
        self.criteria = criteria

    def score_keywords(self, text: str, expected_keywords: dict[str, list[str]]) -> list[RubricScore]:
        lower = text.lower()
        scores: list[RubricScore] = []
        for criterion in self.criteria:
            keywords = expected_keywords.get(criterion, [])
            if not keywords:
                scores.append(RubricScore(criterion=criterion, score=0.0, rationale="no keywords configured"))
                continue
            matched = sum(1 for keyword in keywords if keyword.lower() in lower)
            scores.append(
                RubricScore(
                    criterion=criterion,
                    score=round(matched / len(keywords), 3),
                    rationale=f"matched {matched}/{len(keywords)} keywords",
                )
            )
        return scores
