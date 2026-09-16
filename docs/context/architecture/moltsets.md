---
title: MoltSets — enrichment records, shared-plan pricing and BYOK
status: shipped
sources:
  - src/treg/catalog/moltsets.yaml
  - src/treg/catalog/examples/moltsets.people.search.json
  - src/treg/catalog/examples/moltsets.companies.search.json
  - src/treg/catalog/examples/moltsets.linkedin.profile.search.json
  - src/treg/catalog/examples/moltsets.people.email.find.name.json
  - src/treg/catalog/examples/moltsets.people.enrich.name.json
  - src/treg/catalog/examples/moltsets.people.email.find.json
  - src/treg/catalog/examples/moltsets.people.email.find.business.json
  - src/treg/catalog/examples/moltsets.people.email.find.personal.json
  - src/treg/catalog/examples/moltsets.people.email.find.personal-best.json
  - src/treg/catalog/examples/moltsets.people.phone.find.json
  - src/treg/catalog/examples/moltsets.people.enrich.email.json
  - src/treg/catalog/examples/moltsets.people.enrich.linkedin.json
  - src/treg/catalog/examples/moltsets.people.audiences.maid.json
  - src/treg/catalog/examples/moltsets.people.audiences.sha256.json
  - src/treg/catalog/examples/moltsets.people.audiences.hashes.json
  - src/treg/catalog/examples/moltsets.linkedin.profile.from-email.json
  - src/treg/catalog/examples/moltsets.companies.identify.ip.json
  - src/treg/catalog/adapters.yaml
  - src/treg/catalog/fx.yaml
  - src/treg/oauth_providers.py
  - src/treg/providers.py
  - src/treg/config.py
  - src/treg/domain/capacity/collectors.py
  - src/treg/domain/capacity/policy.py
  - src/treg/web/logos/moltsets.svg
  - tests/test_moltsets.py
  - tests/test_capacity_overflow_routes.py
  - tests/conftest.py
  - tests/test_key_providers.py
  - tests/test_oauth_providers_m3.py
  - tests/test_providers.py
related:
  - architecture/catalog.md
  - architecture/auth-secrets.md
  - architecture/money.md
  - interface/enrich-arena.md
  - ops/capacity.md
---

# MoltSets

MoltSets is a pasted Bearer-key enrichment provider at
`https://api.moltsets.com/api/v1/tools`. `oauth_providers.MOLTSETS` verifies a key with free
`POST /get_account`; the account, billing, and usage operations stay internal probes rather than
public tools. A team's own key wins and is never metered by treg. `platform_key_moltsets` supplies
the optional shared credential, and the existing provider allow-list remains the production switch.
This integration does not change that switch.

The catalog exposes all 17 documented data operations: people and company search, name/company
lookups, four profile-to-email variants, phone lookup, two reverse enrichments, three audience/hash
lookups, email-to-profile, and IP-to-company. Every operation was exercised with synthetic inputs.
MoltSets returns HTTP 200 for both hits and misses; `status: ok` is a hit and
`status: not_found` is a free miss. Validation failures and upstream errors are also free. The
catalog-level `expect` rule lets the existing generic `per_success` settlement distinguish these
outcomes without a provider branch.

## Shared-plan boundary

The $27 monthly subscription has no vendor per-call price. `fx.yaml` therefore declares a
`treg_shared_plan` rate of $0.01 per ordinary successful record, with break-even at 2,700 calls per
month. This is treg's rate, not a claim that MoltSets sells individual $0.01 calls. The generic
credit conversion, margin, reserve, settle, release, recovery report, and BYOK precedence remain
unchanged.

Nine single-result tools are safe shared-key offers: business email and profile by name, reverse
email and profile lookup, three audience/hash conversions, email-to-profile, and IP-to-company.
They reserve one ordinary record and settle only when `status` is `ok`.

Eight tools are BYOK-only:

- People search, company search, and profile search can return variable record counts; profile
  search also has a free `count_only` mode.
- Four profile-to-email tools accept either one URL or batches of up to 100, whose entries can have
  mixed hit/miss outcomes.
- Phone lookup accepts the same batch shape and has two meters on a hit: one ordinary record plus
  one phone token.

The current generic response contract cannot count these variable or per-item outcomes, and the
request guard cannot safely promise single-only input for a body that documents both fields. They
remain faithful, unmetered BYOK relays rather than gaining MoltSets-specific call or money logic.
Phone pricing is displayed as the documented upper-bound replacement cost: $0.50 phone token plus
the $0.01 ordinary record, or $0.51 per hit. Misses cost neither meter.

## Routing and Arena

Verified adapters add four existing contract candidates: `people.email.find` by name/domain and
`people.enrich` by name/domain, email, or professional-profile URL. They map canonical identity
fields to the documented JSON bodies and map the MoltSets envelope back to the existing contract.
Direct responses are still relayed unchanged. No new routed contract or Arena branch exists;
ordinary adapter discovery supplies the candidates. Provider-specific audience and IP capabilities
stay direct tools because no compatible shared contract exists.

## Capacity and evidence

`collectors._moltsets` calls free `POST /get_account`, validates the standard envelope, and reports
the tighter of the rolling five-hour and weekly enrichment-record remainders. Its note includes
enrichment/search record and request headroom. A finite token balance is the fallback for token-bound
plans; `-1` means unlimited and is not misreported as a negative balance. Phone tokens are a separate
pool and are named but not combined with ordinary capacity.

The default policy is `rolling_quota / subscription / api`. The shared-key limiter uses the paid
plan's enrichment request allowance of 5,000 per five hours. Search has a lower allowance but all
search tools are BYOK-only, so it cannot consume this shared limiter. No auto-top-up, overflow route,
or exhaustion signature is claimed.

Live checks covered invalid auth, free account probes, validation errors, hits, misses, pagination,
batch mixtures, both plan states, all data paths, and the phone dual meter. They used 49 API requests
and two phone-token hits, within the task's hard cap. The paid plan showed enrichment limits of
1,000 records per five hours and 5,000 per week, search limits of 500 and 2,500 respectively, and
request limits five times the five-hour record pools. Ordinary hits moved the matching record pool;
misses, account calls, and errors did not. A phone hit moved both the enrichment-record pool and the
phone-token balance. Stored examples contain only reserved synthetic identities or empty results.
