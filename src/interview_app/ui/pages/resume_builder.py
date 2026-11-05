"""AI resume builder page: two tabs (tailored resumes, my resumes), each list → new → open.

Session state (set up in ui.state.init_state):
  rb_tab      "tailored" | "base"            which tab is shown
  rb_screen   None | ("new", None) | ("open", id)   list, the create form, or one item
  rb_draft    parsed-but-unsaved base resume (review step before saving)
  rb_prefill  {"jd_text", "job_title"} handed over by the JD analyzer
"""

from __future__ import annotations

import html
from datetime import datetime

import streamlit as st

from interview_app.features.resume import (
    SUPPORTED_EXTENSIONS,
    BaseResume,
    TailoredResumeDoc,
    UnsupportedFileError,
    extract_text,
    match_scores,
    parse_resume,
    tailor_resume,
    unverified_bullets,
)
from interview_app.features.resume_export import (
    ResumeView,
    to_docx,
    to_markdown,
    to_pdf,
    view_of_base,
    view_of_tailored,
)
from interview_app.guard import GuardBlocked
from interview_app.llm.client import StructuredOutputError
from interview_app.models import ResumeProfile, TailoredBullet
from interview_app.ui import state
from interview_app.ui.components import section_header, show_guard_block, step_header

_TABS = {"tailored": "✨ Tailored resumes", "base": "📚 My resumes"}
_KEYWORD_CHIP = {"present": "must", "added": "added", "missing": "missing"}
_KEYWORD_LABEL = {"present": "already there", "added": "now surfaced", "missing": "missing"}


def render() -> None:
    section_header(
        "AI <span>resume builder</span>",
        "Upload your resumes, then build a version tailored to any job. Every bullet stays "
        "traceable to what you actually wrote.",
    )
    tab = st.segmented_control(
        "Tab",
        list(_TABS),
        format_func=_TABS.__getitem__,
        default=st.session_state.rb_tab,
        key="rb_tab_control",
        label_visibility="collapsed",
    )
    if tab and tab != st.session_state.rb_tab:
        st.session_state.rb_tab = tab
        st.session_state.rb_screen = None
        st.rerun()
    screen = st.session_state.rb_screen
    if st.session_state.rb_tab == "base":
        _base_tab(screen)
    else:
        _tailored_tab(screen)


def _go(tab: str, screen: tuple[str, str | None] | None) -> None:
    st.session_state.rb_tab = tab
    st.session_state.rb_screen = screen
    st.rerun()


def _list_header(title: str, subtitle: str, button: str, key: str) -> bool:
    left, right = st.columns([3, 1.1], vertical_alignment="center")
    left.html(f'<div class="hoot-h2">{title}</div><p class="hoot-sub">{html.escape(subtitle)}</p>')
    return right.button(button, type="primary", key=key, width="stretch")


def _empty_state(icon: str, title: str, text: str, button: str, key: str) -> bool:
    with st.container(key="rb_empty"):
        st.html(
            f'<div class="hoot-empty"><div class="hoot-empty-icon">{icon}</div>'
            f"<h3>{html.escape(title)}</h3><p>{html.escape(text)}</p></div>"
        )
        _, mid, _ = st.columns([1, 1, 1])
        return mid.button(button, type="primary", key=key, width="stretch")


def _confirm_delete(key: str, what: str, label: str = "🗑️ Delete") -> bool:
    with st.popover(label, width="stretch", help="Delete"):
        st.caption(f"Delete {what}? This cannot be undone.")
        return st.button("Yes, delete", type="primary", key=f"{key}_confirm", width="stretch")


def _when(dt: datetime) -> str:
    return f"{dt:%d %b %Y}"


# =====================================================================================
# My resumes
# =====================================================================================


def _base_tab(screen: tuple[str, str | None] | None) -> None:
    if screen is None:
        _base_list()
    elif screen[0] == "new":
        _base_new()
    else:
        _base_open(screen[1] or "")


def _base_list() -> None:
    if _list_header(
        "📚 My resumes",
        "Your base resumes, parsed into sections. Tailored versions are built from these.",
        "＋ Upload a resume",
        "rb_base_add",
    ):
        _go("base", ("new", None))
    resumes = state.store().list_resumes()
    if not resumes:
        if _empty_state(
            "📄",
            "No resumes yet",
            "Upload a PDF or DOCX, or paste the text. It is parsed into sections you can review.",
            "＋ Upload a resume",
            "rb_base_add_empty",
        ):
            _go("base", ("new", None))
        return
    cols = st.columns(3, gap="medium")
    for i, r in enumerate(resumes):
        with cols[i % 3], st.container(key=f"rb_card_{r.id}"):
            st.html(
                f'<div class="hoot-kicker">Base resume · {_when(r.created_at)}</div>'
                f'<div class="hoot-card-title">{html.escape(r.name)}</div>'
                f'<p class="hoot-card-sub">{html.escape(r.headline)}</p>'
            )
            b1, b2, b3 = st.columns([1, 1.1, 0.8])
            if b1.button("View", key=f"rb_view_{r.id}", width="stretch"):
                _go("base", ("open", r.id))
            if b2.button("Tailor", key=f"rb_tailor_{r.id}", width="stretch", type="primary"):
                st.session_state.rb_prefill = {"base_id": r.id}
                _go("tailored", ("new", None))
            with b3:
                if _confirm_delete(f"rb_del_{r.id}", f"“{r.name}”", label="🗑️"):
                    state.store().delete_resume(r.id)
                    st.toast(f"Deleted “{r.name}”")
                    st.rerun()


def _base_new() -> None:
    draft: BaseResume | None = st.session_state.rb_draft
    if draft is not None:
        _base_review(draft)
        return
    with st.container(key="rb_new"):
        step_header(
            1,
            "Add your resume",
            "PDF, DOCX or TXT. Only the text is kept, the file is not stored.",
        )
        how = st.segmented_control(
            "How", ["Upload a file", "Paste text"], default="Upload a file", key="rb_how"
        )
        upload = text = None
        if how == "Paste text":
            text = st.text_area(
                "Resume text",
                height=260,
                max_chars=15000,
                placeholder="Paste the full text of your resume…",
                label_visibility="collapsed",
                key="rb_paste",
            )
        else:
            upload = st.file_uploader(
                "Resume file", type=list(SUPPORTED_EXTENSIONS), label_visibility="collapsed"
            )
            st.caption(
                "No file picker? Editor-embedded browsers (e.g. VS Code's Simple Browser) "
                "cannot open one: use Chrome or Safari at the same address, or paste the text."
            )
        step_header(2, "Name it", "So you can tell your base resumes apart.")
        name = st.text_input(
            "Name",
            placeholder='e.g. "Backend 2026" or "AI-focused"',
            max_chars=60,
            label_visibility="collapsed",
            key="rb_name",
        )
        c1, c2 = st.columns([1.2, 1])
        go = c1.button("Parse resume", type="primary", key="rb_parse", width="stretch")
        if c2.button("Cancel", key="rb_new_cancel", width="stretch"):
            _go("base", None)
        st.caption(
            "Email and phone numbers are removed before the text reaches the model; "
            "they are added back locally. Takes 20 to 40 seconds."
        )
    if not go:
        return
    try:
        if upload is not None:
            raw = extract_text(upload.name, upload.getvalue())
            source, filename = "upload", upload.name
        elif text and text.strip():
            raw, source, filename = text, "paste", ""
        else:
            st.warning("Upload a file or paste the text first.")
            return
    except UnsupportedFileError as err:
        st.error(str(err))
        return
    if len(raw.strip()) < 200:
        st.error("That looks too short to be a resume. Scanned PDFs have no text layer; paste it.")
        return
    fallback = filename.rsplit(".", 1)[0] if filename else f"Resume {_when(datetime.now())}"
    label = name.strip() or fallback
    try:
        with st.spinner("Parsing your resume… (20-40 s)"):
            result = parse_resume(state.pipeline(), raw, model=state.current_model())
    except GuardBlocked as err:
        show_guard_block(err)
        return
    except StructuredOutputError as err:
        st.error(f"The model did not return a valid profile. Try again. ({err})")
        return
    st.session_state.rb_draft = BaseResume(
        name=label,
        source=source,
        filename=filename,
        raw_text=raw,
        profile=result.data.model_dump(),  # dict for the same hot-reload reason as below
    )
    st.toast(f"Parsed · {result.usage.total_tokens:,} tokens · ${result.usage.cost_usd:.4f}")
    st.rerun()


def _base_review(draft: BaseResume) -> None:
    p = draft.profile
    with st.container(key="rb_result"):
        st.html(
            '<div class="hoot-kicker">Review before saving</div>'
            f"<h3>{html.escape(draft.name)}</h3>"
            f"<p>{html.escape(p.headline)}</p>"
        )
        _profile_stats(p)
        c1, c2 = st.columns([1.2, 1])
        if c1.button("Save resume", type="primary", key="rb_save", width="stretch"):
            state.store().save_resume(draft)
            st.session_state.rb_draft = None
            st.toast(f"Saved “{draft.name}”")
            _go("base", ("open", draft.id))
        if c2.button("Discard", key="rb_discard", width="stretch"):
            st.session_state.rb_draft = None
            _go("base", ("new", None))
    st.caption("Check the sections below. If something was missed, discard and paste the text.")
    _render_preview(view_of_base(draft), key="rb_preview")


def _base_open(resume_id: str) -> None:
    try:
        resume = state.store().load_resume(resume_id)
    except KeyError:
        st.warning("That resume no longer exists.")
        _go("base", None)
        return
    p = resume.profile
    with st.container(key="rb_result"):
        st.html(
            f'<div class="hoot-kicker">Base resume · added {_when(resume.created_at)}</div>'
            f"<h3>{html.escape(resume.name)}</h3><p>{html.escape(p.headline)}</p>"
        )
        _profile_stats(p)
        b1, b2, b3 = st.columns([1.4, 1, 1])
        if b1.button("✨ Tailor for a job", type="primary", key="rb_open_tailor", width="stretch"):
            st.session_state.rb_prefill = {"base_id": resume.id}
            _go("tailored", ("new", None))
        if b2.button("← All resumes", key="rb_open_back", width="stretch"):
            _go("base", None)
        with b3:
            if _confirm_delete("rb_open_del", f"“{resume.name}”"):
                state.store().delete_resume(resume.id)
                st.toast(f"Deleted “{resume.name}”")
                _go("base", None)
        _downloads(view_of_base(resume), stem=resume.name, key="rb_base_dl")
    _render_preview(view_of_base(resume), key="rb_preview")


def _profile_stats(p: ResumeProfile) -> None:
    stats = [
        (len(p.experience), "roles"),
        (sum(len(e.bullets) for e in p.experience), "bullets"),
        (len(p.projects), "projects"),
        (sum(len(s.skills) for s in p.skills), "skills"),
    ]
    for col, (n, label) in zip(st.columns(4), stats, strict=True):
        col.html(f'<div class="hoot-stat"><b>{n}</b><span>{label}</span></div>')


# =====================================================================================
# Tailored resumes
# =====================================================================================


def _tailored_tab(screen: tuple[str, str | None] | None) -> None:
    if screen is None:
        _tailored_list()
    elif screen[0] == "new":
        _tailored_new()
    else:
        _tailored_open(screen[1] or "")


def _tailored_list() -> None:
    if _list_header(
        "✨ Tailored resumes",
        "One resume per job application, built from your base resumes.",
        "＋ Tailor for a new job",
        "rb_t_add",
    ):
        _go("tailored", ("new", None))
    docs = state.store().list_tailored()
    if not docs:
        if _empty_state(
            "✨",
            "No tailored resumes yet",
            "Pick a base resume, paste the job description, and get a version aimed at that job.",
            "＋ Tailor for a new job",
            "rb_t_add_empty",
        ):
            _go("tailored", ("new", None))
        return
    cols = st.columns(3, gap="medium")
    for i, d in enumerate(docs):
        with cols[i % 3], st.container(key=f"rb_card_{d.id}"):
            st.html(
                f'<div class="hoot-kicker">Tailored · {_when(d.created_at)}</div>'
                f'<div class="hoot-card-title">{html.escape(d.label)}</div>'
                '<p class="hoot-card-sub">'
                f'<span class="hoot-score">{d.match_score}% match</span></p>'
            )
            b1, b2 = st.columns([2, 0.8])
            if b1.button("Open", key=f"rb_t_open_{d.id}", width="stretch", type="primary"):
                _go("tailored", ("open", d.id))
            with b2:
                if _confirm_delete(f"rb_t_del_{d.id}", f"the resume for “{d.label}”", label="🗑️"):
                    state.store().delete_tailored(d.id)
                    st.toast("Deleted")
                    st.rerun()


def _tailored_new() -> None:
    resumes = state.store().list_resumes()
    prefill = st.session_state.rb_prefill or {}
    with st.container(key="rb_new"):
        step_header(1, "Pick a base resume", "The tailored version is built only from this.")
        if not resumes:
            st.info("Upload a base resume first.")
            if st.button("＋ Upload a resume", type="primary", key="rb_t_need_base"):
                _go("base", ("new", None))
            return
        ids = [r.id for r in resumes]
        default = prefill.get("base_id") if prefill.get("base_id") in ids else ids[0]
        base_id = st.selectbox(
            "Base resume",
            ids,
            index=ids.index(default),
            format_func=lambda i: next(f"{r.name} · {r.headline}" for r in resumes if r.id == i),
            label_visibility="collapsed",
            key="rb_t_base",
        )
        step_header(2, "Paste the job description", "The same text the JD analyzer takes.")
        jd_text = st.text_area(
            "Job description",
            value=prefill.get("jd_text") or st.session_state.get("jd_last_text", ""),
            height=220,
            max_chars=12000,
            label_visibility="collapsed",
            key="rb_t_jd",
        )
        step_header(3, "Job details (optional)")
        c1, c2 = st.columns(2)
        job_title = c1.text_input(
            "Job title", value=prefill.get("job_title", ""), max_chars=120, key="rb_t_title"
        )
        company = c2.text_input("Company", max_chars=120, key="rb_t_company")
        c1, c2 = st.columns([1.2, 1])
        go = c1.button("Tailor my resume", type="primary", key="rb_t_go", width="stretch")
        if c2.button("Cancel", key="rb_t_cancel", width="stretch"):
            st.session_state.rb_prefill = None
            _go("tailored", None)
        st.caption(
            "Nothing is invented: bullets without a source in your resume are flagged. 30-60 s."
        )
    if not go:
        return
    if not jd_text.strip():
        st.warning("Paste a job description first.")
        return
    base = state.store().load_resume(base_id)
    try:
        with st.spinner("Tailoring your resume… (30-60 s)"):
            result = tailor_resume(
                state.pipeline(),
                base,
                jd_text,
                job_title=job_title,
                company=company,
                model=state.current_model(),
            )
    except GuardBlocked as err:
        show_guard_block(err)
        return
    except StructuredOutputError as err:
        st.error(f"The model did not return a valid resume. Try again. ({err})")
        return
    # Dumped to a dict on purpose: Streamlit's hot reload can re-import `features.resume`
    # and leave two `ResumeProfile` classes alive; a dict validates into whichever is current.
    doc = TailoredResumeDoc(
        base_resume_id=base.id,
        base_resume_name=base.name,
        base_profile=base.profile.model_dump(),
        job_title=job_title.strip() or result.data.headline,
        company=company.strip(),
        jd_text=jd_text,
        result=result.data,
    )
    state.store().save_tailored(doc)
    st.session_state.rb_prefill = None
    st.toast(f"Done · {result.usage.total_tokens:,} tokens · ${result.usage.cost_usd:.4f}")
    _go("tailored", ("open", doc.id))


def _tailored_open(doc_id: str) -> None:
    try:
        doc = state.store().load_tailored(doc_id)
    except KeyError:
        st.warning("That tailored resume no longer exists.")
        _go("tailored", None)
        return
    r = doc.result
    before, after = match_scores(r)
    flagged = unverified_bullets(r, doc.base_profile)
    with st.container(key="rb_result"):
        st.html(
            '<div class="hoot-kicker">Tailored resume · from '
            f"“{html.escape(doc.base_resume_name)}” · {_when(doc.created_at)}</div>"
            f"<h3>{html.escape(doc.label)}</h3>"
            f"<p>{html.escape(r.changes_summary)}</p>"
        )
        stats = [
            (f"{before}% → {after}%", "keyword match"),
            (sum(k.status != "missing" for k in r.keywords), f"of {len(r.keywords)} keywords"),
            (len(r.gaps), "gaps to address"),
            (len(flagged), "bullets to verify"),
        ]
        for col, (n, label) in zip(st.columns(4), stats, strict=True):
            col.html(f'<div class="hoot-stat"><b>{n}</b><span>{label}</span></div>')
        b1, b2, b3 = st.columns([1.6, 1, 1])
        if b1.button(
            "🗣️ Prepare for this interview", type="primary", key="rb_t_prep", width="stretch"
        ):
            st.session_state.jd_last_text = doc.jd_text
            st.session_state.jd_analysis = None
            st.switch_page(st.session_state.pages["jd"])
        if b2.button("← All tailored", key="rb_t_back", width="stretch"):
            _go("tailored", None)
        with b3:
            if _confirm_delete("rb_t_open_del", f"the resume for “{doc.label}”"):
                state.store().delete_tailored(doc.id)
                st.toast("Deleted")
                _go("tailored", None)
        _downloads(view_of_tailored(doc), stem=doc.label, key="rb_t_dl")
    if flagged:
        st.warning(
            f"{len(flagged)} bullet(s) have no source in your base resume. They are marked "
            "“verify” in the preview: keep them only if they are true."
        )
    tab_preview, tab_changes, tab_keywords = st.tabs(
        ["Preview", "What changed", f"Keywords & gaps ({len(r.gaps)})"]
    )
    with tab_preview:
        _render_preview(view_of_tailored(doc), key="rb_preview", flagged={b.text for b in flagged})
    with tab_changes:
        _render_changes(doc, flagged)
    with tab_keywords:
        _render_keywords(doc)


# ---------- shared renderers ----------


def _downloads(view: ResumeView, *, stem: str, key: str) -> None:
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in stem).strip() or "resume"
    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "⬇ Word (.docx)",
        to_docx(view),
        file_name=f"{safe}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=f"{key}_docx",
        width="stretch",
    )
    c2.download_button(
        "⬇ PDF",
        to_pdf(view),
        file_name=f"{safe}.pdf",
        mime="application/pdf",
        key=f"{key}_pdf",
        width="stretch",
    )
    c3.download_button(
        "⬇ Markdown",
        to_markdown(view),
        file_name=f"{safe}.md",
        mime="text/markdown",
        key=f"{key}_md",
        width="stretch",
    )


def _render_preview(view: ResumeView, *, key: str, flagged: set[str] | None = None) -> None:
    flagged = flagged or set()
    e = html.escape

    def bullets(items: tuple[str, ...]) -> str:
        return (
            "<ul>"
            + "".join(
                f"<li>{e(b)}{' <span class=hoot-verify>verify</span>' if b in flagged else ''}</li>"
                for b in items
            )
            + "</ul>"
        )

    c = view.contact
    contact = " · ".join(e(x) for x in (c.location, c.email, c.phone, *c.links) if x)
    parts = [
        f"<h1>{e(c.name or 'Your name')}</h1>",
        f'<div class="headline">{e(view.headline)}</div>',
        f'<div class="contact">{contact}</div>' if contact else "",
    ]
    if view.summary:
        parts += ["<h2>Summary</h2>", f"<p>{e(view.summary)}</p>"]
    for title, entries in (("Experience", view.experience), ("Projects", view.projects)):
        if not entries:
            continue
        parts.append(f"<h2>{title}</h2>")
        for entry in entries:
            parts.append(f'<div class="entry"><b>{e(entry.heading)}</b>')
            if entry.meta:
                parts.append(f'<div class="meta">{e(entry.meta)}</div>')
            if entry.description:
                parts.append(f"<p>{e(entry.description)}</p>")
            parts.append(bullets(entry.bullets) + "</div>")
    if view.skills:
        parts.append("<h2>Skills</h2><ul>")
        parts += [f"<li><b>{e(s.name)}:</b> {e(', '.join(s.skills))}</li>" for s in view.skills]
        parts.append("</ul>")
    if view.education:
        parts.append("<h2>Education</h2><ul>")
        for ed in view.education:
            tail = " · ".join(x for x in (ed.dates, ed.details) if x)
            extra = f" ({e(tail)})" if tail else ""
            parts.append(f"<li><b>{e(ed.degree)}</b>, {e(ed.institution)}{extra}</li>")
        parts.append("</ul>")
    if view.certifications:
        parts.append("<h2>Certifications</h2>" + bullets(view.certifications))
    with st.container(key=key):
        st.html('<div class="hoot-cv">' + "".join(parts) + "</div>")


def _render_changes(doc: TailoredResumeDoc, flagged: list[TailoredBullet]) -> None:
    source = {
        b.id: b.text
        for group in (doc.base_profile.experience, doc.base_profile.projects)
        for entry in group
        for b in entry.bullets
    }
    flagged_texts = {b.text for b in flagged}
    st.caption("Each tailored bullet with the base-resume bullets it was built from.")
    sections = [(f"{x.title}, {x.organisation}", x.bullets) for x in doc.result.experience]
    sections += [(x.name, x.bullets) for x in doc.result.projects]
    for i, (heading, bullets) in enumerate(sections):
        with st.container(key=f"rb_change_{i}"):
            st.html(f'<div class="hoot-card-title">{html.escape(heading)}</div>')
            for b in bullets:
                origin = " / ".join(html.escape(source.get(s, s)) for s in b.source_ids)
                if b.text in flagged_texts:
                    tag = '<span class="hoot-verify">verify · no source</span>'
                elif b.reason:
                    tag = f'<span class="hoot-reason">{html.escape(b.reason)}</span>'
                else:
                    tag = '<span class="hoot-reason kept">unchanged</span>'
                from_line = f'<div class="old">from: {origin}</div>' if origin and b.reason else ""
                st.html(
                    f'<div class="hoot-diff"><div class="new">{html.escape(b.text)}</div>'
                    f"{from_line}{tag}</div>"
                )


def _render_keywords(doc: TailoredResumeDoc) -> None:
    r = doc.result
    st.html(
        '<div class="hoot-legend"><span class="hoot-chip must">already there</span>'
        '<span class="hoot-chip added">now surfaced</span>'
        '<span class="hoot-chip missing">missing</span></div>'
    )
    chips = "".join(
        f'<span class="hoot-chip {_KEYWORD_CHIP[k.status]}" title="{html.escape(k.note)}">'
        f"{html.escape(k.keyword)}</span>"
        for k in r.keywords
    )
    st.html(f'<div class="hoot-chips">{chips}</div>')
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(key="rb_gaps"):
        items = (
            "".join(f"<li>{html.escape(g)}</li>" for g in r.gaps)
            or '<li class="hoot-muted">Nothing missing for this job.</li>'
        )
        st.html(f'<div class="hoot-card-title">🧭 Gaps to address</div><ul>{items}</ul>')
    with c2, st.container(key="rb_notes"):
        notes = [k for k in r.keywords if k.note]
        items = (
            "".join(
                f"<li><b>{html.escape(k.keyword)}</b> <small>{_KEYWORD_LABEL[k.status]}</small>"
                f"<br>{html.escape(k.note)}</li>"
                for k in notes
            )
            or '<li class="hoot-muted">No notes.</li>'
        )
        st.html(f'<div class="hoot-card-title">📝 Where each keyword lands</div><ul>{items}</ul>')
