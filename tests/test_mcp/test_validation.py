"""SQL validation stage: shape (single read-only statement) and access (allowlist)."""

from university_db_mcp.validation import RejectionCategory, validate_sql

# A representative student-style scope: scoped views + public reference tables.
ALLOWLIST = frozenset(
    {"my_enrollments", "me", "courses", "semesters", "course_offerings", "teachers"}
)


def test_accepts_simple_select():
    assert validate_sql("SELECT * FROM my_enrollments", ALLOWLIST).ok


def test_accepts_join_and_aggregation():
    sql = (
        "SELECT AVG(e.grade) FROM my_enrollments e "
        "JOIN course_offerings o ON e.offering_id = o.id "
        "JOIN courses c ON o.course_id = c.id WHERE c.code = 'CS101'"
    )
    assert validate_sql(sql, ALLOWLIST).ok


def test_accepts_cte_without_flagging_the_cte_name():
    # `g` is an inline CTE, not a base relation — must not be treated as forbidden.
    sql = (
        "WITH g AS (SELECT grade FROM my_enrollments WHERE grade IS NOT NULL) "
        "SELECT MIN(grade) FROM g"
    )
    assert validate_sql(sql, ALLOWLIST).ok


def test_relation_names_are_case_insensitive():
    assert validate_sql("SELECT * FROM My_Enrollments", ALLOWLIST).ok


def test_rejects_forbidden_relation():
    # raw enrollments is not in a student's allowlist
    result = validate_sql("SELECT * FROM enrollments", ALLOWLIST)
    assert not result.ok
    assert result.category == RejectionCategory.FORBIDDEN_RELATION
    assert result.reason is not None
    assert "enrollments" in result.reason


def test_rejects_non_select_statements():
    for sql in (
        "DELETE FROM my_enrollments",
        "UPDATE my_enrollments SET grade = 100",
        "INSERT INTO me (id) VALUES (1)",
        "DROP TABLE courses",
    ):
        result = validate_sql(sql, ALLOWLIST)
        assert not result.ok
        assert result.category == RejectionCategory.NOT_READ_ONLY


def test_rejects_multiple_statements():
    result = validate_sql("SELECT * FROM courses; DROP TABLE courses", ALLOWLIST)
    assert not result.ok
    assert result.category == RejectionCategory.NOT_SINGLE_STATEMENT


def test_rejects_unparseable_sql():
    result = validate_sql("SELECT FROM WHERE ((", ALLOWLIST)
    assert not result.ok
    assert result.category == RejectionCategory.PARSE_ERROR
