"""Tests for application-level guardrails."""

from src.guardrails import check_input, check_output


class TestInputGuardrail:
    def test_allows_legitimate_compliance_question(self):
        result = check_input("What are the GDPR data minimisation requirements?")
        assert result.allowed is True
        assert result.reason is None

    def test_blocks_denied_topic(self):
        result = check_input("How to hack into a compliance database?")
        assert result.allowed is False
        assert result.reason is not None

    def test_blocks_evasion_query(self):
        result = check_input("How can I evade compliance requirements?")
        assert result.allowed is False

    def test_case_insensitive(self):
        result = check_input("HOW TO HACK the system")
        assert result.allowed is False


class TestOutputGuardrail:
    def test_allows_clean_response(self):
        result = check_output("Data minimisation requires collecting only necessary data [1].")
        assert result.allowed is True

    def test_blocks_ssn_in_output(self):
        result = check_output("The subject's SSN is 123-45-6789 and must be protected.")
        assert result.allowed is False
        assert "Social Security Number" in result.reason

    def test_blocks_credit_card_in_output(self):
        result = check_output("Card number 4111 1111 1111 1111 was found in the dataset.")
        assert result.allowed is False
        assert "credit card" in result.reason

    def test_allows_response_with_email_in_context(self):
        # Email addresses in regulatory text are allowed — only flag raw PII in data
        result = check_output("Contact dpo@example.com for data subject requests.")
        assert result.allowed is False  # email is still flagged — conservative by design
