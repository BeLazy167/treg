# AI Ark provider PRD

## Goal

Add AI Ark as an Enrichment provider with pasted-key access and safe shared-platform access for
bounded synchronous reads. A team's own key always wins and is never metered by treg.

## Scope

- Register `aiark` with `X-TOKEN` authentication and the free credit-balance probe.
- Catalog the current documented API surface. Prefer the V2 single-email and mobile routes and
  omit their duplicate V1 forms.
- Keep lists, async submissions, result reads, history, and webhook resend tools BYOK-only.
- Enable platform access for seven synchronous reads. Fix search page size to one so every hold has
  a known maximum and can settle without provider-specific runtime code.
- Add adapters only where an existing routed contract matches the provider response.
- Collect the remaining credit balance and apply the documented five-request-per-second rate.

## Price and evidence

The assigned plan costs $79 per month for 15,000 credits. The exact rate is $0.005266666… per
credit; treg rounds up to 5,267 micro-USD. Live checks on 2026-09-17 verified authentication,
balance reads, search pagination, fixed and hit-based charges, misses, validation errors, list
writes, and free async history reads. Charged synchronous responses reported `X-Credit` and matched
balance deltas. Two isolated local-app passes then proved platform settlement, routed zero-cost
misses, the real pasted-key connection flow and BYOK precedence. The work used 15.1 credits, below
the approved 50-credit limit.

## Safety boundary

Async jobs can charge at submission, refund up to ten hours later, and expose account-scoped track
IDs. The existing shared-key ownership and settlement contracts do not cover this combination.
They remain BYOK-only. No provider-specific branch is added to relay, money, routing, capacity,
async, or Arena code.

## Release state

The code adds the platform-key slot but does not enable it. Production needs the existing secret
and `aiark` in `TREG_PLATFORM_PROVIDERS`. No deployment, merge, purchase, or auto-top-up change is
part of this work.
