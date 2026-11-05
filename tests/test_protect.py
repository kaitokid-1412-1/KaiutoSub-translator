"""Unit tests for tag protection and style preservation."""

from subtrans.core.protect import TagProtector


def test_tag_protection_lead_and_midline():
    protector = TagProtector()
    raw = r"{\an8}{\pos(100,200)}Hello {\i1}world{\i0}!\NThis is a \htest."

    protected = protector.protect(raw)
    assert protected.lead == r"{\an8}{\pos(100,200)}"
    assert "[[T1]]" in protected.payload
    assert "[[T2]]" in protected.payload
    assert "[[T3]]" in protected.payload
    assert "\n" in protected.payload
    assert r"\N" not in protected.payload

    # Simulate translation preserving tokens
    translated_payload = "سلام [[T1]]دنیا[[T2]]!\nاین یک [[T3]]آزمایش است."
    restored, is_valid = protector.restore(translated_payload, protected, is_ass=True)
    assert is_valid is True
    assert restored.startswith(r"{\an8}{\pos(100,200)}")
    assert r"{\i1}" in restored
    assert r"{\i0}" in restored
    assert r"\h" in restored
    assert r"\N" in restored


def test_tag_protection_missing_token_degraded():
    protector = TagProtector()
    raw = r"Hello {\i1}world{\i0}!"
    protected = protector.protect(raw)

    # Translation lost [[T2]]
    bad_translation = "سلام [[T1]]دنیا!"
    assert protector.validate_tokens(bad_translation, protected) is False

    restored, is_valid = protector.restore(bad_translation, protected, is_ass=True)
    assert is_valid is False
    # Tokens stripped in degraded restore
    assert "[[T1]]" not in restored
    assert "سلام" in restored


def test_tag_protection_plain_text():
    protector = TagProtector()
    raw = "Just a simple text line."
    protected = protector.protect(raw)
    assert protected.lead == ""
    assert protected.payload == "Just a simple text line."
    assert not protected.has_tokens

    restored, is_valid = protector.restore("فقط یک خط متن ساده.", protected, is_ass=True)
    assert is_valid is True
    assert restored == "فقط یک خط متن ساده."
