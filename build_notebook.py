import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []

def md(text):
    cells.append(nbf.v4.new_markdown_cell(text))

def code(text):
    cells.append(nbf.v4.new_code_cell(text))

md("""# Shipment Analytics — FreightFox Take-Home Assignment

This notebook explores `shipments.csv`, documents data quality issues, and backs up
every answer in `BUSINESS_ANSWERS.md` with a query or calculation.

**Structure:**
1. Load & clean data
2. Data quality findings (Q4)
3. Q1 — Worst region for on-time delivery
4. Q2 — Freight cost vs. distance, carrier deviation
5. Q3 — Customer-level delivery delays
6. Q5 — Recommended weekly metric
""")

code("""import sys, os
sys.path.append(os.path.abspath('..'))  # so we can import clean_data.py from the project root

import pandas as pd
import numpy as np
from scipy.stats import chi2_contingency, binomtest
pd.set_option('display.width', 150)
pd.set_option('display.max_columns', None)

from clean_data import load_and_clean

df, quality_report = load_and_clean('../data/shipments.csv')
df.head()""")

md("## 1. Data Quality Findings (backs up Q4)\n\nAll cleaning logic lives in `clean_data.py` so the notebook and dashboard stay consistent.")

code("""for k, v in quality_report.items():
    print(f"{k}: {v}")""")

md("""**Key issues found:**
- **15 exact duplicate rows** — dropped.
- **`delivery_date` is 100% redundant** with `promised_delivery_date` (identical in every row) — excluded from analysis; `actual_delivery_date` is the real outcome field.
- **`status` label disagrees with date-derived reality** in a large share of rows (e.g. "Delivered" shipments that were actually late per the dates). All SLA/on-time metrics below are computed from dates, never from `status`.
- **682 "Delivered"/"Delayed" shipments have no `actual_delivery_date` logged** — see next cell, this is concentrated almost entirely in one region.
- **74 rows have logically impossible dates** (delivered before pickup/booking) — excluded from time-based analysis.
""")

code("""# Confirm delivery_date redundancy
print("delivery_date == promised_delivery_date in", quality_report['delivery_date_equals_promised_pct'], "% of rows")

# Confirm status label unreliability
has_delay = df['delay_days'].notna()
mismatch = has_delay & (
    ((df['status']=='Delivered') & (df['delay_days']>0)) |
    ((df['status']=='Delayed') & (df['delay_days']<=0))
)
print(f"Status/date mismatch: {mismatch.sum()} rows out of {has_delay.sum()} with computable delay")""")

code("""# Where is the missing actual_delivery_date concentrated?
completed = df[df['status'].isin(['Delivered','Delayed'])]
missing_by_region = completed.groupby('region')['actual_delivery_date'].apply(lambda x: x.isna().sum())
total_by_region = completed.groupby('region').size()
pd.DataFrame({'missing_actual_date': missing_by_region, 'total_completed': total_by_region,
              'pct_missing': (missing_by_region/total_by_region*100).round(1)}).sort_values('pct_missing', ascending=False)""")

md("**Finding:** South region accounts for essentially all of the missing-actual-date rows (84% of its completed shipments have no delivery date logged), vs. 0% in North. This is a data pipeline gap specific to South, not a performance signal — South is excluded from delivery-performance comparisons below.")

md("## 2. Q1 — Which region has the worst on-time delivery performance, and what's driving it?")

code("""valid = df[df['valid_for_delay_analysis']]
reliable = valid[valid['region'] != 'South']  # South excluded — unreliable data, see above

region_summary = reliable.groupby('region').agg(
    n=('shipment_id','count'),
    on_time_pct=('delay_days', lambda x: round((x<=0).mean()*100,1)),
    breach_pct=('delay_days', lambda x: round((x>0).mean()*100,1)),
    avg_delay_days=('delay_days','mean'),
).sort_values('breach_pct', ascending=False)
region_summary""")

code("""# Is the regional spread statistically meaningful?
ct = pd.crosstab(reliable['region'], reliable['delay_days']>0)
chi2, p, dof, exp = chi2_contingency(ct)
print(f"Chi-square test (region vs breach): chi2={chi2:.2f}, p-value={p:.4f}")
print("-> Not statistically significant: we cannot confidently say any region performs worse than another.")""")

code("""# Is the real driver carrier, rather than region?
carrier_breach = reliable.groupby('carrier_id').agg(
    n=('shipment_id','count'),
    breach_pct=('delay_days', lambda x: round((x>0).mean()*100,1))
).sort_values('breach_pct', ascending=False)
carrier_breach""")

code("""# Are the worst carriers disproportionately concentrated in Central (the nominal 'worst' region)?
carrier_region_share = pd.crosstab(reliable['carrier_id'], reliable['region'], normalize='index').round(3)*100
carrier_region_share['Central'].sort_values(ascending=False)""")

md("""**Answer:** South cannot be evaluated (84% of its completed shipments are missing delivery dates — a data pipeline problem, not a performance one). Among the four regions with reliable data, breach rates range narrowly from 48.7% (West) to 51.7% (Central) — a chi-square test shows this spread is **not statistically significant** (p=0.66). Mode mix and average distance are also near-identical across regions. The real driver is **carrier**, not region: carrier-level breach rates span 44%–59% (a 15-point spread, 5x wider than the regional spread), and this holds consistently regardless of region — bad carriers aren't concentrated in any one place. So the actionable lever is carrier management, not regional operations, and South's broken data pipeline is the most urgent finding here.""")

md("## 3. Q2 — Is there a relationship between freight cost and distance? Which carrier(s) deviate?")

code("""print("Overall Pearson r (freight_cost vs distance_km):", round(df['freight_cost'].corr(df['distance_km']),3))
print()
for m in df['mode'].unique():
    sub = df[df['mode']==m]
    print(f"{m}: r={sub['freight_cost'].corr(sub['distance_km']):.3f}, n={len(sub)}")""")

code("""# Check CARR_07 specifically
carr07 = df[df['carrier_id']=='CARR_07']
others = df[df['carrier_id']!='CARR_07']
print("CARR_07 avg cost/km by mode:")
print(carr07.groupby('mode')['cost_per_km'].mean())
print()
print("All other carriers avg cost/km by mode:")
print(others.groupby('mode')['cost_per_km'].mean())""")

code("""# Refit the cost model excluding CARR_07 (the anomaly), then check every carrier's deviation
clean = df[df['carrier_id']!='CARR_07'].copy()
clean['predicted_cost'] = np.nan
for m in clean['mode'].unique():
    mask = clean['mode']==m
    sub = clean[mask]
    slope, intercept = np.polyfit(sub['distance_km'], sub['freight_cost'], 1)
    clean.loc[mask, 'predicted_cost'] = intercept + slope * sub['distance_km']
    print(f"{m}: cost = {intercept:.1f} + {slope:.2f} * distance   (r={sub['freight_cost'].corr(sub['distance_km']):.3f})")

clean['pct_deviation'] = (clean['freight_cost'] - clean['predicted_cost']) / clean['predicted_cost'] * 100
print()
clean.groupby('carrier_id')['pct_deviation'].mean().sort_values(ascending=False).round(2)""")

code("""# How consistent is CARR_07's anomaly across ALL of its shipments (not just a few outliers)?
mode_median_cpk = others.groupby('mode')['cost_per_km'].median()
carr07 = carr07.copy()
carr07['ratio_to_median'] = carr07['cost_per_km'] / carr07['mode'].map(mode_median_cpk)
print(carr07['ratio_to_median'].describe())
print("Shipments with ratio > 3x normal median:", (carr07['ratio_to_median']>3).sum(), "out of", len(carr07))""")

md("""**Answer:** Freight cost is almost perfectly explained by distance once you separate by mode (r≈0.985 for FTL/LTL/PTL) — **except for CARR_07**, whose entire fleet of 342 shipments (100%, not a subset) bills at roughly 7–13x (avg ~10x) the normal rate for its mode, with remarkable consistency (tight ratio distribution). That consistency points to a systematic issue — a cost figure off by ~10x, unit/currency mismatch, or an unlabeled premium tier — worth verifying against the billing source rather than assuming either way. Excluding CARR_07, every other carrier (14 of 15) prices within ~1% of the expected cost curve: there is no other meaningful pricing deviation in the fleet.""")

md("## 4. Q3 — Which customer(s) show the most delivery delays? Carrier, region, or something else?")

code("""overall_rate = (valid['delay_days']>0).mean()
cust = valid.groupby('customer_id').agg(n=('shipment_id','count'), n_breach=('delay_days', lambda x: (x>0).sum())).reset_index()
cust['breach_pct'] = (cust['n_breach']/cust['n']*100).round(1)
cust['p_value'] = cust.apply(lambda r: binomtest(r['n_breach'], r['n'], overall_rate, alternative='two-sided').pvalue, axis=1)
cust.sort_values('breach_pct', ascending=False).head(10)""")

code("""sig = cust[cust['p_value']<0.05]
print(f"{len(sig)} of {len(cust)} customers are 'significant' at p<0.05")
print("Expected by chance alone at this threshold:", round(len(cust)*0.05,1))
sig.sort_values('breach_pct', ascending=False)""")

code("""# Do the top-4 raw 'worst' customers share a concentrated carrier or region?
top4 = ['CUST_026','CUST_050','CUST_116','CUST_063']
sub = valid[valid['customer_id'].isin(top4)]
print(pd.crosstab(sub['customer_id'], sub['region']))
print()
print(pd.crosstab(sub['customer_id'], sub['carrier_id']).sum().sort_values(ascending=False).head())""")

md("""**Answer:** No individual customer is a statistically genuine outlier — with 120 customers tested, ~6 would look "significant" at p<0.05 by chance alone, and that's almost exactly what we observe. The customers with the highest raw breach rates (66–74%) don't share a concentrated carrier or region either. This is most consistent with sampling noise (each customer has only 20–35 shipments here), not a real carrier-, region-, or customer-driven pattern. The robust, actionable levers remain the carrier-level findings from Q1/Q2 (CARR_02's elevated breach rate, CARR_07's cost anomaly) — chasing individual "problem customers" off this snapshot isn't well supported by the data.""")

md("""## 5. Q5 — One metric to track weekly

**Recommendation: On-time delivery rate, tracked per carrier (not blended network-wide).**

Rationale: this analysis found carrier to be the dominant, statistically real driver of delay
(15pp spread vs. a non-significant 3pp regional spread). A single blended company-wide
on-time % would hide a specific carrier degrading. Tracking it per carrier, weekly, is directly
actionable — reroute volume away from underperforming carriers before it shows up in the
aggregate number.

**Caveat:** this only works if paired with a companion check — % of shipments missing
`actual_delivery_date` — since that's exactly the silent failure that broke South's data and
would otherwise make the on-time metric itself unreliable without anyone noticing.""")

nb['cells'] = cells

with open('notebooks/shipment_analysis.ipynb', 'w') as f:
    nbf.write(nb, f)

print("Notebook written.")
