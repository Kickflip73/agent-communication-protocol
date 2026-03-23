# Contributing to ACP

Welcome! ACP is a community-driven open standard. All contributions are welcome.

## Ways to Contribute

- 📝 **Spec feedback** — open an Issue to propose changes to the spec
- 🐛 **Bug reports** — relay bugs, SDK bugs, spec ambiguities
- 💡 **New features** — propose via RFC process (see below)
- 🔌 **Transport bindings** — HTTP/2, gRPC-lite, QUIC adapters
- 🌐 **SDK ports** — Java, C#, Swift, Ruby SDKs welcome  
  *(Python ✅ · Node.js ✅ · Go ✅ · Rust ✅ — already complete)*
- 🧪 **Conformance tests** — add compat suite coverage for DID / Extension / SSE  
  *(see [`docs/conformance.md`](docs/conformance.md))*
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
