"""
v2.3 Tests — Null durability defaults to durable.

Source-level verification that:
1. decay.py treats null durability as "durable" (0.15x rate)
2. retrieval.py _payload_to_memory defaults null durability to Durability.DURABLE
"""

import re
from pathlib import Path


def _get_decay_source():
    return Path("src/workers/decay.py").read_text()


def _get_retrieval_source():
    return Path("src/core/retrieval.py").read_text()


def test_decay_defaults_null_durability_to_durable():
    """decay.py must default null durability to 'durable'."""
    source = _get_decay_source()

    # After getting durability from payload, there should be a null check
    # that sets it to "durable"
    # Look for the pattern between getting durability and checking "permanent"
    run_method = re.search(
        r'async def run\(.*?\n(?=\nasync def |\nclass |\Z)',
        source,
        re.DOTALL,
    )
    assert run_method, "Could not find run() method in decay.py"
    method_body = run_method.group(0)

    # Must have null durability → durable logic
    assert 'durability is None' in method_body or 'not durability' in method_body, (
        "decay.py must check for null durability"
    )
    # And it should set to "durable" as the safe default
    assert '"durable"' in method_body, (
        "decay.py must default null durability to 'durable'"
    )


def test_retrieval_defaults_null_durability_to_durable():
    """_payload_to_memory must default null durability to Durability.DURABLE."""
    source = _get_retrieval_source()

    # Find the _payload_to_memory method
    match = re.search(
        r'def _payload_to_memory\(.*?\n(?=\n    (?:async )?def |\nclass |\ndef |\Z)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find _payload_to_memory method"
    method_body = match.group(0)

    # Must default to DURABLE, not None
    assert "DURABLE" in method_body, (
        "_payload_to_memory must default null durability to Durability.DURABLE"
    )


def test_decay_null_durability_gets_reduced_rate():
    """Null durability should decay at 0.15x, not 1.0x."""
    source = _get_decay_source()

    run_method = re.search(
        r'async def run\(.*?\n(?=\nasync def |\nclass |\Z)',
        source,
        re.DOTALL,
    )
    assert run_method, "Could not find run() method in decay.py"
    method_body = run_method.group(0)

    # The null-to-durable conversion must happen BEFORE the durable rate check
    # Verify the null check appears before the "durable" rate reduction
    null_check_pos = method_body.find("durability is None") if "durability is None" in method_body else method_body.find("not durability")
    durable_rate_pos = method_body.find('effective_decay *= 0.15')

    assert null_check_pos >= 0, "Must have null durability check"
    assert durable_rate_pos >= 0, "Must have durable rate reduction"
    assert null_check_pos < durable_rate_pos, (
        "Null durability check must come before durable rate reduction"
    )
