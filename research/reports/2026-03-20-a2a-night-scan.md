# A2A Research Scan — 2026-03-20 Evening

**By:** J.A.R.V.I.S. | **ACP context:** v0.7 complete, v0.8 planning | **Scan time:** 2026-03-20 19:13 CST

---

## Summary

Quiet evening for A2A (only 2 issues updated today, both from morning). Key signal: APS hit v1.18.0 with a new "Data Source Registration" module — growing fast, may become the de-facto Ed25519 identity standard. A2A #1628 trust.signals[] spec proposal confirms enterprise trust complexity continues to expand.

---

## 1. APS v1.18.0 — Module 36A (Data Source Registration & Access Receipts)

**Repo:** https://github.com/aeoess/agent-passport-system  
**Commit:** `463a8dc4` (2026-03-20 05:59)

### What Module 36A adds

Three data source registration modes:
- `self` — agent registers its own data
- `custodian` — trusted third party registers on behalf
- `gateway_observed` — gateway logs what it observed

New primitives:
- **Data access receipts** with gateway signature — proof that data was accessed
- **Terms compliance** — hard (must comply) vs advisory (should comply) split
- **Terms composition** — monotonic narrowing (child terms can only restrict, never expand parent)
- **Merkle commitment** — independent verification without trusting the registry

Audit fixes in this release:
- `expiresAt` signature inclusion (was missing from signed payload, security bug fixed)
- Revoker verification (was not checking delegation chain for revocation authority)

**Stats:** 894 tests, 245 suites, 36 modules, 0 failures

### ACP v0.8 implications

APS is now clearly production-quality (36 modules, 894 tests). For ACP v0.8 Ed25519 work:

- **Use APS as reference, not dependency** — import the crypto primitives pattern, not the full SDK
- The `expiresAt` bug fix is a lesson: signed payloads must include ALL time-bounded fields
- Module 36A's Merkle commitment pattern is interesting for future ACP audit logs (v1.0+)
- **v0.8 scope remains narrow**: Ed25519 keypair + sign + verify. No delegation chains, no revocation, no data receipts.

---

## 2. A2A #1628 — trust.signals[] Consolidated Spec

**Author:** `douglasborthwick-crypto` (+ 3 co-authors)  
**Comments:** 6 | **Updated:** 2026-03-20 00:18

### Four-signal taxonomy

| Signal Type | Description |
|-------------|-------------|
| `onchain_credentials` | Blockchain-verified credentials |
| `onchain_activity` | On-chain interaction history |
| `vouch_chain` | Other agents vouching for this agent |
| `behavioral` | ML-based behavioral trust score |

All signals use ECDSA/JWKS for verification. Trust registry for cold-start evaluation.

### ACP stance

This is the canonical example of enterprise trust over-engineering. ACP's response:
1. v0.7 HMAC = "I know who sent this message" (authentication)
2. v0.8 Ed25519 = "I can verify this agent's identity cryptographically" (identity)
3. NEVER: on-chain credentials, vouching networks, behavioral ML, trust registries

The 4-signal taxonomy addresses "cold start" and "Sybil attacks" — valid enterprise concerns, not ACP concerns. ACP users know their agents personally.

---

## 3. A2A Activity Level

- **Today total:** 2 issues updated (both from overnight, no new afternoon activity)
- **A2A TSC:** No new commits, no governance updates
- **ANP:** Still at 2026-03-05

**Pattern confirmed:** A2A moves slowly under TSC governance. ACP's fast iteration advantage is structural, not temporary.

---

## v0.8 Planning Notes (updated)

| Item | Priority | Reference |
|------|----------|-----------|
| Node.js SDK | P0 | — |
| Compatibility test suite | P0 | — |
| Ed25519 optional identity | P1 | APS v1.18.0 crypto patterns |
| `expiresAt` in signed payload | P1 (security) | APS Module 36A bug fix lesson |
| Merkle commitment for audit logs | P2/v1.0 | APS Module 36A |
| trust.signals[] / vouching | ❌ Never | A2A #1628 (too complex) |
