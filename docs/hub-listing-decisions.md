---
title: hub listing and public run log — the decisions
status: settled 2026-09-16, mockup https://claude.ai/artifact/MW5m46BcxTtcrc7ghcNEG7
---

# hub listing and public run log — the decisions

Two additions Jason asked for on 2026-09-15: a way to list a hub tool in the catalog (until now
every hub tool was unlisted by decision), and a public log of the calls a tool has served. Five
decisions, approved by the owner on 2026-09-16 from the mockup.

**1. Listing is a switch on the tool, not a field in recipe.json.**
Default off. The maker flips it with `treg hub list <id>` / `treg hub unlist <id>`,
`PATCH /hub/tools/{id} {"listed": true}`, or the dashboard switch. No version bump, like a price
change. It is a distribution choice, not part of the recipe contract.

**2. A listed tool appears in catalog search; an unlisted one stays callable by id only.**
In the same results, ranked by relevance, no boost, marked `hub` with the maker's team, the price
label and the 30-day ok rate. `catalog_search` over MCP returns it too. Only `live` versions are
ever listed; failed and retired never appear.

**3. The public log shows outcomes, never people or data.**
Per run: time, ok or failed, duration, steps, units (per_unit), the price paid. Never who called,
never the inputs, never the output. The last 20 runs, and runs per day for 30 days.

**4. The maker can switch the public log off.**
Default on. Failed runs are shown too: the page already shows health, and a log that hides
failures is not a log.

**5. The agent page gets the same log.**
`/hub/<id>.md` carries the run table, so an agent can judge a tool before calling it, the same
way it reads the price.
