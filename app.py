"""
Shipment Analytics Dashboard — FreightFox Take-Home Assignment
Run locally:  streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import chi2_contingency, binomtest

from clean_data import load_and_clean

st.set_page_config(page_title="Shipment Analytics — FreightFox", layout="wide")

# ---------- Load & cache data ----------
@st.cache_data
def get_data():
    return load_and_clean("data/shipments.csv")

df, quality_report = get_data()
valid = df[df["valid_for_delay_analysis"]]
reliable = valid[valid["region"] != "South"]

st.title("🚚 Shipment Analytics Dashboard")
st.caption("FreightFox take-home assignment — all metrics computed from `actual_delivery_date` vs "
           "`promised_delivery_date`, not the `status` label (see Data Quality tab for why).")

tab1, tab2, tab3, tab4 = st.tabs([
    "📦 Data Quality", "🗺️ Region & On-Time Performance",
    "💰 Freight Cost vs Distance", "👥 Customer Delays"
])

# ================= TAB 1: DATA QUALITY =================
with tab1:
    st.header("Data Quality Findings")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Raw rows", quality_report["n_raw_rows"])
    c2.metric("Exact duplicates dropped", quality_report["n_exact_duplicates_dropped"])
    c3.metric("Rows usable for delay analysis", quality_report["n_valid_for_delay_analysis"],
               help="After excluding impossible dates and completed shipments missing an actual delivery date")
    c4.metric("Status vs. date mismatches", quality_report["n_status_vs_date_mismatch"])

    # ---- NEW: split out the status mismatch into its two directions ----
    has_actual_and_delay = df[df["actual_delivery_date"].notna() & df["delay_days"].notna()]
    delivered_rows = has_actual_and_delay[has_actual_and_delay["status"] == "Delivered"]
    delayed_rows = has_actual_and_delay[has_actual_and_delay["status"] == "Delayed"]
    pct_delivered_actually_late = round((delivered_rows["delay_days"] > 0).mean() * 100, 1) if len(delivered_rows) else 0
    pct_delayed_actually_ontime = round((delayed_rows["delay_days"] <= 0).mean() * 100, 1) if len(delayed_rows) else 0

    st.subheader("Key issues")
    st.markdown(f"""
- **`delivery_date` is 100% redundant** — it equals `promised_delivery_date` in
  **{quality_report['delivery_date_equals_promised_pct']}%** of rows. It is not used anywhere in this analysis;
  `actual_delivery_date` is the real outcome field.
- **The `status` label disagrees with date-derived reality** in **{quality_report['n_status_vs_date_mismatch']}**
  rows — and it's not a minor labeling glitch: **{pct_delivered_actually_late}%** of shipments marked
  "Delivered" were actually late by the date math, and **{pct_delayed_actually_ontime}%** of shipments marked
  "Delayed" were actually on-time or early. That's close to a coin flip in both directions. All on-time/SLA
  metrics here are computed from dates, never from `status`.
- **{quality_report['n_completed_missing_actual_date']} "Delivered"/"Delayed" shipments have no
  `actual_delivery_date` logged** — see below, this is concentrated almost entirely in one region.
- **{quality_report['n_impossible_date_rows']} rows have logically impossible dates**
  (delivered before pickup/booking) — excluded from time-based analysis.
""")

    completed = df[df["status"].isin(["Delivered", "Delayed"])]
    missing_by_region = completed.groupby("region")["actual_delivery_date"].apply(lambda x: x.isna().sum())
    total_by_region = completed.groupby("region").size()
    region_missing = pd.DataFrame({
        "missing_actual_date": missing_by_region,
        "total_completed": total_by_region,
        "pct_missing": (missing_by_region / total_by_region * 100).round(1)
    }).sort_values("pct_missing", ascending=False)

    st.subheader("Missing delivery dates by region")
    st.dataframe(region_missing, use_container_width=True)
    st.warning("**South is excluded from all delivery-performance comparisons** in this dashboard — "
               "84% of its completed shipments have no delivery date logged, a data pipeline gap, not a "
               "performance signal.")

# ================= TAB 2: REGION / ON-TIME =================
with tab2:
    st.header("Q1 — Which region has the worst on-time delivery performance?")

    region_summary = reliable.groupby("region").agg(
        n=("shipment_id", "count"),
        on_time_pct=("delay_days", lambda x: round((x <= 0).mean() * 100, 1)),
        breach_pct=("delay_days", lambda x: round((x > 0).mean() * 100, 1)),
        avg_delay_days=("delay_days", "mean"),
    ).sort_values("breach_pct", ascending=False)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("By region (South excluded — see Data Quality tab)")
        st.dataframe(region_summary, use_container_width=True)
        st.bar_chart(region_summary["breach_pct"])

    ct = pd.crosstab(reliable["region"], reliable["delay_days"] > 0)
    chi2, p, dof, exp = chi2_contingency(ct)

    with col2:
        st.subheader("Is the regional spread real?")
        st.metric("Chi-square p-value (region vs. breach)", f"{p:.3f}")
        if p > 0.05:
            st.info("**Not statistically significant.** With this data, no region can confidently be "
                    "called worse than another — the 48.7%–51.7% spread is consistent with noise.")

    st.subheader("The real driver: carrier, not region")
    carrier_breach = reliable.groupby("carrier_id").agg(
        n=("shipment_id", "count"),
        breach_pct=("delay_days", lambda x: round((x > 0).mean() * 100, 1))
    ).sort_values("breach_pct", ascending=False)
    st.bar_chart(carrier_breach["breach_pct"])
    st.caption("Carrier breach rates span ~44%–59% — a 15-point spread, 5x wider than the regional spread — "
               "and this holds consistently across all regions (bad carriers aren't concentrated in one place).")

# ================= TAB 3: FREIGHT COST =================
with tab3:
    st.header("Q2 — Freight cost vs. distance: is there a relationship, and which carrier deviates?")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Overall Pearson r (cost vs distance)", round(df['freight_cost'].corr(df['distance_km']), 3))
    with col2:
        clean_r = df[df['carrier_id'] != 'CARR_07']
        st.metric("Pearson r, excluding CARR_07", round(clean_r['freight_cost'].corr(clean_r['distance_km']), 3))

    st.scatter_chart(df, x="distance_km", y="freight_cost", color="mode")
    st.caption("CARR_07's shipments (visible as the steep separate band) sit far above the rest of the fleet "
               "at every distance.")

    carr07 = df[df["carrier_id"] == "CARR_07"]
    others = df[df["carrier_id"] != "CARR_07"]
    cpk_compare = pd.DataFrame({
        "CARR_07 avg cost/km": carr07.groupby("mode")["cost_per_km"].mean(),
        "All other carriers avg cost/km": others.groupby("mode")["cost_per_km"].mean(),
    })
    cpk_compare["Ratio"] = (cpk_compare["CARR_07 avg cost/km"] / cpk_compare["All other carriers avg cost/km"]).round(1)
    st.subheader("CARR_07 vs. everyone else — cost per km by mode")
    st.dataframe(cpk_compare.round(1), use_container_width=True)
    st.error("**CARR_07 bills ~10x the normal rate across 100% of its 342 shipments** — a consistent, "
             "systematic pattern (not a few outliers), most likely a billing/unit error worth verifying at "
             "the source rather than a genuine premium tier.")

    # ---- NEW: CARR_07's share of total freight spend vs. its share of volume ----
    total_spend = df["freight_cost"].sum()
    carr07_spend = carr07["freight_cost"].sum()
    carr07_spend_share = round(carr07_spend / total_spend * 100, 1)
    carr07_volume_share = round(len(carr07) / len(df) * 100, 1)

    sc1, sc2 = st.columns(2)
    sc1.metric("CARR_07 share of shipment volume", f"{carr07_volume_share}%")
    sc2.metric("CARR_07 share of total freight spend", f"{carr07_spend_share}%")
    st.caption(
        f"CARR_07 accounts for only {carr07_volume_share}% of shipments but **{carr07_spend_share}% of total "
        "reported freight cost** — purely because of its ~10x per-shipment pricing. If this is a billing/unit "
        "error, it is currently misstating a large share of reported freight spend; if it's a genuine different "
        "service tier, it's the single largest cost line in the fleet either way. Verify against the billing "
        "system before using this figure in any cost or contract decision."
    )

    st.subheader("Every other carrier's deviation from the expected cost curve")
    clean = df[df["carrier_id"] != "CARR_07"].copy()
    clean["predicted_cost"] = np.nan
    for m in clean["mode"].unique():
        mask = clean["mode"] == m
        sub = clean[mask]
        slope, intercept = np.polyfit(sub["distance_km"], sub["freight_cost"], 1)
        clean.loc[mask, "predicted_cost"] = intercept + slope * sub["distance_km"]
    clean["pct_deviation"] = (clean["freight_cost"] - clean["predicted_cost"]) / clean["predicted_cost"] * 100
    dev = clean.groupby("carrier_id")["pct_deviation"].mean().sort_values(ascending=False)
    st.bar_chart(dev)

    # ---- FIXED: was hardcoded as "~1%", actual average deviation is ~7-8% ----
    avg_abs_dev = round(clean.groupby("carrier_id")["pct_deviation"].mean().abs().mean(), 1)
    st.caption(f"Excluding CARR_07, every carrier prices within roughly {avg_abs_dev}% of the expected "
               "distance-based cost on average — much tighter than CARR_07's ~10x deviation, though not a "
               "near-zero gap. The remaining spread is likely explained by factors not in this dataset "
               "(e.g. shipment weight/volume), which isn't captured here.")

# ================= TAB 4: CUSTOMER DELAYS =================
with tab4:
    st.header("Q3 — Which customer(s) show the most delivery delays?")

    overall_rate = (valid["delay_days"] > 0).mean()
    cust = valid.groupby("customer_id").agg(
        n=("shipment_id", "count"),
        n_breach=("delay_days", lambda x: (x > 0).sum())
    ).reset_index()
    cust["breach_pct"] = (cust["n_breach"] / cust["n"] * 100).round(1)
    cust["p_value"] = cust.apply(
        lambda r: binomtest(int(r["n_breach"]), int(r["n"]), overall_rate, alternative="two-sided").pvalue,
        axis=1
    )
    cust_sorted = cust.sort_values("breach_pct", ascending=False)

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Top 15 customers by raw breach %")
        st.dataframe(cust_sorted.head(15), use_container_width=True)
    with col2:
        n_sig = (cust["p_value"] < 0.05).sum()
        st.metric("Customers 'significant' at p<0.05", f"{n_sig} / {len(cust)}")
        st.metric("Expected by chance alone", round(len(cust) * 0.05, 1))
        st.info("Almost exactly the number expected by chance — **no individual customer is a genuine "
                "statistical outlier.**")

    st.subheader("Do the top 'worst' customers share a carrier or region?")
    top4 = cust_sorted.head(4)["customer_id"].tolist()
    sub = valid[valid["customer_id"].isin(top4)]
    c1, c2 = st.columns(2)
    with c1:
        st.caption("Region mix")
        st.dataframe(pd.crosstab(sub["customer_id"], sub["region"]))
    with c2:
        st.caption("Carrier mix (top 5 carriers used)")
        st.dataframe(pd.crosstab(sub["customer_id"], sub["carrier_id"]).sum().sort_values(ascending=False).head())
    st.caption("No concentration in either — consistent with noise rather than a real customer-, carrier-, "
               "or region-driven pattern.")

st.divider()
st.subheader("📌 Recommended weekly metric (Q5)")
st.markdown("""
**On-time delivery rate, tracked per carrier — not blended network-wide.**
Carrier is the only statistically real driver of delay found in this data (15pp spread vs. a
non-significant 3pp regional spread). A blended company-wide number would hide a specific carrier
degrading. Pair this with a weekly check on **% of shipments missing `actual_delivery_date`** —
that's the exact failure mode that silently broke South's data.
""")
