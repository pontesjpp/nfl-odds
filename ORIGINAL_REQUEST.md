# Original User Request

## Initial Request — 2026-09-10T18:30:15Z

Conduct a comprehensive security and integrity audit of the `nfl-odds` repository prior to merge and deployment, identifying potential credential leaks, sensitive data exposure, `.gitignore` coverage gaps, unwanted temporary files/artifacts, and PII or internal infrastructure references. Safely apply repository cleanups and produce a prioritized severity report with line references and actionable remediation steps.

Working directory: /home/jppontes/nfl-odds
Integrity mode: development

## Requirements

### R1. Secrets & Credential Detection
Scan the active codebase, uncommitted/staged files, untracked files, and the full Git commit history for hardcoded API keys, JWT tokens, private keys, database passwords, connection strings, or cloud service credentials. Verify that environment files (`.env`, `.env.local`, `.env.production`, etc.) are not tracked in Git.

### R2. Repository Hygiene & Artifact Audit
Scan for tracked or untracked temporary/runtime artifacts, including local database dumps, runtime logs (`*.log`), debug outputs, cache directories, OS files (`.DS_Store`), or test fixtures containing sensitive production data, PII, or internal infrastructure endpoints.

### R3. Safe Remediation & Git Configuration
Update `.gitignore` to comprehensively exclude all standard sensitive patterns, environment files, build/runtime caches, logs, and temporary artifacts. Unstage or untrack any accidentally tracked sensitive files without deleting necessary local developer files. If secrets are detected in Git history, provide copy-pasteable purge commands (e.g., using `git-filter-repo`).

### R4. Security Audit Report Deliverable
Generate a structured report at `SECURITY_AUDIT_REPORT.md` documenting:
- Audited scope (file counts, commit depth, directories inspected)
- Clean files vs. flagged files with severity ratings (Critical, High, Medium, Low)
- Exact file paths, line numbers, and pattern descriptions (with secrets redacted)
- Remediations applied and recommended future protections (e.g., pre-commit hooks)

## Acceptance Criteria

### Secrets & File Hygiene
- [ ] No `.env*` files or sensitive credential files are tracked or staged in Git (`git ls-files` check).
- [ ] `.gitignore` includes rules covering `.env*`, log files (`*.log`), build/runtime caches (`__pycache__`, `.pytest_cache`, `dist/`, etc.), local DB files/dumps, and `.DS_Store`.
- [ ] Working tree scan reveals zero unredacted high-confidence secrets or hardcoded passwords in code/config.

### History & PII Audit
- [ ] Git commit history (`git log -p`) has been scanned for historical secret leaks, with findings documented in the report.
- [ ] Test fixtures, seed data, and mocks are verified free of real PII or internal infrastructure credentials.

### Deliverables & Independent Verification
- [ ] `SECURITY_AUDIT_REPORT.md` is generated in `/home/jppontes/nfl-odds` with clear severity ratings, file/line locations, and remediation steps.
- [ ] An automated programmatic verification script is executed to validate repository clean state, returning exit code 0.
