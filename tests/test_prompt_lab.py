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


def test_judge_results_attaches_verdicts_and_errors(monkeypatch) -> None:
    from interview_app.features.prompt_lab import LabResult, judge_results
    from interview_app.models import JudgeVerdict

    verdict = JudgeVerdict(
        accuracy=4, specificity=3, actionability=5, calibration=4, overall=4, rationale="r"
    )

    def fake_judge(pipe, role, question, answer, feedback, *, model=None):
        if feedback.overall == 2:
            raise StructuredOutputError("bad json")
        return verdict, Usage(model or "m", 10, 5, 0.01, 1.0)

    monkeypatch.setattr(lab, "judge_feedback", fake_judge)
    usage = Usage("m", 1, 1, 0.0, 0.1)
    results = [
        LabResult("feedback/01_zero_shot", _fb(4), usage),
        LabResult("feedback/02_few_shot", _fb(2), usage),
        LabResult("feedback/03_chain_of_thought", None, None, "blocked"),
    ]
    judged = judge_results(None, "AI Engineer", SAMPLE_QUESTION, "a", results, model="judge-m")
    assert judged[0].judge == verdict and judged[0].judge_usage.model == "judge-m"
    assert judged[1].judge is None and "invalid output" in judged[1].judge_error
    assert judged[2].judge is None and judged[2].judge_error is None  # never judged
    assert judged[0].feedback is results[0].feedback  # original result untouched


def test_judge_prompt_renders_and_feedback_goes_in_template() -> None:
    from interview_app.config import Settings
    from interview_app.features.prompt_lab import judge_feedback
    from interview_app.guard import GuardPipeline, SecurityLog
    from interview_app.llm.client import OpenRouterClient
    from interview_app.models import JudgeVerdict

    class FakeClient(OpenRouterClient):
        def __init__(self):
            super().__init__(Settings(openrouter_api_key="t"))
            self.sent = None

        def chat_structured(self, messages, schema, **kw):  # type: ignore[override]
            self.sent = messages
            data = JudgeVerdict(
                accuracy=5, specificity=5, actionability=5, calibration=5, overall=5, rationale="r"
            )
            return StructuredResult(data=data, raw="{}", usage=Usage("m", 1, 1, 0.0, 0.1))

    client = FakeClient()
    pipe = GuardPipeline(client, client.settings, SecurityLog(), llm_guard_enabled=False)
    verdict, _ = judge_feedback(pipe, "AI Engineer", SAMPLE_QUESTION, "my answer", _fb(3))
    assert verdict.overall == 5
    system, user = client.sent[0]["content"], client.sent[-1]["content"]
    assert "AI Engineer" in system and "{{" not in system
    assert "<candidate_answer>\nmy answer\n</candidate_answer>" in user
    assert '"overall": 3' in user  # the feedback JSON is embedded in the template


def test_leaderboard_includes_judge_average(tmp_path: Path) -> None:
    def rec(t, rating, judge):
        return LabRecord(
            "2026-11-03T10:00:00", t, "m", "q", "a", 4, 0.01, 2.0, 100, rating, "", judge, "j"
        )

    append_records(
        [rec("feedback/01_zero_shot", None, 3), rec("feedback/01_zero_shot", None, 5)], tmp_path
    )
    rows = leaderboard(load_records(tmp_path))
    assert rows[0].avg_judge == 4.0 and rows[0].avg_rating is None


def test_old_records_without_judge_fields_still_load(tmp_path: Path) -> None:
    import json

    (tmp_path / "prompt_lab.json").write_text(
        json.dumps(
            [
                {
                    "time": "t",
                    "technique": "feedback/01_zero_shot",
                    "model": "m",
                    "question": "q",
                    "answer_preview": "a",
                    "overall": 4,
                    "cost_usd": 0.01,
                    "latency_s": 1.0,
                    "tokens": 10,
                    "rating": 4,
                    "note": "",
                }
            ]
        )
    )
    records = load_records(tmp_path)
    assert records[0].judge_overall is None and leaderboard(records)[0].avg_judge is None
