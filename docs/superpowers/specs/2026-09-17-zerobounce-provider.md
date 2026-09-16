# ZeroBounce provider integration — product requirements

**Date:** 2026-09-17
**Base commit:** `346ddaaf3ab759aa54c65b8f936d9ca1a5498d22`
**Branch:** `codex/provider-zerobounce`

## Goal

Add a production-ready ZeroBounce provider without changing the shared relay contract. Give agents
one platform-eligible email-validation tool, BYOK account reads, the existing
`treg.people.email.verify` route, and automatic Enrich Arena discovery.

## Product boundary

The first release contains these tools:

| Tool | Upstream operation | Access | Charge |
|---|---|---|---|
| `zerobounce.people.email.verify` | `GET /v2/validate` | platform or BYOK | one credit for a non-unknown result |
| `zerobounce.account.credits` | `GET /v2/getcredits` | BYOK only | free |
| `zerobounce.account.usage` | `GET /v2/getapiusage` | BYOK only | free |

The documented API also includes batch validation, file validation, file scoring, finder, domain
search, Activity Data, filters, and list evaluation. These operations are not in this first release.
Batch validation needs `api_key` in the JSON body. Live tests on all three official hosts accepted
that documented body shape and rejected a query-bound key with HTTP 403. treg supports key bindings
in headers and query parameters, but it does not rewrite a caller's body to add a secret. File jobs
also need multipart and binary-response contracts. Filter writes and file deletion change account
state. Finder has 20-credit, 1-credit, and free branches. Activity Data has no stable public
per-call rate. These facts make exclusion safer than an incomplete tool.

## Credentials and health

ZeroBounce uses `api_key` in the query string for the selected endpoints. A connected team key must
win over `TREG_PLATFORM_KEY_ZEROBOUNCE` and remain unmetered. A shared key is available only when
`zerobounce` is in `TREG_PLATFORM_PROVIDERS`.

The connection probe calls the free API-usage route with a closed date range. Live checks returned
HTTP 403 for a missing or invalid key and HTTP 200 for the supplied key. The credit-balance route is
not the probe because an invalid key can return HTTP 200 with `Credits=-1`.

## Price and settlement

The supplied replacement cost is $69 for 5,000 credits, or $0.0138 per credit. ZeroBounce documents
one credit for a completed single validation and no charge for an unknown result. The tool uses
`per_success`. Its verified adapter treats `unknown` or a missing status as a miss, so the existing
generic settlement rule releases the hold. Other verdicts are answers and settle at 13,800
micro-USD. HTTP failures release the hold through the common call-runtime path.

Live sandbox checks for valid, invalid, and unknown results and two real-address checks produced the
expected response shapes with no balance change. This can be caused by sandbox, cache, free, or
refunded behavior. It does not replace the documented retail price. Discovery spent zero credits,
below the 25-credit limit.

## Capacity and traffic

The capacity collector reads `Credits` from the free balance route. It accepts nonnegative JSON
integers and decimal strings. It rejects Boolean values, missing or malformed values, negatives,
and the invalid-key sentinel. It does not include a query key in an error message. The returned note
states that vendor Auto-Pay is managed upstream and is not read or changed by treg.

ZeroBounce documents a much higher single-validation request rate. The shared-key policy starts at
25 requests per second. This is a conservative operational limit, not a claim about the upstream
maximum. No empty-account response was forced, and no overflow route is claimed.

## Routing and Arena

The adapter maps contract `email` to `queryParams.email`. It returns `status` and sets `valid=true`
only for the provider's `valid` verdict. Invalid, catch-all, spamtrap, abuse, and do-not-mail
verdicts remain useful negative answers. Unknown is a routed miss. The normal route planner and
Arena discovery use this verified adapter; no provider-specific registration is needed.

## Acceptance checks

- Catalog loading and invariant tests pass.
- Invalid and valid connection probes are covered.
- Credit parsing covers zero, number, string, sentinel, malformed, Boolean, and HTTP-error cases.
- Platform success, free unknown, upstream failure, and BYOK precedence are covered.
- The existing verification route and Arena plan both select ZeroBounce.
- Import boundaries, generated plugin mirrors, context drift, and the full test suite pass.
- Production remains disabled until the shared key and provider allow-list are configured.
