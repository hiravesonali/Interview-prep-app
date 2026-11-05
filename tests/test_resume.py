"""AI resume builder: extraction, contact, bullet ids, honesty checks, calls, storage, exports."""

from __future__ import annotations

import io

import pytest

from interview_app.config import Settings
from interview_app.features.resume import (
    BaseResume,
    TailoredResumeDoc,
    UnsupportedFileError,
    build_profile,
    bullet_ids,
    extract_contact,
    extract_text,
    match_scores,
    parse_resume,
    profile_to_text,
    tailor_resume,
    unverified_bullets,
)
from interview_app.features.resume_export import (
    to_docx,
    to_markdown,
    to_pdf,
    view_of_base,
    view_of_tailored,
)
from interview_app.guard import GuardPipeline, InputKind, SecurityLog
from interview_app.llm.client import OpenRouterClient, StructuredResult, Usage
from interview_app.models import (
    Bullet,
    EducationEntry,
    ExperienceEntry,
    KeywordMatch,
    ParsedResume,
    ProjectEntry,
    ResumeProfile,
    SkillCategory,
    TailoredBullet,
    TailoredExperience,
    TailoredResume,
)
from interview_app.storage.db import make_engine
from interview_app.storage.store import Store

RAW = """Ada Lovelace
Berlin, Germany · ada@example.com · +49 170 1234567 · linkedin.com/in/ada-l · github.com/ada

Senior Backend Engineer

Experience
Senior Backend Engineer, Acme, Mar 2021 - present
- Built event-driven order pipeline on Kafka handling 2M events/day
- Led migration from Django monolith to FastAPI services
"""


def _parsed() -> ParsedResume:
    return ParsedResume(
        name="Ada Lovelace",
        location="Berlin, Germany",
        headline="Senior Backend Engineer",
        summary="Backend engineer with 8 years in Python.",
        experience=[
            ExperienceEntry(
                title="Senior Backend Engineer",
                organisation="Acme",
                dates="Mar 2021 - present",
                bullets=[
                    Bullet(text="Built event-driven order pipeline on Kafka, 2M events/day"),
                    Bullet(text="Led migration from Django monolith to FastAPI services"),
                ],
            )
        ],
        projects=[
            ProjectEntry(
                name="hoot",
                description="AI interview coach",
                technologies=["Python", "Streamlit"],
                bullets=[Bullet(text="Shipped a guard pipeline for LLM calls")],
            )
        ],
        skills=[SkillCategory(name="Languages", skills=["Python", "SQL"])],
        education=[EducationEntry(degree="BSc Mathematics", institution="TU Berlin", dates="2014")],
        certifications=["AWS Developer Associate"],
    )


def _profile() -> ResumeProfile:
    return build_profile(_parsed(), RAW)


def _base() -> BaseResume:
    return BaseResume(name="Backend 2026", raw_text=RAW, profile=_profile())


def _tailored(source_ids: list[str]) -> TailoredResume:
    return TailoredResume(
        headline="Senior Backend Engineer · Platform",
        summary="Aimed at the job.",
        experience=[
            TailoredExperience(
                title="Senior Backend Engineer",
                organisation="Acme",
                dates="Mar 2021 - present",
                bullets=[
                    TailoredBullet(text="Kafka pipeline, 2M events/day", source_ids=["e1b1"]),
                    TailoredBullet(text="Kubernetes rollout", source_ids=source_ids, reason="new"),
                ],
            )
        ],
        projects=[],
        skills=[SkillCategory(name="Languages", skills=["Python"])],
        keywords=[
            KeywordMatch(keyword="Kafka", status="present"),
            KeywordMatch(keyword="FastAPI", status="added"),
            KeywordMatch(keyword="Kubernetes", status="missing"),
            KeywordMatch(keyword="Python", status="present"),
        ],
        gaps=["No Kubernetes experience listed"],
        changes_summary="Reordered bullets.",
    )


class FakeStructuredClient(OpenRouterClient):
    def __init__(self, data):
        super().__init__(Settings(openrouter_api_key="t"))
        self.data = data
        self.sent: list[list[dict]] = []

    def chat_structured(self, messages, schema, **kw):  # type: ignore[override]
        self.sent.append(messages)
        assert isinstance(self.data, schema)
        return StructuredResult(self.data, self.data.model_dump_json(), Usage("m", 1, 1, 0.0, 0.1))


def _pipe(data) -> tuple[GuardPipeline, FakeStructuredClient]:
    client = FakeStructuredClient(data)
    return GuardPipeline(client, client.settings, SecurityLog(), llm_guard_enabled=False), client


# ---------- local extraction ----------


def test_extract_text_from_txt_docx_and_pdf() -> None:
    assert "Kafka" in extract_text("cv.txt", RAW.encode())

    from docx import Document

    d = Document()
    d.add_paragraph("Ada Lovelace")
    d.add_paragraph("Built event-driven pipeline on Kafka")
    buf = io.BytesIO()
    d.save(buf)
    text = extract_text("cv.docx", buf.getvalue())
    assert text.splitlines()[0] == "Ada Lovelace" and "Kafka" in text

    pdf = to_pdf(view_of_base(_base()))
    assert "Kafka" in extract_text("cv.pdf", pdf)


def test_unsupported_extension_is_rejected() -> None:
    with pytest.raises(UnsupportedFileError):
        extract_text("cv.pages", b"x")


def test_extract_contact_finds_email_phone_and_links_locally() -> None:
    c = extract_contact(RAW)
    assert c.email == "ada@example.com"
    assert c.phone == "+49 170 1234567"
    assert c.links == ["linkedin.com/in/ada-l", "github.com/ada"]


def test_bullet_ids_and_prompt_text() -> None:
    p = _profile()
    assert bullet_ids(p) == {"e1b1", "e1b2", "p1b1"}
    text = profile_to_text(p)
    assert "[e1b2] Led migration" in text and "[p1b1] Shipped" in text
    assert "ada@example.com" not in text and "1234567" not in text  # contact stays local


# ---------- the two calls ----------


def test_parse_resume_merges_local_contact_and_never_sends_it() -> None:
    pipe, client = _pipe(_parsed())
    result = parse_resume(pipe, RAW)
    profile = result.data
    assert profile.contact.name == "Ada Lovelace" and profile.contact.email == "ada@example.com"
    assert profile.experience[0].bullets[1].id == "e1b2"
    sent = client.sent[0][-1]["content"]
    assert "ada@example.com" not in sent and "[email]" in sent
    assert "1234567" not in sent


def test_tailor_resume_sends_profile_with_ids_and_jd_as_input() -> None:
    pipe, client = _pipe(_tailored(["e1b2"]))
    result = tailor_resume(pipe, _base(), "We need Kafka and Kubernetes.", job_title="Platform Eng")
    assert result.data.headline.startswith("Senior")
    sent = client.sent[0][-1]["content"]
    assert "Target role: Platform Eng" in sent
    assert "[e1b1] Built event-driven" in sent
    assert "<job_description>\nWe need Kafka and Kubernetes.\n</job_description>" in sent
    assert "ada@example.com" not in sent


# ---------- checks in code ----------


def test_unverified_bullets_flags_missing_or_unknown_sources() -> None:
    base = _profile()
    assert unverified_bullets(_tailored(["e1b2"]), base) == []
    flagged = unverified_bullets(_tailored([]), base)
    assert [b.text for b in flagged] == ["Kubernetes rollout"]
    assert len(unverified_bullets(_tailored(["e9b9"]), base)) == 1


def test_match_scores_are_a_ratio_over_keywords() -> None:
    assert match_scores(_tailored(["e1b2"])) == (50, 75)
    empty = _tailored(["e1b2"]).model_copy(update={"keywords": []})
    assert match_scores(empty) == (0, 0)


# ---------- storage ----------


def test_resume_round_trip_list_and_delete_are_per_user() -> None:
    engine = make_engine("sqlite://")
    alice, bob = Store(engine, "alice"), Store(engine, "bob")
    base = _base()
    alice.save_resume(base)
    assert alice.load_resume(base.id).profile.contact.email == "ada@example.com"
    assert [r.name for r in alice.list_resumes()] == ["Backend 2026"]
    assert bob.list_resumes() == []
    with pytest.raises(KeyError):
        bob.load_resume(base.id)
    bob.delete_resume(base.id)  # no effect on someone else's row
    assert len(alice.list_resumes()) == 1
    alice.delete_resume(base.id)
    assert alice.list_resumes() == []


def test_tailored_round_trip_keeps_snapshot_and_score() -> None:
    engine = make_engine("sqlite://")
    store = Store(engine, "alice")
    base = _base()
    doc = TailoredResumeDoc(
        base_resume_id=base.id,
        base_resume_name=base.name,
        base_profile=base.profile,
        job_title="Platform Engineer",
        company="Globex",
        jd_text="jd",
        result=_tailored(["e1b2"]),
    )
    store.save_tailored(doc)
    rows = store.list_tailored()
    assert rows[0].label == "Platform Engineer · Globex" and rows[0].match_score == 75
    loaded = store.load_tailored(doc.id)
    assert loaded.base_profile.education[0].degree == "BSc Mathematics"
    store.delete_tailored(doc.id)
    assert store.list_tailored() == []


# ---------- exports ----------


def test_exports_render_both_kinds() -> None:
    base = _base()
    doc = TailoredResumeDoc(
        base_resume_id=base.id,
        base_resume_name=base.name,
        base_profile=base.profile,
        job_title="Platform Engineer",
        jd_text="jd",
        result=_tailored(["e1b2"]),
    )
    md = to_markdown(view_of_tailored(doc))
    assert md.startswith("# Ada Lovelace\n**Senior Backend Engineer · Platform**")
    assert "BSc Mathematics" in md and "AWS Developer Associate" in md  # copied from the base
    assert "Kafka pipeline, 2M events/day" in md
    assert to_docx(view_of_base(base))[:2] == b"PK"
    assert to_pdf(view_of_tailored(doc)).startswith(b"%PDF")


def test_resume_input_kind_has_a_larger_cap() -> None:
    from interview_app.guard.input_guard import MAX_CHARS

    assert MAX_CHARS[InputKind.RESUME] > MAX_CHARS[InputKind.JOB_DESCRIPTION]
