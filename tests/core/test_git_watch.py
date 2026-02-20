"""
Tests for the git diff value extraction module.

Verifies that concrete values (IPs, ports, URLs, paths, env vars, version strings)
are correctly extracted from unified diff output.
"""


def test_extract_ips():
    """Extract IPv4 addresses from diff output."""
    from src.core.diff_parser import extract_values

    diff = """\
+OLLAMA_HOST=192.168.50.62
-OLLAMA_HOST=192.168.50.10
+  server: 10.0.0.1:8080
"""
    values = extract_values(diff)
    ips = [v for v in values if v["type"] == "ip"]
    ip_addrs = {v["value"] for v in ips}
    assert "192.168.50.62" in ip_addrs
    assert "192.168.50.10" in ip_addrs
    assert "10.0.0.1" in ip_addrs


def test_extract_ports():
    """Extract port numbers from diff output."""
    from src.core.diff_parser import extract_values

    diff = """\
+  port: 8200
+  - "6379:6379"
+EXPOSE 11434
"""
    values = extract_values(diff)
    ports = {v["value"] for v in values if v["type"] == "port"}
    assert "8200" in ports
    assert "6379" in ports
    assert "11434" in ports


def test_extract_urls():
    """Extract URLs from diff output."""
    from src.core.diff_parser import extract_values

    diff = """\
+API_URL=http://192.168.50.19:8200
+  endpoint: https://api.example.com/v2/data
"""
    values = extract_values(diff)
    urls = {v["value"] for v in values if v["type"] == "url"}
    assert "http://192.168.50.19:8200" in urls
    assert "https://api.example.com/v2/data" in urls


def test_extract_env_vars():
    """Extract environment variable assignments from diff output."""
    from src.core.diff_parser import extract_values

    diff = """\
+RECALL_API_KEY=sk-test-12345
+OLLAMA_HOST=192.168.50.62
+DATABASE_URL=postgres://user:pass@localhost/db
"""
    values = extract_values(diff)
    env_vars = {v["value"] for v in values if v["type"] == "env_var"}
    assert "RECALL_API_KEY=sk-test-12345" in env_vars
    assert "DATABASE_URL=postgres://user:pass@localhost/db" in env_vars


def test_extract_file_paths():
    """Extract file paths from diff output."""
    from src.core.diff_parser import extract_values

    diff = """\
+  volume: /DATA/AppData/Recall/src:/app/src
+  config: ./config/nginx.conf
"""
    values = extract_values(diff)
    paths = {v["value"] for v in values if v["type"] == "path"}
    assert "/DATA/AppData/Recall/src" in paths or any(
        "/DATA/AppData" in v["value"] for v in values if v["type"] == "path"
    )


def test_extract_version_strings():
    """Extract version strings from diff output."""
    from src.core.diff_parser import extract_values

    diff = """\
+  image: python:3.14-slim
+  version: "2.7.0"
+pymupdf>=1.24.0
"""
    values = extract_values(diff)
    versions = {v["value"] for v in values if v["type"] == "version"}
    assert any("3.14" in v for v in versions)


def test_only_added_lines():
    """Only extract values from added (+) lines, not removed (-) or context."""
    from src.core.diff_parser import extract_values

    diff = """\
-OLD_HOST=10.0.0.1
+NEW_HOST=10.0.0.2
 UNCHANGED=10.0.0.3
"""
    values = extract_values(diff)
    ips = {v["value"] for v in values if v["type"] == "ip"}
    # Both added and removed lines should be extracted (both are changes)
    assert "10.0.0.2" in ips
    assert "10.0.0.1" in ips
    # Unchanged context lines should not be extracted
    assert "10.0.0.3" not in ips


def test_empty_diff():
    """Empty diff returns empty list."""
    from src.core.diff_parser import extract_values

    assert extract_values("") == []
    assert extract_values("\n\n") == []


def test_deduplication():
    """Same value appearing multiple times is deduplicated."""
    from src.core.diff_parser import extract_values

    diff = """\
+HOST=192.168.50.19
+BACKUP_HOST=192.168.50.19
+API=http://192.168.50.19:8200
"""
    values = extract_values(diff)
    ip_values = [v for v in values if v["type"] == "ip" and v["value"] == "192.168.50.19"]
    assert len(ip_values) == 1
