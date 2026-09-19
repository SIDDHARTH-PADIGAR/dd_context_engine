import pytest

from dd_context_engine.ingestion.email import reconstruct_thread_key


def test_standard_headers_form_thread_key():
    result = reconstruct_thread_key(
        {
            "Message-ID": "<m2@example.com>",
            "In-Reply-To": "<m1@example.com>",
            "References": "<m0@example.com> <m1@example.com>",
        }
    )
    assert result.message_id == "<m2@example.com>"
    assert result.parent_id == "<m1@example.com>"
    assert result.references == ("<m0@example.com>", "<m1@example.com>")


def test_missing_message_id_is_rejected():
    with pytest.raises(ValueError):
        reconstruct_thread_key({})
