# Security Policy

## Reporting a Vulnerability

We take the security of this project seriously and encourage responsible disclosure of any security vulnerabilities following best practices from the [GitHub Security Lab](https://securitylab.github.com/).

### Private Vulnerability Reporting

Please **do not** open public GitHub issues or discussions for security vulnerabilities.

Instead, please use **[GitHub Private Vulnerability Reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)** directly on this repository:

1. Navigate to the main page of the repository.
2. Under the repository name, click **Security**.
3. Click **Report a vulnerability** to open a private disclosure draft.
4. Provide details, reproduction steps, and potential impact.

Your report will be reviewed privately, and a patch will be prepared and published before public advisory release.

---

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2026.x  | :white_check_mark: |
| < 2026  | :x:                |

---

## Security Guardrails & Practices

This repository enforces five core security layers aligned with `gh-secure`:

1. **Branch Protection**: Enforces pull requests, passing status checks, and linear history.
2. **Private Vulnerability Reporting**: Enables safe private reporting channels for external researchers.
3. **Secret Scanning & Push Protection**: Blocks accidental commits of API keys, tokens, or credentials.
4. **Dependabot Automated Security Updates**: Scans Python and GitHub Actions dependencies weekly.
5. **Code Scanning (CodeQL)**: Performs static analysis security scanning on every push and pull request.
