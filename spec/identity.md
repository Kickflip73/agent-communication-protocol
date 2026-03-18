# ACP Identity & Trust

## Agent Identifiers (AID)

ACP uses a DID-inspired identifier scheme:

```
did:acp:<namespace>:<local-id>
```

### Namespaces

| Namespace | Trust Level | Resolution |
|-----------|-------------|------------|
| `local` | Process-level (dev/test) | No resolution needed |
| `<org-name>` | Org-internal | Org's ACP registry |
| `global` | Cross-org public | Public ACP registry (v0.4+) |

## v0.1 Baseline (No Crypto)

In v0.1, identity is asserted (not verified). Suitable for:
- Local development
- Trusted internal networks
- Proof-of-concept deployments

## v0.4+ (Signed Messages)

Future versions will add:
- Ed25519 message signing
- DID document resolution
- JWT-based agent tokens
- mTLS for transport-level auth
