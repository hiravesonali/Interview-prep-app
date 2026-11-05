"""Feature 3: AI resume builder — parse a base resume, tailor it to a job description.

Two structured calls, both through the GuardPipeline:
  parse_resume   raw text → ResumeProfile (sections, nothing invented)
  tailor_resume  profile + JD → TailoredResume (bullets with source ids, keywords, gaps)

Three rules are enforced here, in code, rather than left to the prompt:
  * contact details are extracted locally with regexes and never sent to the model (the input
    guard redacts emails and phones before the parser sees the text);
  * every tailored bullet must trace back to base-resume bullet ids, else it is flagged;
  * the match score is a ratio over the model's keyword list, not a number the model reports.
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from interview_app.guard import GuardPipeline, InputKind
from interview_app.llm.client import StructuredResult
from interview_app.llm.prompts import load_prompt
from interview_app.models import (
    ContactInfo,
    ParsedResume,
    ResumeProfile,
    TailoredBullet,
    TailoredResume,
)

SUPPORTED_EXTENSIONS = ("pdf", "docx", "txt", "md")


class BaseResume(BaseModel):
    """An uploaded (or pasted) resume with its parsed profile; one row in `resumes`."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = Field(description="Label chosen by the user, e.g. 'Backend 2026'")
    source: Literal["upload", "paste"] = "paste"
    filename: str = ""
    raw_text: str
    profile: ResumeProfile
    created_at: datetime = Field(default_factory=datetime.now)


class TailoredResumeDoc(BaseModel):
    """One tailored resume per job application; one row in `tailored_resumes`.

    `base_profile` is a snapshot so the document still renders if the base resume is deleted.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    base_resume_id: str
    base_resume_name: str
    base_profile: ResumeProfile
    job_title: str
    company: str = ""
    jd_text: str
    result: TailoredResume
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def label(self) -> str:
        return f"{self.job_title} · {self.company}" if self.company else self.job_title


# ---------- text extraction (local, no model) ----------


class UnsupportedFileError(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    """Plain text of an uploaded PDF, DOCX or text file. Layout is not preserved."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif ext == "docx":
        from docx import Document

        document = Document(io.BytesIO(data))
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        text = "\n".join(parts)
    elif ext in ("txt", "md"):
        text = data.decode("utf-8", errors="replace")
    else:
        raise UnsupportedFileError(
            f"Unsupported file type '.{ext}'. Upload a PDF, DOCX or TXT file, or paste the text."
        )
    return _clean(text)


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<![\w/])\+?\(?\d[\d\s().\-]{7,}\d(?![\w/])")
_LINK = re.compile(
    r"(?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com|gitlab\.com|[\w-]+\.(?:dev|io|me))"
    r"/[\w./-]*[\w/]",
    re.IGNORECASE,
)


def extract_contact(raw_text: str) -> ContactInfo:
    """Email, phone and profile links from the raw text. Runs locally; nothing is sent."""
    head = raw_text[:1500]  # contact blocks sit at the top; avoids matching dates in bullets
    email = _EMAIL.search(head)
    phones = (m.group(0).strip() for m in _PHONE.finditer(head))
    phone = next((x for x in phones if len(re.sub(r"\D", "", x)) >= 9), "")
    links = []
    for m in _LINK.finditer(raw_text):
        link = m.group(0).rstrip(".,)")
        if link.lower() not in (x.lower() for x in links):
            links.append(link)
    return ContactInfo(email=email.group(0) if email else "", phone=phone, links=links[:4])


# ---------- bullet ids and the profile as prompt text ----------


def assign_bullet_ids(profile: ParsedResume) -> None:
    """`e<role><bullet>` for experience, `p<project><bullet>` for projects, e.g. e1b2, p2b1."""
    for i, entry in enumerate(profile.experience, 1):
        for j, b in enumerate(entry.bullets, 1):
            b.id = f"e{i}b{j}"
    for i, project in enumerate(profile.projects, 1):
        for j, b in enumerate(project.bullets, 1):
            b.id = f"p{i}b{j}"


def bullet_ids(profile: ParsedResume) -> set[str]:
    return {
        b.id
        for group in (profile.experience, profile.projects)
        for entry in group
        for b in entry.bullets
    }


def profile_to_text(profile: ResumeProfile) -> str:
    """The base resume as the tailoring prompt sees it: sections, bullets tagged with ids."""
    lines = [f"Headline: {profile.headline}"]
    if profile.summary:
        lines += ["", "Summary:", profile.summary]
    lines += ["", "Experience:"]
    for entry in profile.experience:
        where = f" ({entry.location})" if entry.location else ""
        lines.append(f"- {entry.title}, {entry.organisation}{where}, {entry.dates}")
        lines += [f"  [{b.id}] {b.text}" for b in entry.bullets]
    if profile.projects:
        lines += ["", "Projects:"]
        for project in profile.projects:
            tech = f" ({', '.join(project.technologies)})" if project.technologies else ""
            desc = f": {project.description}" if project.description else ""
            lines.append(f"- {project.name}{tech}{desc}")
            lines += [f"  [{b.id}] {b.text}" for b in project.bullets]
    lines += ["", "Skills:"]
    lines += [f"- {cat.name}: {', '.join(cat.skills)}" for cat in profile.skills]
    if profile.education:
        lines += ["", "Education:"]
        lines += [
            f"- {e.degree}, {e.institution}, {e.dates}".rstrip(", ") for e in profile.education
        ]
    if profile.certifications:
        lines += ["", "Certifications: " + "; ".join(profile.certifications)]
    return "\n".join(lines)


# ---------- the two model calls ----------


def parse_resume(
    pipe: GuardPipeline, raw_text: str, *, model: str | None = None
) -> StructuredResult[ResumeProfile]:
    """Resume text → profile. The guard redacts email/phone; `extract_contact` restores them."""
    result = pipe.structured(
        load_prompt("resume_parse"),
        raw_text,
        InputKind.RESUME,
        ParsedResume,
        user_template="<resume>\n{input}\n</resume>",
        model=model,
        max_tokens=8000,
        purpose="resume_parse",
    )
    profile = build_profile(result.data, raw_text)
    return StructuredResult(data=profile, raw=result.raw, usage=result.usage)


def build_profile(parsed: ParsedResume, raw_text: str) -> ResumeProfile:
    """Parser output + locally extracted contact details, bullets numbered."""
    assign_bullet_ids(parsed)
    local = extract_contact(raw_text)
    contact = local.model_copy(update={"name": parsed.name, "location": parsed.location})
    return ResumeProfile(**parsed.model_dump(), contact=contact)


_TAILOR_TEMPLATE = """Target role: {job_title}
Company: {company}

<base_resume>
{resume}
</base_resume>

<job_description>
{input}
</job_description>"""


def tailor_resume(
    pipe: GuardPipeline,
    base: BaseResume,
    jd_text: str,
    *,
    job_title: str = "",
    company: str = "",
    model: str | None = None,
) -> StructuredResult[TailoredResume]:
    """Profile + JD → tailored resume. Both texts pass the input guard; the JD is `{input}`."""
    title = pipe.check_input(job_title, InputKind.TITLE).text if job_title.strip() else ""
    org = pipe.check_input(company, InputKind.TITLE).text if company.strip() else ""
    resume_text = pipe.check_input(profile_to_text(base.profile), InputKind.RESUME).text
    template = (
        _TAILOR_TEMPLATE.replace("{job_title}", title or "(not given, infer from the JD)")
        .replace("{company}", org or "(not given)")
        .replace("{resume}", resume_text)
    )
    return pipe.structured(
        load_prompt("resume_tailor"),
        jd_text,
        InputKind.JOB_DESCRIPTION,
        TailoredResume,
        user_template=template,
        model=model,
        max_tokens=10000,
        purpose="resume_tailor",
    )


# ---------- checks computed in code ----------


def unverified_bullets(result: TailoredResume, base: ResumeProfile) -> list[TailoredBullet]:
    """Bullets with no source id, or with an id the base resume does not have: new claims."""
    known = bullet_ids(base)
    return [
        b
        for group in (result.experience, result.projects)
        for entry in group
        for b in entry.bullets
        if not b.source_ids or any(s not in known for s in b.source_ids)
    ]


def match_scores(result: TailoredResume) -> tuple[int, int]:
    """(before, after) as percentages of JD keywords covered; (0, 0) if the list is empty."""
    total = len(result.keywords)
    if not total:
        return 0, 0
    present = sum(k.status == "present" for k in result.keywords)
    added = sum(k.status == "added" for k in result.keywords)
    return round(100 * present / total), round(100 * (present + added) / total)
