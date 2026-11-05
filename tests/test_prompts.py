from interview_app.llm.prompts import list_prompts, render_prompt


def test_render_substitutes_placeholders_only() -> None:
    text = render_prompt("question_generation", role="AI Engineer")
    assert "AI Engineer positions" in text
    assert "{{role}}" not in text
    assert '{"id": 1' in text  # JSON braces untouched


def test_feedback_variants_listed() -> None:
    names = list_prompts("feedback")
    assert "feedback/01_zero_shot" in names


def test_jd_prompt_days() -> None:
    assert "exactly 14 days" in render_prompt("jd_analysis", plan_days=14)


def test_question_wording_rules_present() -> None:
    # Both question-producing prompts carry the short, single-ask wording rule.
    for name, kwargs in (("question_generation", {"role": "x"}), ("jd_analysis", {"plan_days": 7})):
        assert "25 words or fewer" in render_prompt(name, **kwargs)
