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

## Follow-up — 2026-09-15T09:30:53Z

Implement the Week 2 NFL props predictive and betting pipeline improvements plan: calibrate model win probabilities to address Brier score deficit, enforce conservative risk management rules (haircut for high EV bets and default flat sizing), and introduce automated regression verification.

Working directory: /home/jppontes/nfl-odds
Integrity mode: development

## Requirements

### R1. Probability Calibration Layer
Introduce a formal probability calibration stage (e.g. Platt Scaling or Isotonic Regression) applied to the XGBoost quantile-interpolated probabilities before EV calculation. The calibration must demonstrably improve the Brier Skill Score against a baseline predictor on historical holdout data.

### R2. Stake Management & High-EV Haircut
Adjust the betting logic to apply a risk haircut (reduced exposure factor, e.g. 0.75x) to bets with high nominal expected value (EV > 8.0%) rather than inflating stakes, while keeping the Safe Flat (1.0u) allocation tier prominently featured as the recommended baseline.

### R3. Automated Pipeline Tests & Significance Verification
Build an end-to-end regression test suite verifying that odds parsing, probability calibration, EV evaluation, and stake calculations produce valid and bounded outputs. Ensure the weekly significance tracking routine integrates cleanly with settled results.

## Acceptance Criteria

### Calibration & Edge Evaluation
- [ ] Calibration transformation is applied to win probabilities across all supported markets (passing, rushing, receiving yards) without producing unmonotonic or NaN probabilities.
- [ ] A test script or benchmark confirms a positive or improved Brier Skill Score on validation splits compared to uncalibrated probabilities.
- [ ] The fair odds and EV calculations strictly consume the calibrated probabilities.

### Risk Sizing
- [ ] Portfolio sizing engine applies an explicit haircut to picks where EV > 8.0% instead of awarding higher unit multipliers.
- [ ] Safe Flat portfolio calculations remain exact 1.0u per bet regardless of model multipliers.

### Verification & Robustness
- [ ] A dedicated test command (e.g. pytest or equivalent test runner) executes all unit and pipeline verification tests with exit code 0.
- [ ] No regression is introduced to existing dashboard API endpoints (`/api/predict`, `/api/portfolio`, `/api/top-picks`).
