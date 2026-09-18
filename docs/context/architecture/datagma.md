---
title: Datagma — single-record enrichment and internal account capacity
status: implemented; live authentication, prices, charges, and response shapes verified
sources:
  - src/treg/catalog/datagma.yaml
  - src/treg/catalog/examples/datagma.people.email.find.json
  - src/treg/catalog/examples/datagma.people.enrich.json
  - src/treg/catalog/examples/datagma.companies.enrich.json
  - src/treg/catalog/examples/datagma.people.phone.find.json
  - src/treg/catalog/examples/datagma.people.job-change.detect.json
  - src/treg/catalog/adapters.yaml
  - src/treg/catalog/fx.yaml
  - src/treg/config.py
  - src/treg/oauth_providers.py
  - src/treg/providers.py
  - src/treg/application/call/settle.py
  - src/treg/domain/capacity/collectors.py
  - src/treg/domain/capacity/policy.py
  - tests/test_datagma.py
  - tests/test_capacity_overflow_routes.py
  - tests/test_key_providers.py
related:
  - architecture/catalog.md
  - architecture/auth-secrets.md
  - architecture/money.md
  - interface/enrich-arena.md
  - ops/capacity.md
---

# Datagma

Datagma is a pasted-key enrichment provider at `https://gateway.datagma.net`. Its API ID rides in
the `apiId` query parameter. A team's own key has priority and is never metered or routed through
the shared key. `TREG_PLATFORM_KEY_DATAGMA` enables the platform key only when `datagma` is also in
`TREG_PLATFORM_PROVIDERS`.

## Public surface

The catalog exposes five synchronous, read-only, single-record tools:

- find a verified work email;
- enrich a person without phone or premium expansion;
- enrich a company with the premium and full company views;
- find a mobile phone;
- detect a job or employer change.

All five work with either a team's key or the platform key. There are no bulk tools. People search,
`phoneFull`, reverse email, reverse phone, and Twitter lookups remain out of scope because their
price or response contract was not verified for this release. `find_people` is intentionally not
implemented.

The free `GET /api/ingress/v1/mine` route is not a catalog tool. It is used only to validate a key
and collect platform capacity. Neither direct callers nor BYOK users can call it through `/call/`.
The connection flow returns only generic success or failure, and the capacity collector retains
only `currentCredit`; it discards the rest of the account response.

## Price and settlement

The platform acquired 3,000 prepaid credits for EUR 59. That is EUR 0.0196667 per credit. Using the
ECB 2026-09-17 reference rate of EUR 1 = USD 1.1481 gives USD 0.0225793, rounded up to 22,580
micro-USD per credit before the configured platform margin. Email, person, company, and job-change
calls reserve one credit. Phone reserves 30 credits, or 677,400 micro-USD.

Every successful Datagma response can report `creditBurn` as a numeric string. Settlement parses
that field and multiplies it by the request's frozen credit rate. This matters because a cached
email repeat returned HTTP 200 with `creditBurn: "0"`; it must release the whole hold. Missing,
negative, Boolean, nonnumeric, or nonfinite values are not accepted as charge evidence and fall
back to the normal conservative settlement rule. Shared-key 401, 403, 429, and upstream failures
remain free to the caller under the common platform rules.

Live checks observed one credit for a fresh verified email, basic person enrichment, premium plus
full company enrichment, and a completed job-change check. A successful mobile lookup used 30
credits. A geographically restricted mobile lookup returned HTTP 403 and used no credits.

## Routing and Enrich Arena

Verified adapters add Datagma email finding, person enrichment, and company enrichment to the
corresponding `treg.*` routed tools. Enrich Arena discovers the same adapters and fixtures. The
one-credit rate is competitive with the current provider sets.

Phone has no adapter. At 30 credits, its base cost is USD 0.6774, near the top of the current phone
provider range, so it stays an explicit direct tool rather than an automatic fallback or Arena
contender. Job-change detection has no matching routed or Arena contract and also stays direct.

## Capacity and operations

The capacity collector calls the free internal account route, accepts a finite nonnegative numeric
`currentCredit`, and reports only the remaining prepaid credits. HTTP errors are replaced with a
sanitized message because an `httpx` exception can include the query credential in its URL. The
policy is `credits / manual / api`. Datagma documents 10 requests per second, which is also the
shared-key smoothing limit. No empty-account response was forced, and no overflow route is claimed.

The committed examples are synthetic. They contain no API ID, account identity, real mobile
number, raw account response, or balance.
