# Business Answers

## Candidate name: Ankit Shaw
## Date: 22-08-2026

---

## Q1. Which region has the worst on-time delivery performance, and what's actually driving it?

**Answer:**

Region turns out not to be where the real problem is — the data doesn't support
ranking regions at all, and the actual driver is carrier, not geography.

- **South must be excluded from any ranking.** 84.5% of its shipments marked
  "Delivered" or "Delayed" have no `actual_delivery_date` logged at all
  (0% for every other region). Its apparent on-time rate is computed from only
  124 real records out of 971 total shipments — not comparable to other
  regions, and arguably a more urgent finding on its own: South's
  delivery-tracking pipeline is broken and needs to be fixed before its
  performance can be assessed at all.
- Among the four regions with trustworthy data, breach rates range narrowly
  from **48.7% (West) to 51.7% (Central)** — a 3-point spread — and a
  chi-square test on region vs. breach outcome returns **p = 0.66**, i.e.
  **not statistically significant**. We cannot claim any region is genuinely
  worse than another from this data.
- Average distance and mode mix are nearly identical across all four regions
  (avg distance 1,239–1,310 km; FTL/LTL/PTL split within 2 points of ~40/39/20%
  everywhere), so there's no structural reason to expect a regional effect.
- The real, robust signal is **carrier**: breach rates range from **44.7%
  (CARR_11) to 59.6% (CARR_02)** — a 15-point spread, five times wider than
  the regional spread — and this holds consistently across every region
  (poor carriers aren't concentrated in any one place).

**Caveat:** `region` in this dataset is derived from the shipment's *origin*
city, not the destination — worth flagging since it could be misread as a
delivery-side attribute.

**How you checked it (query/method):**

Computed `delay_days = actual_delivery_date - promised_delivery_date` for all
rows (never using the `status` column — see Q4). Filtered to
`valid_for_delay_analysis` rows (excludes impossible dates and completed
shipments with no logged actual date). Grouped by region to get on-time/breach
%, ran a chi-square test of independence (region × breach outcome) to check
significance, checked per-region average distance and mode mix to rule out a
structural explanation, then grouped by carrier within and across regions and
checked each carrier's regional volume share to confirm poor performers
weren't concentrated in a specific region. Full code in
`notebooks/shipment_analysis.ipynb`, Q1 section.

---

## Q2. Is there a relationship between freight cost and distance? Which carrier(s) deviate, and by how much?

**Answer:**

Yes — a strong, clean relationship, once one anomalous carrier is set aside.

- Freight cost is **near-perfectly linear** in distance once separated by mode
  (FTL ≈ ₹25/km, LTL ≈ ₹12/km, PTL ≈ ₹8/km), with **r = 0.98–0.99** across all
  three modes — but only after CARR_07 is excluded from the fit. With CARR_07
  included, the same per-mode correlation collapses to ~0.31–0.34, so
  isolating CARR_07 is what reveals the underlying relationship, not an
  incidental cleanup step.
- **CARR_07 is the one true outlier.** All 342 of its shipments — 100%, not a
  subset — bill at roughly 7–13x (mean 9.9x, std 1.4) the rate every other
  carrier charges for the same mode and distance. The tightness of that
  multiple points to a systematic issue — a cost field off by a factor of
  ~10, or a currency/unit mismatch — rather than genuine pricing variance.
  This should be verified against the actual billing system before it's
  treated as real cost data; it could also be a legitimately different
  service tier we don't have visibility into.
- **This isn't a rounding error in the data — it's material.** CARR_07
  accounts for only 6.8% of total shipment volume but **41.8% of total
  freight spend** (₹70.5M of ₹168.7M) purely because of this ~10x pricing.
  If this is a data/billing error, it is currently misstating a very large
  share of reported freight cost; if it's a real, different service tier, it
  is the single largest cost line in the fleet and deserves its own review
  either way.
- Every other carrier (14 of 15) prices within **~7–8%** of the expected cost
  curve once CARR_07 is excluded — a much tighter band than CARR_07, though
  not the near-zero deviation a first pass might suggest.

**How you checked it (query/method):**

Computed Pearson correlation between `freight_cost` and `distance_km`, both
overall and split by `mode`. Fit a per-mode linear regression (`np.polyfit`)
excluding CARR_07 and computed each shipment's % deviation from its predicted
cost. Computed CARR_07's cost-per-km as a multiple of the model-predicted cost
for its mode (7–13x, on every single shipment) and its share of total freight
spend vs. shipment volume. Full code in `notebooks/shipment_analysis.ipynb`,
Q2 section.

---

## Q3. Which customer(s) are experiencing the most delivery delays? Carrier-driven, region-driven, or something else?

**Answer:**

No individual customer is a statistically genuine outlier — this is the
important finding, not a ranked list.

- The customers with the highest raw breach rates (CUST_026, CUST_050,
  CUST_116, CUST_063 — 70–74%) look concerning at first glance.
- But out of 120 customers tested, a binomial test against the overall breach
  rate (50.0%) flags only **6 as "significant" at p<0.05** — and **6.0 is
  exactly the number you'd expect from random chance alone** when testing 120
  independent groups at that threshold (120 × 0.05 = 6.0). The observed count
  matching the chance-expected count almost exactly is the signature of no
  real effect, not a true finding.
- The top-raw-rate customers don't share a concentrated carrier or region
  either — their carrier and region mix is close to baseline proportions
  across the board.
- **So: it's neither carrier-driven nor region-driven for these specific
  customers — it's most consistent with sampling noise**, since each customer
  only has 18–44 shipments in this dataset. The real, robust levers remain
  what Q1/Q2 found: CARR_02's consistently elevated breach rate and CARR_07's
  cost anomaly.

**Recommendation:** don't act on "problem customers" identified from a single
5,000-row snapshot. Track customer-level breach rate on a rolling basis over a
longer window (more shipments per customer) before treating any one customer
as a genuine issue.

**How you checked it (query/method):**

Grouped valid shipments by `customer_id`, computed breach % per customer, then
ran a two-sided binomial test for each customer (observed breaches vs. overall
breach rate, given that customer's shipment count). Compared the count of
statistically significant customers (p<0.05) against the number expected by
chance alone at that threshold (n × 0.05). Cross-tabbed the top raw-rate
customers' carrier and region mix against baseline proportions to rule out a
hidden concentration. Full code in `notebooks/shipment_analysis.ipynb`, Q3
section.

---

## Q4. What data quality issues did you find, and how did you handle them?

**Answer:**

| Issue | Rows affected | Handling |
|---|---|---|
| Exact duplicate rows (same `shipment_id`, all columns identical) | 15 | Dropped |
| `delivery_date` is fully redundant — equals `promised_delivery_date` in 100% of rows | all 5,000 | Ignored the column entirely; used `actual_delivery_date` as the only source of truth for what actually happened |
| `status` label disagrees with date-derived reality | 1,742 rows (35% of all shipments) | All on-time/SLA metrics computed from `delay_days = actual_delivery_date - promised_delivery_date`, never from `status` |
| Completed status (Delivered/Delayed) but missing `actual_delivery_date` — 100% concentrated in South region | 682 | Excluded from delay analysis; flagged as a regional data-pipeline gap rather than imputed |
| `actual_delivery_date` earlier than `pickup_date` or `booking_date` (logically impossible) | 74 | Excluded from delay analysis |
| Missing `booking_date` / `pickup_date` | 71 / 87 | Left as-is — doesn't affect delay calculations |
| Origin city == destination city | 244 | Kept — plausibly legitimate intra-city moves, just noted |

The most consequential finding: **the `status` field cannot be trusted for
SLA analysis at all — it's barely better than a coin flip.** Among shipments
with a logged actual delivery date, **50.3% of "Delivered" shipments were
actually late** by the date math, and **51.4% of "Delayed" shipments were
actually on-time or early**. This isn't a minor labeling inconsistency; it
suggests `status` may be set at booking or dispatch time rather than updated
on actual delivery, or written by a separate process that doesn't reconcile
against real dates. Worth confirming directly with whoever owns that field —
but until then, every metric in this project is built from dates, not from
`status`.

Net effect of all cleaning/filtering: **3,444 of 5,000 rows (69%) are usable
for delay-based analysis.** This is disclosed wherever a delay-based metric is
shown, both in the notebook and the dashboard.

---

## Q5. If you could track exactly one metric weekly to catch support problems early, what would it be and why?

**Answer:**

**On-time delivery rate, computed from dates (not `status`), broken out by
carrier — not blended into a single company-wide number.**

The analysis above found the carrier effect is large and real (15-point
spread, consistent across every region), while region and customer effects
tested out as statistically indistinguishable from noise. A single blended
on-time percentage would average away exactly the signal that's actionable —
you can reassign volume away from an underperforming carrier; you can't "fix"
a region that isn't actually underperforming.

**Mandatory paired guardrail:** % of shipments missing a logged
`actual_delivery_date` within 7 days of their promised date. Without this
check running alongside the primary metric, the primary metric can quietly
become meaningless — which is exactly what happened to South, where the
underlying data pipeline broke and the on-time number kept reporting a
misleadingly good result with nothing catching it.

**Suggested action thresholds:** flag the guardrail if missing-data rate
exceeds ~10% for any region/carrier in a given week; flag a carrier if its
breach rate sits more than 5 points above the fleet median for two
consecutive weeks. These are starting points, not fixed rules — they should
be recalibrated once a few months of weekly data are available.

---

## Anything else you'd flag if this were a real dataset at FreightFox?

1. **South's delivery-tracking gap needs a root-cause conversation** with
   whoever owns that region's data pipeline — this looks more like a systems/
   process issue than a performance one, and it's currently invisible unless
   someone checks completeness directly.
2. **The `status` field's ~50% disagreement rate with actual dates needs its
   own root-cause investigation** — this is large enough that it's likely a
   systemic timing/process issue (e.g. status set at booking rather than
   delivery) rather than scattered data entry errors, and it should be fixed
   at the source rather than worked around indefinitely.
3. **CARR_07's pricing should be verified against the actual billing system
   immediately** — not as a minor cleanup item. A consistent ~10x multiple
   across every one of its 342 shipments is very unlikely to be genuine
   pricing variance, and it currently represents ~42% of total reported
   freight spend in this dataset. If it's a data/billing error, it is
   materially distorting cost reporting; if it's real, it's the single
   largest cost driver in the fleet and merits its own analysis.
4. **The dataset would benefit from a weight/volume field.** Freight cost
   still has ~7–8% unexplained variance even within mode+distance for the 14
   normal carriers, which a shipment size field would likely explain.
5. This is a snapshot of ~5,000 shipments across 120 customers and 15
   carriers — the Q3 "no significant customer effect" finding is a property
   of *this* sample size and should be re-tested as more data accumulates,
   not treated as a permanent conclusion.
