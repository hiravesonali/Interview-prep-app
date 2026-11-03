from __future__ import annotations

from pathlib import Path

from interview_app.features import prompt_lab as lab
from interview_app.features.prompt_lab import SAMPLE_QUESTION, run_comparison
from interview_app.llm.client import StructuredOutputError, StructuredResult, Usage
from interview_app.llm.prompts import list_prompts, render_prompt
from interview_app.models import AnswerFeedback, DimensionScore
from interview_app.storage.prompt_lab import LabRecord, append_records, leaderboard, load_records


def _fb(overall: int) -> AnswerFeedback:
    return AnswerFeedback(
        scores=[
            DimensionScore(dimension=d, score=overall, comment="c")
            for d in ("correctness", "depth", "structure", "communication")
        ],
        overall=overall,
        strengths=["s"],
        gaps=["g"],
        model_answer="m",
        follow_up_question="f",
    )


def test_five_feedback_variants_exist_and_render() -> None:
    names = list_prompts("feedback")
    assert len(names) == 5
    for n in names:
        text = render_prompt(n, role="AI Engineer")
        assert "AI Engineer" in text and "{{" not in text


def test_run_comparison_collects_results_and_errors(monkeypatch) -> None:
    def fake(pipe, role, question, answer, *, technique, model=None):
        if technique.endswith("03_chain_of_thought"):
            raise StructuredOutputError("bad json")
        return StructuredResult(data=_fb(4), raw="{}", usage=Usage("m", 10, 5, 0.01, 1.0))

    monkeypatch.setattr(lab, "evaluate_answer_detailed", fake)
    results = run_comparison(
        None, "AI Engineer", SAMPLE_QUESTION, "answer", list_prompts("feedback")
    )
    assert [r.technique for r in results] == list_prompts("feedback")  # order preserved
    failed = [r for r in results if not r.ok]
    assert len(failed) == 1 and "invalid output" in failed[0].error


def test_store_roundtrip_and_leaderboard(tmp_path: Path) -> None:
    def rec(t, rating, cost):
        return LabRecord("2026-11-03T10:00:00", t, "m", "q", "a", 4, cost, 2.0, 100, rating)  # noqa: E731

    append_records(
        [rec("feedback/01_zero_shot", 3, 0.01), rec("feedback/02_few_shot", 5, 0.02)], tmp_path
    )
    append_records(
        [rec("feedback/01_zero_shot", 5, 0.03), rec("feedback/05_self_critique", None, 0.04)],
        tmp_path,
    )
    records = load_records(tmp_path)
    assert len(records) == 4
    rows = leaderboard(records)
    assert rows[0].technique == "feedback/02_few_shot" and rows[0].avg_rating == 5.0
    assert rows[1].technique == "feedback/01_zero_shot" and rows[1].avg_rating == 4.0
    assert rows[1].avg_cost_usd == 0.02 and rows[1].runs == 2
    assert rows[-1].technique == "feedback/05_self_critique" and rows[-1].avg_rating is None
