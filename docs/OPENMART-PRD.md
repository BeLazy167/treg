# Openmart provider integration PRD

Status: implemented for review

## Goal

Add Openmart as a direct catalog provider. An agent can connect its own Openmart API key, call every documented API operation, inspect the provider page, and use the existing `companies.search` routed contract where the mapping is exact.

The change does not deploy, enable, or merge Openmart in production.

## Product surface

The provider page groups 17 operations:

- Search businesses, search IDs, and retrieve business records by Openmart or Google Place ID.
- Enrich companies and search brands.
- Start decision-maker, technology, company-email, and known-person batch tasks.
- Read batch status, list task IDs, and read task results.
- Create, check, and delete deny rules.
- Read the connected account credit balance.

Authentication uses a Bearer API key. A free credit-balance request verifies the connection and supplies capacity data.

## Safety and billing decision

All direct operations are BYOK-only.

Full search and lookup operations charge by returned record. The ID-only rate is not stated precisely. Company-email documentation and the live whole-credit meter disagree. The generic call runtime cannot count Openmart result envelopes. It also cannot assign delayed batch charges or task ownership to the submitting team without provider-specific logic.

Account reads and deny-rule operations are also BYOK-only. They expose or mutate private account state. Deny-rule writes forbid caching, and deletion stays clearly destructive.

The configured platform key supports connection metadata and capacity collection. It does not make any catalog operation platform-eligible. A team's own key still wins and is never metered by treg.

The credit conversion is $0.0298 per credit. It comes from the active $149 monthly subscription with 5,000 credits. There is no auto-top-up claim.

## Routing and Arena

`openmart.companies.search` maps exactly to the existing `companies.search` contract. The adapter forwards a text or name query, optional country, and limit. It returns companies, count, and cursor from the stored response fixture.

Company enrichment can return several location matches for one input. Selecting one would change the answer. It has no adapter. People operations are asynchronous and do not match the synchronous people contracts. They have no adapters or Arena branches.

## Verification evidence

Live checks used synthetic inputs and stayed below the 50-credit cap. They covered missing, bogus, and valid authentication; pagination; hits, misses, and validation errors; each synchronous data operation; all batch types; batch status; task listing; task results; deny checks; and balance reads.

Observed rules:

- Full business records used one credit per returned record. Empty and invalid requests used none.
- ID-only search moved no whole credit in small and paginated checks, but the documentation says reduced billing. Its price stays unknown.
- Technology results cost two credits.
- Decision-maker and known-person data use three credits for email and eight for phone.
- A successful company-email task moved one whole credit, while the public page states 0.3 credit. The catalog records the conflict.
- Task reads, deny checks, and balance reads used no credits.

Stored fixtures contain only synthetic IDs, domains, people, and balances. No raw live response or secret is in the repository.

## Acceptance criteria

- The catalog loads all 17 unique method and path pairs.
- Every operation has a stored sanitized response fixture and a direct provider-page entry.
- No operation is platform-eligible.
- A platform-only call stops before relay and creates no money entry.
- A connected team key relays unchanged and creates no treg money entry.
- The connection probe accepts a valid key and rejects an invalid key.
- The capacity collector validates a non-negative integer credit balance.
- The company-search adapter passes fixture verification and joins only the existing company-search route.
- The official logo renders on the provider page.
- Focused tests, catalog tests, import boundaries, context drift, and the full suite pass.

