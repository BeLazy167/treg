---
title: Openmart — business search, asynchronous enrichment and BYOK boundaries
status: shipped
sources:
  - src/treg/catalog/openmart.yaml
  - src/treg/catalog/examples/openmart.businesses.search.json
  - src/treg/catalog/examples/openmart.businesses.search.ids.json
  - src/treg/catalog/examples/openmart.businesses.lookup.openmart.json
  - src/treg/catalog/examples/openmart.businesses.lookup.google-place.json
  - src/treg/catalog/examples/openmart.companies.enrich.json
  - src/treg/catalog/examples/openmart.companies.search.json
  - src/treg/catalog/examples/openmart.people.find.batch.json
  - src/treg/catalog/examples/openmart.technologies.find.batch.json
  - src/treg/catalog/examples/openmart.companies.email.find.batch.json
  - src/treg/catalog/examples/openmart.people.enrich.batch.json
  - src/treg/catalog/examples/openmart.tasks.batch.status.json
  - src/treg/catalog/examples/openmart.tasks.batch.ids.json
  - src/treg/catalog/examples/openmart.tasks.get.json
  - src/treg/catalog/examples/openmart.deny-rules.create.json
  - src/treg/catalog/examples/openmart.deny-rules.check.json
  - src/treg/catalog/examples/openmart.deny-rules.delete.json
  - src/treg/catalog/examples/openmart.account.balance.json
  - src/treg/catalog/adapters.yaml
  - src/treg/catalog/fx.yaml
  - src/treg/oauth_providers.py
  - src/treg/providers.py
  - src/treg/config.py
  - src/treg/domain/capacity/collectors.py
  - src/treg/domain/capacity/policy.py
  - src/treg/web/logos/openmart.svg
  - tests/test_openmart.py
  - tests/test_capacity_overflow_routes.py
  - tests/conftest.py
  - tests/test_key_providers.py
  - tests/test_mcp.py
  - tests/test_oauth_providers_m3.py
related:
  - architecture/catalog.md
  - architecture/auth-secrets.md
  - architecture/money.md
  - interface/enrich-arena.md
  - ops/capacity.md
---

# Openmart

Openmart is a pasted Bearer-key enrichment provider at `https://api.openmart.ai`. The free
`GET /api/v2/credit-balance` operation verifies a connection and supplies the capacity collector.
The catalog exposes every documented API operation: business and brand search, two ID lookups,
company enrichment, four batch submission types, three task reads, three deny-rule operations, and
the credit balance.

## Shared-key boundary

Every Openmart operation is BYOK-only. This is one boundary with three reasons:

- Search and lookup costs depend on returned records. The generic runtime does not count Openmart
  result envelopes.
- Batch submission and task reads form an asynchronous lifecycle. Charges can land after submit,
  results can mix outcomes, and task ownership belongs to the key that created the batch.
- Balance and deny-rule operations read or mutate private account state. A shared key would expose
  one team's state to another. Deny writes also forbid caching.

`platform_key_openmart` exists so the standard provider configuration and capacity machinery can
hold the optional account key. It does not make a catalog operation eligible. The provider
allow-list remains the production switch. This integration does not change that switch.

The catalog records the active subscription conversion of $149 for 5,000 credits, or $0.0298 per
credit. It does not claim auto-top-up. The fast ID-only rate stays unknown because documentation
says reduced billing while small live checks moved no whole credit. The company-email rate also
stays explicitly uncertain because the public 0.3-credit statement did not match the whole-credit
account meter in one successful live task.

## Routing and Arena

Only `openmart.companies.search` has an adapter. It maps a canonical text or name, optional country,
and limit to brand search. Its stored fixture verifies companies, count, and cursor output. The
child remains BYOK-routed because the direct tool is not platform-eligible.

Company enrichment can return several location matches. Choosing the first would change semantics,
so it does not join `companies.enrich`. People operations are asynchronous and do not join the
synchronous people routes or Arena tasks. No new routed contract or Arena branch is added.

## Capacity and evidence

`collectors._openmart` calls the free balance endpoint, accepts only a non-negative integer balance,
and reports subscription credits with the current period end when available. The default policy is
`credits / subscription / api`. A provider-wide 15 requests per second policy uses the strictest
published endpoint-family limit. Direct BYOK calls bypass shared-key smoothing.

Live checks used synthetic inputs and stayed within the task cap. They covered authentication,
search pagination, hits, misses, validation, every data operation, the full batch lifecycle, deny
checks, and balance reads. Stored examples use reserved synthetic identities only. No key or raw
live response is stored.
