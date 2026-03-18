# Contributing to ACP

Welcome! ACP is a community-driven open standard. All contributions are welcome.

## Ways to Contribute

- 📝 **Spec feedback** — open an Issue to propose changes to the spec
- 🐛 **Bug reports** — SDK bugs, spec ambiguities
- 💡 **New message types** — propose via RFC process (see below)
- 🔌 **Transport bindings** — implement new transport adapters
- 🌐 **SDK ports** — JavaScript, Go, Rust, Java SDKs welcome
- 📖 **Documentation** — examples, tutorials, blog posts

## RFC Process (for Spec Changes)

1. Open an Issue tagged `[RFC]` describing the proposed change
2. Discussion period: 2 weeks minimum
3. If consensus reached, submit PR with spec changes
4. Core maintainers merge after review

## Development Setup

```bash
git clone https://github.com/Kickflip73/agent-communication-protocol
cd agent-communication-protocol/sdk/python
pip install -e ".[dev]"
pytest tests/
```

## Code Style

- Python: Black + isort
- TypeScript: Prettier + ESLint
- Spec: Markdown, clear language, examples for every concept

## License

By contributing, you agree your contributions are licensed under Apache 2.0.
