"""Basic tests for the Second Auditor."""

from bookforge.auditor import SecondAuditor, AuditEntry


def test_auditor_creates():
    """Verify auditor initializes without errors."""
    auditor = SecondAuditor(language="el")
    assert auditor.total_corrections == 0
    assert auditor.audit_log == []


def test_audit_entry():
    """Verify AuditEntry serialization."""
    entry = AuditEntry("abc", "def", "test reason")
    d = entry.to_dict()
    assert d["original"] == "abc"
    assert d["corrected"] == "def"
    assert d["category"] == "test reason"


def test_em_dash_spacing():
    """Verify em-dash spacing correction."""
    auditor = SecondAuditor(language="en")
    text = "word\u2014another"
    result, logs = auditor.audit_text(text)
    assert "\u2014" in result
    # Should have spaces around the em-dash
    assert "word \u2014 another" == result or " \u2014 " in result


def test_passthrough_clean_text():
    """Verify that clean text passes through unchanged."""
    auditor = SecondAuditor(language="en")
    text = "This is a perfectly clean sentence."
    result, logs = auditor.audit_text(text)
    assert result == text
    assert len(logs) == 0

