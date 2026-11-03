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
