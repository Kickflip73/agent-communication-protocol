# Security Policy

ACP handles agent identity, message routing, and local relay connectivity. Please report security issues privately so maintainers can coordinate a fix before public disclosure.

## Supported Versions

Security fixes target the current `main` branch and the latest tagged release. Older protocol experiments in `research/`, `acp-research/`, and historical docs are not maintained as deployable software.

## Reporting a Vulnerability

Use GitHub Private Vulnerability Reporting from the repository's **Security** tab when it is enabled. Include:

- A short description of the issue and affected component
- Reproduction steps or a proof of concept
- Impact assessment, including whether keys, messages, or network boundaries are affected
- Any suggested mitigation

Please avoid opening public GitHub issues for vulnerabilities until a maintainer has acknowledged the report. If private vulnerability reporting is unavailable, open a non-sensitive issue asking maintainers for a private reporting channel.

## Response Targets

- Acknowledgement: within 3 business days
- Initial assessment: within 7 business days
- Fix or mitigation plan: based on severity and exploitability

## Security Documentation

See [docs/security.md](docs/security.md) for the relay security model, identity notes, and operational hardening guidance.
