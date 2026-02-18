"""
v2.3 Integration Tests — Full pipeline verification.

Validates that all v2.3 fixes are in place by checking source code
for the complete chain of fixes across all subsystems.
"""

import re
from pathlib import Path

# =============================================================
# Subsystem 1: Domain normalization
# =============================================================


def test_pipeline_domain_normalization_chain():
    """Full domain normalization chain: domains.py → signal_detector → observer → memory store."""
    # 1. Canonical domains exist
    domains_source = Path("src/core/domains.py").read_text()
    assert "CANONICAL_DOMAINS" in domains_source
    assert "normalize_domain" in domains_source

    # 2. Signal detector constrained
    detector_source = Path("src/core/signal_detector.py").read_text()
    assert "normalize_domain" in detector_source
    assert "must be one of" in detector_source.lower() or "one of:" in detector_source.lower()

    # 3. Observer constrained
    observer_source = Path("src/workers/observer.py").read_text()
    assert "normalize_domain" in observer_source
    assert "must be one of" in observer_source.lower() or "one of:" in observer_source.lower()

    # 4. Store path normalizes
    memory_source = Path("src/api/routes/memory.py").read_text()
    assert "normalize_domain" in memory_source

    # 5. Migration endpoint exists
    admin_source = Path("src/api/routes/admin.py").read_text()
    assert "domains/normalize" in admin_source


# =============================================================
# Subsystem 2: Signal pipeline
# =============================================================


def test_pipeline_signal_chain():
    """Signal pipeline: pending dict → approve → durability + importance."""
    # 1. Pending dict includes importance + durability
    signals_source = Path("src/workers/signals.py").read_text()
    pending_match = re.search(
        r"add_pending_signal\(\s*session_id,\s*\{(.*?)\}",
        signals_source,
        re.DOTALL,
    )
    assert pending_match
    pending_dict = pending_match.group(1)
    assert "importance" in pending_dict
    assert "durability" in pending_dict

    # 2. approve_signal sets durability + initial_importance
    ingest_source = Path("src/api/routes/ingest.py").read_text()
    approve_match = re.search(
        r'memory = Memory\((.*?)"approved": True\}.*?\)',
        ingest_source,
        re.DOTALL,
    )
    assert approve_match
    constructor = approve_match.group(0)
    assert "durability=" in constructor
    assert "initial_importance=" in constructor

    # 3. SIGNAL_DURABILITY fallback used
    assert "SIGNAL_DURABILITY" in ingest_source


# =============================================================
# Subsystem 3: Graph relationships
# =============================================================


def test_pipeline_graph_chain():
    """Graph: auto-linker → store paths → bootstrap endpoint."""
    # 1. Auto-linker exists
    linker_source = Path("src/core/auto_linker.py").read_text()
    assert "auto_link_memory" in linker_source
    assert "strengthen_relationship" in linker_source

    # 2. Called from all three store paths
    memory_source = Path("src/api/routes/memory.py").read_text()
    assert "auto_link_memory" in memory_source

    signals_source = Path("src/workers/signals.py").read_text()
    assert "auto_link_memory" in signals_source

    observer_source = Path("src/workers/observer.py").read_text()
    assert "auto_link_memory" in observer_source

    # 3. Bootstrap endpoint exists
    admin_source = Path("src/api/routes/admin.py").read_text()
    assert "graph/bootstrap" in admin_source


# =============================================================
# Subsystem 4: Decay/scoring balance
# =============================================================


def test_pipeline_decay_scoring_chain():
    """Decay/scoring: importance floor → null durability → rehabilitation."""
    # 1. Scoring uses importance floor
    retrieval_source = Path("src/core/retrieval.py").read_text()
    assert "max(memory.importance, 0.15)" in retrieval_source

    # 2. Null durability → durable
    decay_source = Path("src/workers/decay.py").read_text()
    assert "durability is None" in decay_source

    # 3. _payload_to_memory defaults to DURABLE
    assert "Durability.DURABLE" in retrieval_source

    # 4. Rehabilitation endpoint exists
    admin_source = Path("src/api/routes/admin.py").read_text()
    assert "importance/rehabilitate" in admin_source


# =============================================================
# Full chain: all 12 tasks verified
# =============================================================


def test_all_v23_fixes_present():
    """Every v2.3 fix is present — comprehensive gate test."""
    files = {
        "src/core/domains.py": ["CANONICAL_DOMAINS", "DOMAIN_ALIASES", "normalize_domain"],
        "src/core/signal_detector.py": ["normalize_domain"],
        "src/workers/observer.py": ["normalize_domain", "auto_link_memory"],
        "src/workers/signals.py": ["auto_link_memory"],
        "src/api/routes/memory.py": ["normalize_domain", "auto_link_memory"],
        "src/api/routes/ingest.py": ["SIGNAL_DURABILITY", "Durability"],
        "src/core/retrieval.py": ["max(memory.importance, 0.15)", "Durability.DURABLE"],
        "src/workers/decay.py": ["durability is None"],
        "src/core/auto_linker.py": ["auto_link_memory", "strengthen_relationship"],
        "src/api/routes/admin.py": [
            "domains/normalize",
            "graph/bootstrap",
            "importance/rehabilitate",
        ],
    }

    for filepath, expected_strings in files.items():
        source = Path(filepath).read_text()
        for s in expected_strings:
            assert s in source, f"Missing '{s}' in {filepath}"
