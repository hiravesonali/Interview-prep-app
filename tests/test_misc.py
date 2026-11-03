from interview_app.llm.prompts import load_prompt
from interview_app.models import JobAnalysis, QuestionSet
from interview_app.roles import find_role, load_roles


def test_guard_prompt_loads() -> None:
    assert "classif" in load_prompt("guard_classifier").lower()


def test_roles_load() -> None:
    roles = load_roles()
    assert len(roles) >= 6
    assert find_role("AI Engineer") is not None


def test_schemas_export_json_schema() -> None:
    for model in (QuestionSet, JobAnalysis):
        schema = model.model_json_schema()
        assert schema["type"] == "object"
