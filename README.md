# arc-conditional-pay

Hold a USDC payment on Arc until a milestone is verified, then release it. "Pay this
address 100 USDC when the work is verified, by this deadline, by this verifier." An agent
or an oracle calls verify, and the payment fires only if the milestone is met within the
rules. Expired or cancelled jobs never pay. Exposed as [MCP](https://modelcontextprotocol.io)
tools.

This is the milestone half of agent commerce. It pairs with
[arc-agent-guard](https://github.com/Mnorbert87/arc-agent-guard) (limits on what an agent
may spend) to make agent payments both bounded and conditional: an agent can release a
payment only when a job is genuinely done, and only within its budget.

## How it works

A job is created in the `open` state with a payee, an amount, an optional deadline, and an
optional required verifier. The lifecycle is a small, well-tested state machine:

```
open --verify (within deadline, right verifier)--> released   (pays)
open --deadline passes-------------------------->  expired     (never pays)
open --cancel------------------------------------> cancelled   (never pays)
```

The state transition is pure and deterministic, and the payment only fires when the
transition says it should. A failed send leaves the job open so it can be retried, rather
than silently marking it released.

## Tools

| Tool | What it does |
|------|--------------|
| `condpay_create` | create a held job (payee, amount, optional deadline and verifier) |
| `condpay_verify` | attest the milestone; releases the payment if allowed |
| `condpay_cancel` | cancel an open job before release |
| `condpay_run_expiry` | mark past-deadline jobs as expired |
| `condpay_get` / `condpay_list` | inspect jobs |
| `condpay_wallet` | the paying wallet and whether a key is set |

## Example

```
condpay_create(payee="0xfreelancer", amount_usdc=100, required_verifier="0xreviewer", expiry_ts=...)
# ... work happens ...
condpay_verify(job_id=1, verifier="0xreviewer")   # -> released, returns the Arc tx hash
```

## Run

```bash
cp .env.example .env
# set ARC_PRIVATE_KEY to a throwaway testnet key, funded at https://faucet.circle.com
uv run -m condpay.server
```

## Trust model

The funds are released from the configured wallet when a job is verified, so the payer
pre-funds the service. That is a custodial-style hold, not trustless escrow. A v2 that
locks funds in an on-chain Solidity contract (so neither side can pull them early) is the
natural next step. For testnet and agent automation, the custodial hold is the simple,
testable starting point.

## Tests

The release rules (verify pays, expiry and cancel never pay, wrong verifier blocked,
double-verify pays once, failed send stays open) are covered by a deterministic suite that
runs without a chain:

```bash
uv run -m pytest
```

## License

MIT, see [LICENSE](LICENSE). Part of an agent payments stack for Arc.
