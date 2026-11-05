"""Export a resume (base profile or tailored document) as Markdown, .docx or PDF.

Both kinds are first flattened into a `ResumeView` so the three writers share one shape.
Layout is deliberately plain (one column, standard fonts): ATS parsers read it reliably.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from interview_app.features.resume import BaseResume, TailoredResumeDoc
from interview_app.models import ContactInfo, EducationEntry, SkillCategory


@dataclass(frozen=True)
class ViewEntry:
    heading: str  # "Senior Backend Engineer, Acme"
    meta: str  # "Mar 2021 - present · Berlin"  or technologies for a project
    description: str = ""
    bullets: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResumeView:
    contact: ContactInfo
    headline: str
    summary: str
    experience: tuple[ViewEntry, ...]
    projects: tuple[ViewEntry, ...]
    skills: tuple[SkillCategory, ...]
    education: tuple[EducationEntry, ...]
    certifications: tuple[str, ...] = field(default_factory=tuple)


def view_of_base(resume: BaseResume) -> ResumeView:
    p = resume.profile
    return ResumeView(
        contact=p.contact,
        headline=p.headline,
        summary=p.summary,
        experience=tuple(
            ViewEntry(
                f"{e.title}, {e.organisation}",
                _meta(e.dates, e.location),
                bullets=tuple(b.text for b in e.bullets),
            )
            for e in p.experience
        ),
        projects=tuple(
            ViewEntry(
                pr.name,
                ", ".join(pr.technologies),
                pr.description,
                tuple(b.text for b in pr.bullets),
            )
            for pr in p.projects
        ),
        skills=tuple(p.skills),
        education=tuple(p.education),
        certifications=tuple(p.certifications),
    )


def view_of_tailored(doc: TailoredResumeDoc) -> ResumeView:
    r, base = doc.result, doc.base_profile
    return ResumeView(
        contact=base.contact,
        headline=r.headline,
        summary=r.summary,
        experience=tuple(
            ViewEntry(
                f"{e.title}, {e.organisation}",
                _meta(e.dates, e.location),
                bullets=tuple(b.text for b in e.bullets),
            )
            for e in r.experience
        ),
        projects=tuple(
            ViewEntry(
                pr.name,
                ", ".join(pr.technologies),
                pr.description,
                tuple(b.text for b in pr.bullets),
            )
            for pr in r.projects
        ),
        skills=tuple(r.skills),
        education=tuple(base.education),
        certifications=tuple(base.certifications),
    )


def _meta(dates: str, location: str) -> str:
    return " · ".join(x for x in (dates, location) if x)


def _contact_line(c: ContactInfo) -> str:
    return " · ".join(x for x in (c.location, c.email, c.phone, *c.links) if x)


# ---------- Markdown ----------


def to_markdown(view: ResumeView) -> str:
    out = [f"# {view.contact.name or 'Resume'}", f"**{view.headline}**"]
    if line := _contact_line(view.contact):
        out.append(line)
    if view.summary:
        out += ["", "## Summary", view.summary]
    if view.experience:
        out += ["", "## Experience"]
        for e in view.experience:
            out += ["", f"### {e.heading}", f"*{e.meta}*"]
            out += [f"- {b}" for b in e.bullets]
    if view.projects:
        out += ["", "## Projects"]
        for p in view.projects:
            out += ["", f"### {p.heading}", f"*{p.meta}*"] if p.meta else ["", f"### {p.heading}"]
            if p.description:
                out.append(p.description)
            out += [f"- {b}" for b in p.bullets]
    if view.skills:
        out += ["", "## Skills"]
        out += [f"- **{s.name}:** {', '.join(s.skills)}" for s in view.skills]
    if view.education:
        out += ["", "## Education"]
        for ed in view.education:
            tail = " · ".join(x for x in (ed.dates, ed.details) if x)
            out.append(f"- **{ed.degree}**, {ed.institution}" + (f" ({tail})" if tail else ""))
    if view.certifications:
        out += ["", "## Certifications"]
        out += [f"- {c}" for c in view.certifications]
    return "\n".join(out).strip() + "\n"


# ---------- .docx ----------


def to_docx(view: ResumeView) -> bytes:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Pt(50)
        section.left_margin = section.right_margin = Pt(54)

    doc.add_heading(view.contact.name or "Resume", level=0)
    doc.add_paragraph().add_run(view.headline).bold = True
    if line := _contact_line(view.contact):
        doc.add_paragraph(line)
    if view.summary:
        doc.add_heading("Summary", level=1)
        doc.add_paragraph(view.summary)
    for title, entries in (("Experience", view.experience), ("Projects", view.projects)):
        if not entries:
            continue
        doc.add_heading(title, level=1)
        for e in entries:
            doc.add_paragraph().add_run(e.heading).bold = True
            if e.meta:
                doc.add_paragraph().add_run(e.meta).italic = True
            if e.description:
                doc.add_paragraph(e.description)
            for b in e.bullets:
                doc.add_paragraph(b, style="List Bullet")
    if view.skills:
        doc.add_heading("Skills", level=1)
        for s in view.skills:
            p = doc.add_paragraph()
            p.add_run(f"{s.name}: ").bold = True
            p.add_run(", ".join(s.skills))
    if view.education:
        doc.add_heading("Education", level=1)
        for ed in view.education:
            p = doc.add_paragraph()
            p.add_run(ed.degree).bold = True
            p.add_run(f", {ed.institution}" + (f" · {ed.dates}" if ed.dates else ""))
            if ed.details:
                doc.add_paragraph(ed.details)
    if view.certifications:
        doc.add_heading("Certifications", level=1)
        for c in view.certifications:
            doc.add_paragraph(c, style="List Bullet")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------- PDF ----------


def to_pdf(view: ResumeView) -> bytes:
    from xml.sax.saxutils import escape

    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    base = getSampleStyleSheet()
    normal, grey, purple = base["Normal"], "#555555", "#5B3FA0"
    styles = {
        "name": ParagraphStyle(
            "name", parent=base["Title"], fontSize=20, leading=24, alignment=TA_LEFT, spaceAfter=2
        ),
        "headline": ParagraphStyle(
            "headline", parent=normal, fontName="Helvetica-Bold", fontSize=11.5, leading=14
        ),
        "contact": ParagraphStyle(
            "contact", parent=normal, fontSize=9, leading=12, textColor=grey, spaceAfter=8
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading2"],
            fontSize=12.5,
            leading=15,
            spaceBefore=10,
            spaceAfter=4,
            textColor=purple,
        ),
        "entry": ParagraphStyle(
            "entry",
            parent=normal,
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            spaceBefore=5,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=normal,
            fontName="Helvetica-Oblique",
            fontSize=9.5,
            leading=12,
            textColor=grey,
        ),
        "body": ParagraphStyle("body", parent=normal, fontSize=10, leading=13.5),
    }

    def p(text: str, style: str) -> Paragraph:
        return Paragraph(escape(text), styles[style])

    def bullets(items: tuple[str, ...]) -> ListFlowable:
        return ListFlowable(
            [ListItem(p(b, "body"), leftIndent=12) for b in items],
            bulletType="bullet",
            start="•",
            leftIndent=12,
            bulletFontSize=8,
        )

    story: list = [p(view.contact.name or "Resume", "name"), p(view.headline, "headline")]
    if line := _contact_line(view.contact):
        story.append(p(line, "contact"))
    if view.summary:
        story += [p("Summary", "h1"), p(view.summary, "body")]
    for title, entries in (("Experience", view.experience), ("Projects", view.projects)):
        if not entries:
            continue
        story.append(p(title, "h1"))
        for e in entries:
            story.append(p(e.heading, "entry"))
            if e.meta:
                story.append(p(e.meta, "meta"))
            if e.description:
                story.append(p(e.description, "body"))
            if e.bullets:
                story.append(bullets(e.bullets))
    if view.skills:
        story.append(p("Skills", "h1"))
        for s in view.skills:
            line = f"<b>{escape(s.name)}:</b> {escape(', '.join(s.skills))}"
            story.append(Paragraph(line, styles["body"]))
    if view.education:
        story.append(p("Education", "h1"))
        for ed in view.education:
            tail = f" · {ed.dates}" if ed.dates else ""
            line = f"<b>{escape(ed.degree)}</b>, {escape(ed.institution)}{escape(tail)}"
            story.append(Paragraph(line, styles["body"]))
            if ed.details:
                story.append(p(ed.details, "meta"))
    if view.certifications:
        story += [p("Certifications", "h1"), bullets(view.certifications)]
    story.append(Spacer(1, 4 * mm))

    buf = io.BytesIO()
    SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"{view.contact.name} - {view.headline}".strip(" -"),
        author=view.contact.name,
    ).build(story)
    return buf.getvalue()
