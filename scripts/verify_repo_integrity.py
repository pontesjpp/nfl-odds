#!/usr/bin/env python3
"""
Repository Security & Integrity Verification Script.

Automated gatekeeper validating:
  1. Forbidden tracked files in git index (no .env, .db, .joblib, scrape dumps)
  2. Git staging area hygiene (no sensitive files staged)
  3. Root .gitignore completeness and functional git check-ignore probing
  4. Working tree secret regex scan across active code/config (ignoring local .env)
  5. Pytest suite execution and mock data PII validation
  6. SECURITY_AUDIT_REPORT.md existence and structural section completeness
  7. Git status and working tree cleanliness

Zero External Dependencies: Uses Python Standard Library only.
Exit Codes:
  0: All verification checks passed.
  1: One or more checks failed.
  2: Command-line invocation / usage error.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import fnmatch
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import List, Optional, Tuple

# ==============================================================================
# Configuration & Pattern Definitions
# ==============================================================================

FORBIDDEN_TRACKED_PATTERNS = [
    # Environment & Secrets
    ".env", ".env.*",
    "*.pem", "*.key", "*.pfx", "*.p12", "id_rsa*", "id_ed25519*", "*.crt",
    # Databases & Storage
    "*.db", "*.sqlite", "*.sqlite3", "*.dump", "*.sql",
    "data/nfl_odds.db",
    # Scraper Dumps & Residue
    "data/ng_state.json",
    "data/*.html", "data/links.txt", "data/raw_odds.txt",
    "data/*_cache.json",
    # Binary ML Models & Large Datasets
    "*.joblib", "*.parquet", "*.pkl", "*.pickle",
    # Logs & OS Files
    "*.log", "npm-debug.log*", "yarn-error.log*",
    ".DS_Store", "Thumbs.db",
    # Build & Test Caches
    "__pycache__/*", "*.py[oc]",
    ".pytest_cache/*", ".coverage", "htmlcov/*",
    # Tooling & Coordination
    ".vscode/*", ".idea/*", ".agents/*",
]

ALLOWED_TRACKED_FILES = {
    ".env.example",
    ".env.template",
    ".gitkeep",
}

ALLOWED_TRACKED_PATTERNS = [
    "data/depth_charts_2026_2027/*",
]

REQUIRED_GITIGNORE_RULES = [
    ("Environment variables (.env / .env.*)", re.compile(r"^\s*\.env(?:\.\*|\b)", re.MULTILINE)),
    ("Exemption for .env.example (!.env.example)", re.compile(r"^\s*!\.env\.example\b", re.MULTILINE)),
    ("Databases (*.db / *.sqlite)", re.compile(r"\*\.db|\*\.sqlite", re.MULTILINE)),
    ("Logs (*.log)", re.compile(r"\*\.log", re.MULTILINE)),
    ("Python & test caches (__pycache__ / .pytest_cache)", re.compile(r"__pycache__", re.MULTILINE)),
    ("OS Artifacts (.DS_Store)", re.compile(r"\.DS_Store", re.MULTILINE)),
    ("Scraper dumps & caches (data/*.html / data/ng_state.json / *.joblib / *.parquet)",
     re.compile(r"data/\*\.html|\.joblib|\.parquet|ng_state\.json", re.MULTILINE)),
]

DYNAMIC_IGNORE_PROBES = [
    # (Path, MustBeIgnored: bool)
    (".env", True),
    (".env.local", True),
    ("data/test.db", True),
    ("data/nfl_odds.db", True),
    ("debug.log", True),
    (".DS_Store", True),
    ("__pycache__", True),
    ("data/ng_state.json", True),
    ("data/betclic_page.html", True),
    ("model.joblib", True),
    ("dataset.parquet", True),
    (".agents/", True),
    (".env.example", False),
    ("src/nfl_odds/pipeline.py", False),
    ("README.md", False),
]

SECRET_PATTERNS = [
    ("Google Places API Key", re.compile(r"\bAIzaSy[0-9A-Za-z-_]{33}\b")),
    ("Google API Key (General)", re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b")),
    ("Google Gemini Key Format", re.compile(r"\bAQ\.[A-Za-z0-9_\-]{30,}\b")),
    ("OpenAI API Key", re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|sk-proj-[A-Za-z0-9_\-]{40,})\b")),
    ("Anthropic API Key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{30,}\b")),
    ("AWS Access Key ID", re.compile(r"\b(?:AKIA|ABIA|ACCA)[0-9A-Z]{16}\b")),
    ("AWS Secret Access Key Assignment", re.compile(r"(?i)aws_secret_access_key\s*=\s*['\"][A-Za-z0-9/+=]{40}['\"]")),
    ("GitHub Token", re.compile(r"\b(?:(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82})\b")),
    ("Private Key Header", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("Database URI with Password", re.compile(r"\b(?:postgres|postgresql|mysql|mongodb|redis):\/\/[^:\s]+:[^@\s]+@[A-Za-z0-9.-]+")),
    ("Hardcoded Credential Assignment", re.compile(r"(?i)(?:api_key|secret_key|admin_secret|auth_token|access_token|password)\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]")),
]

SAFE_PLACEHOLDERS = [
    "SUA_CHAVE_", "YOUR_KEY_HERE", "YOUR_API_KEY", "CHANGEME", "TODO",
    "dummy", "placeholder", "xxx", "REDACTED", "REPLACEME", "example",
    "os.getenv", "os.environ.get", '""', "''",
]

EXCLUDE_DIRS = {
    ".git", ".venv", "node_modules", ".next", "__pycache__",
    ".agents", "scratch", ".pytest_cache"
}

EXCLUDE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".pdf", ".joblib", ".parquet", ".db", ".sqlite", ".sqlite3",
    ".pyc", ".pyo", ".woff", ".woff2", ".ttf", ".eot", ".lock",
}

PII_PATTERNS = [
    ("Real Email Address", re.compile(r"\b[A-Za-z0-9._%+-]+@(?!example\.com|test\.com|localhost)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("North American Phone Number", re.compile(r"\b(?:\+?1[-.\s]?)?\(?[2-9][0-9]{2}\)?[-.\s]?[2-9][0-9]{2}[-.\s]?[0-9]{4}\b")),
    ("Social Security Number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("Internal RFC1918 IP Address", re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")),
]

REPORT_REQUIRED_SECTIONS = [
    ("Document Title", re.compile(r"^#\s+.*Security.*Audit.*", re.MULTILINE | re.IGNORECASE)),
    ("Audited Scope", re.compile(r"^##\s+.*(?:Scope|Audited Scope).*", re.MULTILINE | re.IGNORECASE)),
    ("Severity Ratings & Findings", re.compile(r"^##\s+.*(?:Severity|Findings|Clean vs\.? Flagged).*", re.MULTILINE | re.IGNORECASE)),
    ("Remediations Applied", re.compile(r"^##\s+.*(?:Remediation|Remediations Applied|Remediation Steps).*", re.MULTILINE | re.IGNORECASE)),
    ("Future Protections", re.compile(r"^##\s+.*(?:Future Protection|Recommendations|Continuous Security).*", re.MULTILINE | re.IGNORECASE)),
]

REPORT_REQUIRED_KEYWORDS = ["Critical", "High", "Medium", "Low"]

# ==============================================================================
# Helper Classes & Functions
# ==============================================================================

@dataclass
class CheckResult:
    check_id: int
    name: str
    passed: bool
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)

class UI:
    def __init__(self, use_color: bool = True):
        self.use_color = use_color and sys.stdout.isatty()

    def green(self, text: str) -> str:
        return f"\033[92m{text}\033[0m" if self.use_color else text

    def red(self, text: str) -> str:
        return f"\033[91m{text}\033[0m" if self.use_color else text

    def yellow(self, text: str) -> str:
        return f"\033[93m{text}\033[0m" if self.use_color else text

    def bold(self, text: str) -> str:
        return f"\033[1m{text}\033[0m" if self.use_color else text

    def cyan(self, text: str) -> str:
        return f"\033[96m{text}\033[0m" if self.use_color else text

def redact_secret(val: str) -> str:
    val = val.strip()
    if len(val) <= 12:
        return "***"
    return f"{val[:8]}...{val[-4:]}"

def get_repo_root() -> Path:
    try:
        root_bytes = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL)
        return Path(root_bytes.decode("utf-8").strip())
    except Exception:
        return Path(__file__).resolve().parent.parent

def is_path_whitelisted(rel_path: str) -> bool:
    if rel_path in ALLOWED_TRACKED_FILES:
        return True
    for pat in ALLOWED_TRACKED_PATTERNS:
        if fnmatch.fnmatch(rel_path, pat):
            return True
    return False

# ==============================================================================
# Check Implementations
# ==============================================================================

def check_1_tracked_files(repo_root: Path, verbose: bool) -> CheckResult:
    start_time = time.perf_counter()
    result = CheckResult(1, "Tracked Files Forbidden Pattern Audit", passed=True)
    
    try:
        raw_output = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo_root)
        tracked_files = [f for f in raw_output.decode("utf-8", errors="replace").split("\0") if f]
    except Exception as e:
        result.passed = False
        result.errors.append(f"Failed to execute `git ls-files`: {e}")
        result.duration_seconds = time.perf_counter() - start_time
        return result

    violations = []
    for rel_path in tracked_files:
        if is_path_whitelisted(rel_path):
            continue
        base_name = os.path.basename(rel_path)
        for pattern in FORBIDDEN_TRACKED_PATTERNS:
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(base_name, pattern):
                violations.append((rel_path, pattern))
                break

    if violations:
        result.passed = False
        for path, pattern in violations:
            result.errors.append(
                f"Tracked file '{path}' matches forbidden pattern '{pattern}'.\n"
                f"      Remediation: Run `git rm --cached \"{path}\"`"
            )
    else:
        result.info.append(f"Clean: All {len(tracked_files)} tracked files conform to tracking policies.")

    result.duration_seconds = time.perf_counter() - start_time
    return result

def check_2_staging_hygiene(repo_root: Path, verbose: bool) -> CheckResult:
    start_time = time.perf_counter()
    result = CheckResult(2, "Git Staging Area Hygiene", passed=True)

    try:
        # Use --diff-filter=d to exclude staged deletions (untracking a forbidden file is allowed)
        raw_output = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=d", "-z"], cwd=repo_root
        )
        staged_files = [f for f in raw_output.decode("utf-8", errors="replace").split("\0") if f]
    except Exception as e:
        result.passed = False
        result.errors.append(f"Failed to execute `git diff --cached`: {e}")
        result.duration_seconds = time.perf_counter() - start_time
        return result

    if not staged_files:
        result.info.append("Clean: Staging area has no added/modified forbidden files.")
        result.duration_seconds = time.perf_counter() - start_time
        return result

    staged_violations = []
    for rel_path in staged_files:
        if is_path_whitelisted(rel_path):
            continue
        base_name = os.path.basename(rel_path)
        for pattern in FORBIDDEN_TRACKED_PATTERNS:
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(base_name, pattern):
                staged_violations.append((rel_path, pattern))
                break

    if staged_violations:
        result.passed = False
        for path, pattern in staged_violations:
            result.errors.append(
                f"Forbidden file '{path}' is staged for commit (matched '{pattern}').\n"
                f"      Remediation: Run `git reset HEAD \"{path}\"`"
            )
    else:
        result.info.append(f"Clean: All {len(staged_files)} staged files conform to hygiene policies.")

    result.duration_seconds = time.perf_counter() - start_time
    return result

def check_3_gitignore_completeness(repo_root: Path, verbose: bool) -> CheckResult:
    start_time = time.perf_counter()
    result = CheckResult(3, "Root .gitignore Completeness & Check-Ignore", passed=True)
    gitignore_path = repo_root / ".gitignore"

    if not gitignore_path.exists():
        result.passed = False
        result.errors.append("Root `.gitignore` does not exist.")
        result.duration_seconds = time.perf_counter() - start_time
        return result

    gitignore_content = gitignore_path.read_text(encoding="utf-8", errors="replace")

    # 3A: Static inspection
    for rule_name, rule_regex in REQUIRED_GITIGNORE_RULES:
        if not rule_regex.search(gitignore_content):
            result.passed = False
            result.errors.append(f"Missing required .gitignore rule for: {rule_name}")

    # 3B: Dynamic check-ignore probe verification
    for probe_path, should_be_ignored in DYNAMIC_IGNORE_PROBES:
        proc = subprocess.run(
            ["git", "check-ignore", "-q", probe_path],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        is_ignored = (proc.returncode == 0)
        if should_be_ignored and not is_ignored:
            result.passed = False
            result.errors.append(f"Probe '{probe_path}' was NOT ignored by git (expected to be ignored).")
        elif not should_be_ignored and is_ignored:
            result.passed = False
            result.errors.append(f"Probe '{probe_path}' WAS ignored by git (expected to NOT be ignored).")

    if result.passed:
        result.info.append(f"Verified {len(REQUIRED_GITIGNORE_RULES)} rule categories and {len(DYNAMIC_IGNORE_PROBES)} functional probes.")

    result.duration_seconds = time.perf_counter() - start_time
    return result

def check_4_secret_scan(repo_root: Path, verbose: bool, report_path: Optional[Path] = None) -> CheckResult:
    start_time = time.perf_counter()
    result = CheckResult(4, "Working Tree Active Code & Config Secret Scan", passed=True)

    # 1. Get tracked files
    try:
        raw_output = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo_root)
        files_to_scan = set([f for f in raw_output.decode("utf-8", errors="replace").split("\0") if f])
    except Exception:
        files_to_scan = set()

    # 2. Add active source directory files (if not ignored)
    active_dirs = ["src", "scripts", "tests", "frontend", "docs"]
    for d in active_dirs:
        dir_path = repo_root / d
        if not dir_path.is_dir():
            continue
        for root, dirs, filenames in os.walk(dir_path):
            dirs[:] = [sub for sub in dirs if sub not in EXCLUDE_DIRS]
            for fname in filenames:
                full_path = Path(root) / fname
                rel_path = full_path.relative_to(repo_root).as_posix()
                files_to_scan.add(rel_path)

    # 3. Always scan root configuration, documentation, and deliverable files
    root_conf_files = [
        "pyproject.toml",
        "package.json",
        ".env.example",
        "pipeline.py",
        "SECURITY_AUDIT_REPORT.md",
        "README.md",
        ".gitignore",
    ]
    for root_conf in root_conf_files:
        if (repo_root / root_conf).exists():
            files_to_scan.add(root_conf)

    # Include custom audit report path if specified
    if report_path:
        target_report = (repo_root / report_path) if not report_path.is_absolute() else report_path
        if target_report.exists():
            try:
                files_to_scan.add(target_report.relative_to(repo_root).as_posix())
            except ValueError:
                pass

    # Also scan any root-level markdown or configuration files
    for item in repo_root.iterdir():
        if item.is_file() and not item.name.startswith("."):
            if item.suffix.lower() in {".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".py", ".sh"}:
                files_to_scan.add(item.name)

    secret_findings = []
    scanned_count = 0

    for rel_path in sorted(files_to_scan):
        full_path = repo_root / rel_path
        if not full_path.is_file():
            continue

        # Check extension
        if full_path.suffix.lower() in EXCLUDE_EXTENSIONS:
            continue

        # Skip excluded directory paths
        parts = full_path.relative_to(repo_root).parts
        if any(p in EXCLUDE_DIRS for p in parts):
            continue

        # Crucial: Check if file is untracked and gitignored (e.g. local .env)
        # If it is gitignored and NOT tracked, skip it!
        check_proc = subprocess.run(
            ["git", "check-ignore", "-q", rel_path],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if check_proc.returncode == 0:
            ls_proc = subprocess.run(
                ["git", "ls-files", "--error-unmatch", rel_path],
                cwd=repo_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if ls_proc.returncode != 0:
                # Untracked and ignored (e.g. local .env) -> skip
                continue

        scanned_count += 1
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                for line_no, line in enumerate(f, 1):
                    # Check safe placeholders
                    if any(ph in line for ph in SAFE_PLACEHOLDERS):
                        continue
                    # Check secret signatures
                    for name, pattern in SECRET_PATTERNS:
                        m = pattern.search(line)
                        if m:
                            secret_findings.append((rel_path, line_no, name, redact_secret(m.group(0))))
        except Exception as e:
            if verbose:
                result.warnings.append(f"Could not read {rel_path}: {e}")

    if secret_findings:
        result.passed = False
        for path, lno, name, preview in secret_findings:
            result.errors.append(f"Secret detected in {path}:{lno} [{name}] -> {preview}")
    else:
        result.info.append(f"Clean: Scanned {scanned_count} active code/config files with 0 unredacted secrets found.")

    result.duration_seconds = time.perf_counter() - start_time
    return result

def check_5_pytest_and_pii(repo_root: Path, verbose: bool) -> CheckResult:
    start_time = time.perf_counter()
    result = CheckResult(5, "Pytest Suite Execution & Mock PII Validation", passed=True)

    # 5A: Pytest execution
    cmd = None
    if shutil.which("uv"):
        cmd = ["uv", "run", "pytest", "tests/"]
    elif shutil.which("python3") and subprocess.run([sys.executable, "-m", "pytest", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        cmd = [sys.executable, "-m", "pytest", "tests/"]
    elif shutil.which("pytest"):
        cmd = ["pytest", "tests/"]

    if not cmd:
        result.passed = False
        result.errors.append("No viable pytest test runner detected in environment.")
        result.duration_seconds = time.perf_counter() - start_time
        return result

    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60
        )
        if proc.returncode != 0:
            result.passed = False
            result.errors.append(f"Pytest execution failed with exit code {proc.returncode}:\n{proc.stdout}\n{proc.stderr}")
        else:
            match = re.search(r"(\d+)\s+passed", proc.stdout)
            passed_count = match.group(1) if match else "all"
            result.info.append(f"Pytest passed successfully ({passed_count} tests).")
    except subprocess.TimeoutExpired:
        result.passed = False
        result.errors.append("Pytest execution timed out after 60 seconds.")
        result.duration_seconds = time.perf_counter() - start_time
        return result
    except Exception as e:
        result.passed = False
        result.errors.append(f"Failed to execute pytest runner {cmd}: {e}")
        result.duration_seconds = time.perf_counter() - start_time
        return result

    # 5B: Mock PII Scanning in tests/
    tests_dir = repo_root / "tests"
    pii_violations = []
    if tests_dir.is_dir():
        for root, _, files in os.walk(tests_dir):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                p = Path(root) / fname
                rel_p = p.relative_to(repo_root).as_posix()
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        for line_no, line in enumerate(f, 1):
                            for name, pat in PII_PATTERNS:
                                m = pat.search(line)
                                if m:
                                    pii_violations.append((rel_p, line_no, name, m.group(0)))
                except Exception as e:
                    result.warnings.append(f"Could not read test file {rel_p}: {e}")

    if pii_violations:
        result.passed = False
        for path, lno, name, val in pii_violations:
            result.errors.append(f"PII/Infra signature detected in test file {path}:{lno} [{name}] -> {val}")
    else:
        result.info.append("Clean: Test fixtures verified free of real PII and internal infrastructure references.")

    result.duration_seconds = time.perf_counter() - start_time
    return result

def check_6_security_audit_report(repo_root: Path, report_path: Optional[Path], verbose: bool) -> CheckResult:
    start_time = time.perf_counter()
    result = CheckResult(6, "Security Audit Report Completeness", passed=True)
    target = report_path or (repo_root / "SECURITY_AUDIT_REPORT.md")

    if not target.exists():
        result.passed = False
        result.errors.append(f"Deliverable '{target.name}' not found at {target}.")
        result.duration_seconds = time.perf_counter() - start_time
        return result

    file_size = target.stat().st_size
    if file_size < 1000:
        result.passed = False
        result.errors.append(f"Deliverable '{target.name}' is too small ({file_size} bytes). Minimum expected: 1000 bytes.")

    content = target.read_text(encoding="utf-8", errors="replace")

    # Check structural sections
    missing_sections = []
    for section_name, section_regex in REPORT_REQUIRED_SECTIONS:
        if not section_regex.search(content):
            missing_sections.append(section_name)

    if missing_sections:
        result.passed = False
        for sec in missing_sections:
            result.errors.append(f"Deliverable missing required structural section: '{sec}'")

    # Check required severity keywords
    missing_keywords = [kw for kw in REPORT_REQUIRED_KEYWORDS if not re.search(rf"\b{kw}\b", content, re.IGNORECASE)]
    if missing_keywords:
        result.passed = False
        result.errors.append(f"Deliverable missing required severity classification keywords: {missing_keywords}")

    if result.passed:
        result.info.append(f"Verified '{target.name}' ({file_size} bytes) contains all required sections and classifications.")

    result.duration_seconds = time.perf_counter() - start_time
    return result

def check_7_git_status_cleanliness(repo_root: Path, strict: bool, verbose: bool) -> CheckResult:
    start_time = time.perf_counter()
    result = CheckResult(7, "Git Status & Working Tree Cleanliness", passed=True)

    try:
        raw_output = subprocess.check_output(["git", "status", "--porcelain=v1", "-z"], cwd=repo_root)
    except Exception as e:
        result.passed = False
        result.errors.append(f"Failed to execute `git status --porcelain`: {e}")
        result.duration_seconds = time.perf_counter() - start_time
        return result

    entries = [e for e in raw_output.decode("utf-8", errors="replace").split("\0") if e]
    if not entries:
        result.info.append("Clean: Working tree and index are completely clean.")
        result.duration_seconds = time.perf_counter() - start_time
        return result

    permitted_untracked = {"ORIGINAL_REQUEST.md", ".agents/"}

    for entry in entries:
        if len(entry) < 3:
            continue
        status_code = entry[:2]
        path = entry[3:]

        # Untracked files
        if status_code == "??":
            base_name = os.path.basename(path)
            is_forbidden = any(
                fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(base_name, pat)
                for pat in FORBIDDEN_TRACKED_PATTERNS
            )
            if is_forbidden and not is_path_whitelisted(path):
                result.passed = False
                result.errors.append(f"Untracked forbidden file in working tree: '{path}'")
            elif strict and path not in permitted_untracked and not is_path_whitelisted(path):
                result.passed = False
                result.errors.append(f"Untracked file found (strict mode): '{path}'")
            else:
                result.info.append(f"Untracked permitted file: '{path}'")
        else:
            # Staged deletions of forbidden files are valid remediations (untracking)
            if status_code.strip() == "D" or status_code[0] == "D":
                result.info.append(f"Remediated: tracked artifact staged for deletion from index: [{status_code}] '{path}'")
                continue

            base_name = os.path.basename(path)
            is_forbidden = any(
                fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(base_name, pat)
                for pat in FORBIDDEN_TRACKED_PATTERNS
            )
            if is_forbidden and not is_path_whitelisted(path):
                result.passed = False
                result.errors.append(f"Forbidden artifact in dirty working tree state: [{status_code}] '{path}'")
            elif strict:
                result.passed = False
                result.errors.append(f"Uncommitted modification (strict mode): [{status_code}] '{path}'")
            else:
                result.warnings.append(f"Working tree has uncommitted change: [{status_code}] '{path}'")

    result.duration_seconds = time.perf_counter() - start_time
    return result

# ==============================================================================
# CLI Entry Point & Runner
# ==============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="NFL-Odds Repository Security and Integrity Verification Engine"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable detailed diagnostic logging")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress non-error output")
    parser.add_argument("-c", "--check", type=int, choices=range(1, 8), help="Run only a specific check (1 to 7)")
    parser.add_argument("--strict", action="store_true", help="Enforce strict cleanliness (fail on untracked files)")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color codes")
    parser.add_argument("--report-path", type=Path, default=None, help="Custom path to SECURITY_AUDIT_REPORT.md")

    args = parser.parse_args()
    ui = UI(use_color=not args.no_color)
    repo_root = get_repo_root()

    try:
        commit_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
    except Exception:
        commit_hash = "unknown"

    if not args.quiet:
        print(ui.bold("=" * 80))
        print(ui.bold("          NFL-ODDS REPOSITORY SECURITY & INTEGRITY VERIFICATION"))
        print(ui.bold("=" * 80))
        print(f"Repository Root : {repo_root}")
        print(f"Commit Hash     : {commit_hash}")
        print(f"Python Runtime  : {sys.version.split()[0]} ({sys.executable})")
        print(f"Timestamp       : {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
        print("-" * 80)

    check_functions = [
        (1, check_1_tracked_files),
        (2, check_2_staging_hygiene),
        (3, check_3_gitignore_completeness),
        (4, lambda r, v: check_4_secret_scan(r, v, args.report_path)),
        (5, check_5_pytest_and_pii),
        (6, lambda r, v: check_6_security_audit_report(r, args.report_path, v)),
        (7, lambda r, v: check_7_git_status_cleanliness(r, args.strict, v)),
    ]

    selected_checks = [item for item in check_functions if args.check is None or item[0] == args.check]
    results: List[CheckResult] = []
    total_start = time.perf_counter()

    for check_id, check_fn in selected_checks:
        res = check_fn(repo_root, args.verbose)
        results.append(res)

        status_tag = ui.green("[ PASS ]") if res.passed else ui.red("[ FAIL ]")
        dots = "." * (58 - len(res.name))
        if not args.quiet:
            print(f"[CHECK {res.check_id}/7] {res.name} {dots} {status_tag} ({res.duration_seconds:.3f}s)")

        if not res.passed or args.verbose:
            for err in res.errors:
                print(f"  {ui.red('[-] VIOLATION:')} {err}")
            for warn in res.warnings:
                print(f"  {ui.yellow('[!] WARNING:')} {warn}")
            if args.verbose:
                for inf in res.info:
                    print(f"  {ui.cyan('[+] INFO:')} {inf}")

    total_time = time.perf_counter() - total_start
    all_passed = all(r.passed for r in results)

    if not args.quiet:
        print("=" * 80)
        print(ui.bold("                               SUMMARY REPORT"))
        print("=" * 80)
        print(f"Total Checks Evaluated : {len(results)}")
        print(f"Passed Checks          : {sum(1 for r in results if r.passed)}")
        print(f"Failed Checks          : {sum(1 for r in results if not r.passed)}")
        print(f"Total Execution Time   : {total_time:.3f}s\n")

        if all_passed:
            print(ui.green(ui.bold(">>> OVERALL RESULT: ALL INTEGRITY CHECKS PASSED (EXIT CODE 0)")))
        else:
            print(ui.red(ui.bold(">>> OVERALL RESULT: INTEGRITY VERIFICATION FAILED (EXIT CODE 1)")))
        print("=" * 80)

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
