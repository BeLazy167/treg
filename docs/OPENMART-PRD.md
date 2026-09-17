# Openmart provider integration PRD

Status: implemented for review

## Goal

Add Openmart as a direct catalog provider. An agent can connect its own Openmart API key, use treg's metered key for proven synchronous data reads, inspect the provider page, and use the existing `companies.search` routed contract where the mapping is exact.

The change does not deploy, enable, or merge Openmart in production.

## Product surface

The provider page groups 16 operations:

- Search businesses, search IDs, and retrieve business records by Openmart or Google Place ID.
- Enrich companies and search brands.
- Start decision-maker, technology, company-email, and known-person batch tasks.
- Read batch status, list task IDs, and read task results.
- Create, check, and delete deny rules.

Authentication uses a Bearer API key. A free credit-balance request verifies the connection and supplies internal capacity data, but is not exposed as a caller tool.

## Safety and billing decision

Five synchronous data reads are BYOK + platform: business search, lookup by Openmart ID, lookup by Google Place ID, company enrichment, and brand search. A provider-neutral catalog declaration counts the documented response alternatives (root arrays, `data[]`, or ID-keyed maps), reserves from a bounded limit/input cardinality, and settles from returned records. A team's own key still wins and is never metered by treg.

Fast ID-only search is BYOK-only because its fractional rate is unresolved. All batch submissions and task reads are BYOK-only because ownership and charges span an asynchronous lifecycle. Deny-rule operations are BYOK-only because they expose or mutate private account state. The shared balance endpoint is internal only.

The credit conversion is $0.0298 per credit from the active $149 monthly subscription with 5,000 credits. Search/enrichment is 0.3 credit per returned record ($0.00894 raw); people data is 3 credits/email and 8/phone; technology detection is 2 credits when technologies are found. There is no auto-top-up claim.

## Routing and Arena

`openmart.companies.search` maps exactly to the existing `companies.search` contract. The adapter forwards a text or name query, optional country, and limit. It returns companies, count, and cursor from the stored response fixture.

Company enrichment can return several location matches for one input. Selecting one would change the answer. It has no adapter and is not in Enrich Arena. People operations are asynchronous and do not match the synchronous people contracts. They have no adapters or Arena branches.

## Verification evidence

Live checks used synthetic inputs and stayed below the 50-credit cap. They covered missing, bogus, and valid authentication; pagination; hits, misses, and validation errors; each synchronous data operation; all batch types; batch status; task listing; task results; deny checks; and balance reads.

Observed rules:

- The dashboard prices search/enrichment at 0.3 credit per returned record. A one-result search and a three-result search each reduced the displayed integer balance by one, and neither response carried usage/cost metadata. Balance deltas therefore hide fractions and must never settle calls.
- ID-only search moved no whole credit in small and paginated checks, but the documentation says reduced billing. Its price stays unknown.
- Technology results cost two credits.
- Decision-maker and known-person data use three credits for email and eight for phone.
- Company email is documented at 0.3 credit; its async lifecycle remains BYOK-only.
- Task reads, deny checks, and balance reads used no credits.

Stored fixtures contain only synthetic IDs, domains, people, and balances. No raw live response or secret is in the repository.

## Acceptance criteria

- The catalog loads all 16 caller-facing unique method and path pairs; balance stays internal.
- Every operation has a stored sanitized response fixture and a direct provider-page entry.
- Exactly five proven synchronous data operations are platform-eligible.
- The unpriced fast-ID operation stops before relay and creates no money entry.
- Platform synchronous calls reserve by bounded request size and settle by the declared returned-record count, including empty 2xx responses at zero.
- A connected team key relays unchanged and creates no treg money entry.
- The connection probe accepts a valid key and rejects an invalid key.
- The capacity collector validates a non-negative integer credit balance.
- The company-search adapter passes fixture verification and joins only the existing company-search route.
- The official logo renders on the provider page.
- Focused tests, catalog tests, import boundaries, context drift, and the full suite pass.
