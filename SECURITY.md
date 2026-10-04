# 🛡️ Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| `0.4.x` | :white_check_mark: |
| `< 0.4` | :x:                |

## Reporting a Vulnerability

The Social Media Threat Intelligence Engine is designed for digital forensics examiners and cyber investigation cells. We take security vulnerabilities and responsible disclosure seriously.

### How to Report
- **Email:** Report security vulnerabilities privately to **chokshitirth4@gmail.com**.
- Please do **not** open public GitHub issues for security vulnerabilities involving potential exploits, token leakages, or remote execution risks.
- Include detailed steps to reproduce the issue, proof of concept (PoC) scripts, and any observed impact.

### Security Guarantees & Safeguards
1. **Zero Credential Exposure:** API keys and credentials must never be committed to git repositories. Always use `.env` or cloud secret managers.
2. **Path Traversal Defense:** Dataset IDs and stream IDs are strictly validated with `^[A-Za-z0-9_-]+$`.
3. **Upload Size Restrictions:** File ingestion is capped at a strict 50 MB limit to prevent disk exhaustion.
4. **Concurrency Protection:** Multi-threaded Louvain analysis jobs are throttled to prevent resource exhaustion on low-memory servers.
5. **Responsible AI Guardrails:** Strict non-profiling enforcement (`.bob/rules-osint-analyst/03-no-profiling.md`) blocks model-generated communal, religious, or caste attribution.
