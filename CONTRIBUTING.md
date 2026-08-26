# Contributing to ACP

Thanks for helping improve the Agent Communication Protocol. ACP is a small,
interop-focused project: the most valuable contributions make it easier for two
independent agents, SDKs, or transports to talk to each other reliably.

Chinese contributors can also read [CONTRIBUTING.zh.md](CONTRIBUTING.zh.md).

## Good First Contributions

- Clarify protocol behavior in `spec/` or `docs/`
- Add runnable examples for common agent frameworks
- Extend SDK conformance coverage in `sdk/*/tests`
- Improve relay reliability, logging, or error messages
- Add transport bindings or compatibility notes for real deployments

Please open a GitHub issue before large protocol changes, new mandatory fields,
or changes that affect wire compatibility.

## Development Setup

```bash
git clone https://github.com/Kickflip73/agent-communication-protocol.git
cd agent-communication-protocol

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]" -e "./sdk/python[dev]"
```

The Node, Go, and Rust SDKs are intentionally lightweight. Their test commands
run from their own SDK directories and do not require generated code.

## Local Quality Checks

Run the focused checks before opening a pull request:

```bash
make lint
make test-python
make test-node
make test-go
make test-rust
make build
make docs
```

If you do not have every toolchain installed, run the checks for the files you
changed and mention any skipped checks in the pull request.

## Pull Request Guidelines

- Keep pull requests focused on one behavior or documentation improvement.
- Include tests for relay, SDK, or wire-format changes.
- Update docs when changing CLI flags, endpoints, AgentCard fields, or examples.
- Preserve backwards compatibility unless the issue or RFC explicitly calls for
  a breaking change.
- Use clear commit messages such as `fix(relay): handle closed stream` or
  `docs(spec): clarify task pagination`.

## RFC Process

Use the RFC flow for protocol-level changes:

1. Open an issue titled `[RFC] short proposal`.
2. Describe the motivation, compatibility impact, and example payloads.
3. Let the community discuss for at least 7 days.
4. Submit the spec PR after the direction is clear.
5. Add SDK or relay changes only after the spec text is reviewable.

## Security Issues

Do not open public issues for vulnerabilities. Follow
[SECURITY.md](SECURITY.md) and use GitHub Private Vulnerability Reporting from
the repository Security tab when available.

## License

By contributing, you agree that your contribution is licensed under the
[Apache License 2.0](LICENSE).
