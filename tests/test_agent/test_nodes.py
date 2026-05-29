"""Unit tests for the pure node helpers (no LLM / no gateway)."""

from university_agent.nodes import _retry_feedback, render_schema


def test_render_schema_lists_relations_and_columns():
    schema = {
        "relations": [
            {"name": "my_enrollments", "columns": [{"name": "grade"}, {"name": "student_id"}]},
            {"name": "courses", "columns": [{"name": "code"}]},
        ]
    }
    rendered = render_schema(schema)
    assert "- my_enrollments(grade, student_id)" in rendered
    assert "- courses(code)" in rendered


def test_render_schema_handles_no_relations():
    assert "no accessible relations" in render_schema({"relations": []})


def test_retry_feedback_empty_when_no_history():
    assert _retry_feedback([]) == ""


def test_retry_feedback_lists_every_prior_attempt():
    feedback = _retry_feedback(
        [
            {"sql": "SELECT bad", "error": "no such column: bad"},
            {"sql": "SELECT * FROM enrollments", "error": "forbidden_relation"},
        ]
    )
    assert "SELECT bad" in feedback
    assert "no such column: bad" in feedback
    assert "SELECT * FROM enrollments" in feedback
    assert "forbidden_relation" in feedback
