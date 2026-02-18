"""
Git diff value extraction.

Parses unified diff output and extracts concrete values that might
appear in stored memories: IPs, ports, URLs, file paths, env var
assignments, and version strings. Used by the git-watch invalidation
pipeline to find potentially stale memories.
"""

import re

# Regex patterns for value extraction
_IP_PATTERN = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
_PORT_PATTERN = re.compile(r"(?:port[:\s=]+|EXPOSE\s+|:)(\d{4,5})\b")
_URL_PATTERN = re.compile(r"(https?://[^\s\"'`,;)}\]]+)")
_ENV_VAR_PATTERN = re.compile(r"([A-Z][A-Z0-9_]{2,}=[^\s]+)")
_PATH_PATTERN = re.compile(r"(/[a-zA-Z0-9_./-]{4,})")
_VERSION_PATTERN = re.compile(r"(\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9]+)?)")
_CHANGED_FILE_PATTERN = re.compile(r"^diff --git a/(.+?) b/", re.MULTILINE)


def _is_changed_line(line: str) -> bool:
    """Check if a line is an added or removed line in a diff."""
    return line.startswith("+") or line.startswith("-")


def _strip_diff_prefix(line: str) -> str:
    """Remove the +/- prefix from a diff line."""
    if line.startswith("+") or line.startswith("-"):
        return line[1:]
    return line


def extract_values(diff_text: str) -> list[dict]:
    """
    Extract concrete values from unified diff text.

    Only processes added (+) and removed (-) lines, not context lines.
    Returns deduplicated list of {type, value} dicts.

    Types: ip, port, url, env_var, path, version
    """
    if not diff_text or not diff_text.strip():
        return []

    seen = set()
    results = []

    for raw_line in diff_text.splitlines():
        if not _is_changed_line(raw_line):
            continue

        line = _strip_diff_prefix(raw_line)

        # Extract IPs
        for match in _IP_PATTERN.finditer(line):
            ip = match.group(1)
            parts = ip.split(".")
            if all(0 <= int(p) <= 255 for p in parts):
                key = ("ip", ip)
                if key not in seen:
                    seen.add(key)
                    results.append({"type": "ip", "value": ip})

        # Extract ports
        for match in _PORT_PATTERN.finditer(line):
            port = match.group(1)
            if 1 <= int(port) <= 65535:
                key = ("port", port)
                if key not in seen:
                    seen.add(key)
                    results.append({"type": "port", "value": port})

        # Extract URLs
        for match in _URL_PATTERN.finditer(line):
            url = match.group(1)
            key = ("url", url)
            if key not in seen:
                seen.add(key)
                results.append({"type": "url", "value": url})

        # Extract env var assignments
        for match in _ENV_VAR_PATTERN.finditer(line):
            env = match.group(1)
            key = ("env_var", env)
            if key not in seen:
                seen.add(key)
                results.append({"type": "env_var", "value": env})

        # Extract file paths
        for match in _PATH_PATTERN.finditer(line):
            path = match.group(1)
            key = ("path", path)
            if key not in seen:
                seen.add(key)
                results.append({"type": "path", "value": path})

        # Extract version strings
        for match in _VERSION_PATTERN.finditer(line):
            ver = match.group(1)
            key = ("version", ver)
            if key not in seen:
                seen.add(key)
                results.append({"type": "version", "value": ver})

    return results


def parse_changed_files(diff_text: str) -> list[str]:
    """Extract file paths from diff --git headers."""
    return _CHANGED_FILE_PATTERN.findall(diff_text)
