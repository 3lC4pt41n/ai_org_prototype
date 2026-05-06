from __future__ import annotations

from pydantic import BaseModel, Field


class BookOutline(BaseModel):
    title: str
    audience: str
    thesis: str
    chapters: list[str]
    styleguide: str


class BookChapter(BaseModel):
    index: int
    title: str
    content: str
    parent_outline_version: str = "outline:v1"
    styleguide_version: str = "styleguide:v1"
    research_version: str = "research:v1"
    status: str = "draft"


class ContinuityReport(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    issues: list[str] = []


class EditorialReview(BaseModel):
    approved: bool
    score: float = Field(ge=0.0, le=1.0)
    comments: list[str] = []


def plan_outline(goal: str, audience: str = "general readers", chapter_count: int = 8) -> BookOutline:
    title = goal.strip().rstrip(".") or "Untitled Book"
    thesis = f"{title} explains a coherent argument for {audience}."
    chapters = [f"Chapter {idx}: {title} Part {idx}" for idx in range(1, chapter_count + 1)]
    return BookOutline(
        title=title,
        audience=audience,
        thesis=thesis,
        chapters=chapters,
        styleguide="Clear, concrete, consistent, non-fiction prose.",
    )


def write_chapter(
    outline: BookOutline,
    chapter_index: int,
    *,
    research_summary: str = "Core facts are internally consistent.",
) -> BookChapter:
    title = outline.chapters[chapter_index - 1]
    content = (
        f"{title}\n\n"
        f"Thesis: {outline.thesis}\n"
        f"Audience: {outline.audience}\n"
        f"Research: {research_summary}\n"
        f"This chapter advances the book argument with a stable vocabulary."
    )
    return BookChapter(index=chapter_index, title=title, content=content)


def continuity_check(chapters: list[BookChapter]) -> ContinuityReport:
    issues: list[str] = []
    seen_indexes: set[int] = set()
    for chapter in chapters:
        if chapter.index in seen_indexes:
            issues.append(f"duplicate chapter index {chapter.index}")
        seen_indexes.add(chapter.index)
        if "INCONSISTENT" in chapter.content:
            issues.append(f"chapter {chapter.index} contains explicit inconsistency marker")
    expected = set(range(1, len(chapters) + 1))
    if seen_indexes != expected:
        issues.append("chapter index sequence is incomplete")
    score = max(0.0, 1.0 - (0.2 * len(issues)))
    return ContinuityReport(score=round(score, 3), issues=issues)


def style_harmonize(chapters: list[BookChapter], styleguide: str) -> list[BookChapter]:
    return [
        chapter.model_copy(
            update={
                "content": f"{chapter.content}\n\nStyle pass: {styleguide}",
                "status": "styled",
            }
        )
        for chapter in chapters
    ]


def review_manuscript(chapters: list[BookChapter]) -> EditorialReview:
    continuity = continuity_check(chapters)
    approved = continuity.score >= 0.85 and all(chapter.status in {"styled", "approved"} for chapter in chapters)
    comments = continuity.issues[:]
    if not approved and not comments:
        comments.append("manuscript needs style harmonization before approval")
    return EditorialReview(approved=approved, score=continuity.score, comments=comments)


def run_book_smoke_workflow(goal: str, chapter_count: int = 8) -> dict[str, object]:
    outline = plan_outline(goal, chapter_count=chapter_count)
    chapters = [write_chapter(outline, idx) for idx in range(1, chapter_count + 1)]
    styled = style_harmonize(chapters, outline.styleguide)
    review = review_manuscript(styled)
    manuscript = "\n\n".join(chapter.content for chapter in styled)
    return {
        "outline": outline,
        "chapters": styled,
        "review": review,
        "manuscript": manuscript,
        "lineage": {
            chapter.title: {
                "outline": chapter.parent_outline_version,
                "styleguide": chapter.styleguide_version,
                "research": chapter.research_version,
            }
            for chapter in styled
        },
    }
