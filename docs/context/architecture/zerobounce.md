---
title: ZeroBounce — single email validation and account capacity
status: implemented; live authentication and response shapes verified
sources:
  - src/treg/catalog/zerobounce.yaml
  - src/treg/catalog/examples/zerobounce.people.email.verify.json
  - src/treg/catalog/examples/zerobounce.account.credits.json
  - src/treg/catalog/examples/zerobounce.account.usage.json
  - src/treg/catalog/adapters.yaml
  - src/treg/catalog/fx.yaml
  - src/treg/config.py
  - src/treg/oauth_providers.py
  - src/treg/domain/capacity/collectors.py
  - src/treg/domain/capacity/policy.py
  - src/treg/web/logos/zerobounce.svg
  - tests/conftest.py
  - tests/test_zerobounce.py
  - tests/test_archive.py
  - tests/test_key_providers.py
  - tests/test_oauth_providers_m3.py
  - tests/test_capacity_overflow_routes.py
related:
  - architecture/catalog.md
  - architecture/auth-secrets.md
  - architecture/money.md
  - interface/enrich-arena.md
  - ops/capacity.md
---

# ZeroBounce

ZeroBounce is a pasted-key email-validation provider at `https://api.zerobounce.net`. The selected
operations use an `api_key` query parameter. A team's connected key has priority and is unmetered.
`TREG_PLATFORM_KEY_ZEROBOUNCE` enables shared-key calls only when `zerobounce` is also in
`TREG_PLATFORM_PROVIDERS`.

## Safe first surface

The catalog exposes synchronous single validation and two account reads. Single validation is the
only platform-eligible tool. Credit balance and API usage are `own_account` tools because they
describe the credential owner's account.

The wider documented API includes batch and file validation, scoring, finder, domain search,
Activity Data, filters, and list evaluation. Batch is excluded because the endpoint needs `api_key`
in its JSON body. Live tests on the three official hosts accepted the documented body shape and
rejected the query-bound shape with HTTP 403. The shared relay does not add secrets to request
bodies. File lifecycles need multipart and binary contracts. Mutating filters and deletion are not
safe read operations. Finder has several result-dependent prices, and Activity Data has no stable
public per-call rate. The first surface does not guess at these contracts.

## Routing, Arena, and settlement

The verified adapter joins `zerobounce.people.email.verify` to the existing
`treg.people.email.verify` route. It maps the contract email to `queryParams.email`, returns the
provider status, and sets valid only for `status=valid`. Invalid, catch-all, spamtrap, abuse, and
do-not-mail are useful answers. Unknown or a missing status is a miss, so a waterfall can continue.
Arena discovers the same adapter without provider-specific code.

The supplied acquisition rate is $69 / 5,000 credits, or $0.0138 per credit. Official material says
a completed non-unknown single validation uses one credit and an unknown result uses none. The tool
therefore uses `per_success`. The existing verified-adapter settlement rule releases an unknown
hold and settles other HTTP-200 verdicts at 13,800 micro-USD. Common failure handling releases the
hold on upstream errors. No ZeroBounce branch is added to money code.

## Connection and capacity

The free connection probe reads API usage for a fixed closed date range. A missing or invalid key
returned HTTP 403; the supplied key returned HTTP 200. The balance route is not used for connection
validation because a bad key can return HTTP 200 with `Credits=-1`.

The capacity collector reads the free balance route. It accepts nonnegative integers and decimal
strings. It rejects Boolean, missing, malformed, and negative values. It also removes the query key
from error reporting by replacing upstream HTTP errors with a safe provider message. The policy is
`credits / auto_recharge / api` for vendor-managed Auto-Pay. treg reads the balance but does not
read or change the Auto-Pay setting. Shared-key calls start at the conservative policy rate of 25
requests per second.

## Live evidence and operations

Sandbox valid, invalid, and unknown requests returned the documented shapes. Real checks returned
an invalid mailbox and a role-based catch-all-related verdict. All checks showed zero balance delta.
That can reflect sandbox, cache, free, or refunded behavior, so pricing stays at the documented
retail replacement rate. Discovery spent no credits and remained below the 25-credit limit.

No empty-account response was forced and no overflow route is claimed. Production serving still
needs the normal platform key and provider allow-list configuration. This change does not enable
either. The committed examples contain no key, account balance, address from the account, or raw
live response.
