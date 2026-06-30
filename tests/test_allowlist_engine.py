import pytest

from guardrails.allowlist_engine import check_max_length, validate_sql


class TestValidateSql:
    def test_clean_select(self):
        result = validate_sql("SELECT id, name FROM users", ["SELECT"])
        assert result.passed is True
        assert result.statement_type == "SELECT"

    def test_select_with_join(self):
        query = """
        SELECT u.id, o.total
        FROM users u
        JOIN orders o ON u.id = o.user_id
        WHERE o.total > 100
        """
        result = validate_sql(query, ["SELECT"])
        assert result.passed is True
        assert result.statement_type == "SELECT"

    def test_select_with_subquery(self):
        query = "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)"
        result = validate_sql(query, ["SELECT"])
        assert result.passed is True

    def test_drop_table(self):
        result = validate_sql("DROP TABLE Users", ["SELECT"])
        assert result.passed is False
        assert result.statement_type == "DROP"

    def test_stacked_query_semicolon(self):
        result = validate_sql("SELECT 1; DROP TABLE Users;--", ["SELECT"])
        assert result.passed is False
        assert "Multiple statements" in (result.reason or "")

    def test_comment_based_injection(self):
        result = validate_sql("SELECT * FROM users WHERE id = 1; -- DROP TABLE users", ["SELECT"])
        assert result.passed is False

    def test_case_variation_drop(self):
        result = validate_sql("DrOp TaBle users", ["SELECT"])
        assert result.passed is False
        assert result.statement_type == "DROP"

    def test_truncate(self):
        result = validate_sql("TRUNCATE TABLE users", ["SELECT"])
        assert result.passed is False
        assert result.statement_type == "TRUNCATE"

    def test_grant(self):
        result = validate_sql("GRANT ALL ON users TO attacker", ["SELECT"])
        assert result.passed is False
        assert result.statement_type == "GRANT"

    def test_delete(self):
        result = validate_sql("DELETE FROM users WHERE id = 1", ["SELECT"])
        assert result.passed is False
        assert result.statement_type == "DELETE"

    def test_insert(self):
        result = validate_sql("INSERT INTO users (name) VALUES ('x')", ["SELECT"])
        assert result.passed is False
        assert result.statement_type == "INSERT"

    def test_update(self):
        result = validate_sql("UPDATE users SET name = 'x' WHERE id = 1", ["SELECT"])
        assert result.passed is False
        assert result.statement_type == "UPDATE"

    def test_owasp_tautology(self):
        result = validate_sql(
            "SELECT * FROM users WHERE name = 'a' OR '1'='1'",
            ["SELECT"],
        )
        assert result.passed is True
        assert result.statement_type == "SELECT"

    def test_owasp_union_select(self):
        result = validate_sql(
            "SELECT id FROM users UNION SELECT password FROM admin",
            ["SELECT"],
        )
        assert result.passed is True
        assert result.statement_type == "SELECT"

    def test_owasp_stacked_admin_add(self):
        result = validate_sql(
            "SELECT 1; INSERT INTO admin VALUES ('hacker', 'pass')",
            ["SELECT"],
        )
        assert result.passed is False


class TestCheckMaxLength:
    def test_oversized_query(self):
        result = check_max_length("x" * 501, 500)
        assert result.passed is False
        assert "exceeds limit" in (result.reason or "")

    def test_within_limit(self):
        result = check_max_length("SELECT 1", 500)
        assert result.passed is True
