---
title: hub pricing flexibility — the decisions, from the owner interview
status: settled 2026-09-14, no code written yet
---

# hub pricing flexibility — the decisions

Today a hub tool has one price: a flat `price_usd` the maker sets, charged once when a run
succeeds and paid to the maker as one `earned` block. The buyer also pays each catalog step's
real cost; a step on the maker's own tool runs on the maker's key and is not metered. This work
adds two more pricing modes so the price can change with the run.

This file is the record of a question-and-answer session with the owner on 2026-09-14, before any
design work. The questions are kept word for word. Under each one is the answer the owner approved.

## The frame the owner set
- Add pricing flexibility to the hub. The flat price is not enough.
- The other two questions (what is `data.csv`, where the script runs) were understanding, not gaps.
  Nothing about `data.csv` or the sandbox changes.

## Round 1 — the pricing model

**1. Which pricing modes do we add, beyond the flat price?**
Add two, keep flat. Mode `flat` (today). Mode `per_unit`: a price times a count the script returns.
Mode `cost_plus`: the maker earns a percent of the run's catalog step cost. The maker picks one
mode per tool version.

**2. In `per_unit` mode, what is one unit?**
The script returns an integer in a reserved output field named `units`. treg multiplies `units` by
the per-unit price. The maker's code sets `units`, usually the row count, but it can be anything
they bill for.

**3. Does a variable-price tool declare a maximum price per run?**
Yes, required. The manifest adds `max_price_usd` for `per_unit` and `cost_plus`. It is the most the
buyer can pay for the price part of one run.

**4. How do we hold the money when the price is not known at the start?**
Reserve `max_price_usd` at the start, run, then settle the real price and release the rest. This
keeps the reserve-then-settle rule exactly once, and the buyer's worst case is known before the run.

**5. In `cost_plus` mode, what is the maker's price based on?**
The maker sets `markup_percent`. The maker earns that percent of the run's catalog step cost.
Example: steps cost $0.20, markup 30 percent, the maker earns $0.06, the buyer pays $0.26 for the run.

**6. Where does the maker write the mode and its numbers?**
`recipe.json` gets a `pricing` block: `{mode, price_usd, per_unit_usd, markup_percent, max_price_usd}`.
treg reads only the fields the mode needs. A file with just `price_usd` still means `flat`.

**7. What does the buyer see before a run on the public page?**
The page shows the mode in words and the worst case. `flat`: "$X per run". `per_unit`: "$X per unit,
up to $Y per run". `cost_plus`: "the provider cost plus Z percent, up to $Y per run".

**8. When a variable run succeeds, how is the maker paid?**
The same as today. The final variable price settles to the maker as one `earned` block, in the same
one transaction as today. No new money entry.

**9. In `per_unit`, what stops a huge count from charging a huge price?**
The real price is the smaller of `units × per_unit_usd` and `max_price_usd`. The maker never earns
above their own declared maximum. This is also what makes reserving the maximum safe.

**10. Do existing flat-price tools change at all?**
No change. A recipe with just `price_usd` stays `flat`, reserved and settled exactly as today. The
new modes are opt-in through the `pricing` block.

## Round 2 — the edges

**1. What price applies if a `per_unit` script returns no `units`, or a bad value?**
The run fails with a clear error, and the maker earns nothing. `units` must be an integer of 0 or
more. A `units` of 0 succeeds and charges 0. Missing or not an integer fails the run.

**2. Is `cost_plus` allowed when a tool calls no catalog steps?**
Refuse it at publish. If the mode is `cost_plus` and `uses` names no catalog id, the publish fails
with a message. That maker should pick `flat` or `per_unit`.

**3. How does the publish check price the check run?**
No change. The check run skips the price part, same as today. It only proves the tool runs and
returns its declared fields. It never charges a price.

**4. Does the check verify the price fields, not just the output fields?**
Yes. The manifest validator checks the `pricing` block up front: the mode is valid, the numbers the
mode needs are present, `max_price_usd` is at least the per-unit price. For `per_unit`, the check run
also requires an integer `units` in the output. A tool with a broken price never goes live.

**5. Does the earnings report gain a column for the variable price?**
Add one column, `avg_price_micro`, the earned amount divided by the successful runs. No per-unit
breakdown, just the average price per successful run, so the maker sees how the variable price lands.

## The backlog, in the order it was named
(none named in this session)
