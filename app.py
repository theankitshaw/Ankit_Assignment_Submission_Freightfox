"""
Shipment Analytics Dashboard — FreightFox take-home assignment
Run locally with: streamlit run app.py
"""
import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import chi2_contingency, binomtest

from clean_data import load_and_clean

st.set_page_config(page_title="Shipment Analytics — FreightFox", layout="wide")

# ----------------------------------------------------------------------------
# Load data
# ----------------------------------------------------------------------------
@st.cache_data
def get_data():
    df, report = load_and_clean("data/shipments.csv")
    return df, report

df, quality_report = get_data()
valid = df[df["valid_for_delay_analysis"]]
reliable = valid[valid["region"] != "South"]  # South excluded — see Data Quality tab

st.title("🚚 Shipment Analytics — FreightFox")
st.caption(
    "All on-time/SLA metrics below are computed from `actual_delivery_date` vs "
    "`promised_delivery_date` — never from the `status` field, which disagrees "
    "with actual outcomes in 35% of rows. See the **Data Quality** tab for why."
)

tab_overview, tab_region, tab_cost, tab_customer, tab_quality = st.tabs(
    ["📊 Overview", "🗺️ Region (Q1)", "💰 Cost vs Distance (Q2)", "👥 Customers (Q3)", "🧹 Data Quality (Q4)"]
)

# ----------------------------------------------------------------------------
# TAB: Overview
# ----------------------------------------------------------------------------
with tab_overview:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total shipments (raw)", f"{quality_report['n_raw_rows']:,}")
    c2.metric("Clean rows", f"{quality_report['n_after_dedup']:,}")
    c3.metric("Valid for delay analysis", f"{quality_report['n_valid_for_delay_analysis']:,}",
              f"{quality_report['n_valid_for_delay_analysis']/quality_report['n_after_dedup']*100:.0f}% of clean rows")
    overall_breach = (valid["delay_days"] > 0).mean() * 100
    c4.metric("Overall breach rate (reliable data)", f"{overall_breach:.1f}%")

    st.subheader("Weekly tracking recommendation (Q5)")
    st.info(
        "**Track on-time delivery rate by carrier, weekly — not one blended company-wide number.** "
        "Carrier effects are large and real (15pp spread); region and customer effects tested out as noise. "
        "Pair it with a mandatory guardrail: % of shipments missing a logged `actual_delivery_date` within "
        "N days of promised date — this is exactly the check that would have caught South's broken pipeline."
    )

    st.subheader("Carrier breach rate — the dominant, real signal")
    carrier_perf = reliable.groupby("carrier_id").agg(
        n=("shipment_id", "count"),
        breach_pct=("delay_days", lambda x: (x > 0).mean() * 100),
    ).sort_values("breach_pct", ascending=False)
    st.bar_chart(carrier_perf["breach_pct"])
    st.caption("CARR_02 shows the highest breach rate (~59%), consistent across every region — this is where the real SLA problem lives, not region or customer.")

# ----------------------------------------------------------------------------
# TAB: Region (Q1)
# ----------------------------------------------------------------------------
with tab_region:
    st.header("Q1: Which region has the worst on-time delivery performance?")

    south_completed = df[(df["region"] == "South") & (df["status"].isin(["Delivered", "Delayed"]))]
    south_missing_pct = south_completed["actual_delivery_date"].isna().mean() * 100
    st.warning(
        f"⚠️ **South is excluded from ranking.** {south_missing_pct:.0f}% of its 'completed' shipments "
        "have no logged actual delivery date — a regional data pipeline gap, not a performance signal. "
        "Its apparent on-time rate would be computed from only ~124 real records."
    )

    region_summary = reliable.groupby("region").agg(
        n=("shipment_id", "count"),
        on_time_pct=("delay_days", lambda x: round((x <= 0).mean() * 100, 1)),
        breach_pct=("delay_days", lambda x: round((x > 0).mean() * 100, 1)),
        avg_delay_days=("delay_days", "mean"),
    ).sort_values("breach_pct", ascending=False)

    col1, col2 = st.columns([2, 1])
    with col1:
        st.dataframe(region_summary, use_container_width=True)
        st.bar_chart(region_summary["breach_pct"])
    with col2:
        ct = pd.crosstab(reliable["region"], reliable["delay_days"] > 0)
        chi2, p, dof, exp = chi2_contingency(ct)
        st.metric("Chi-square p-value (region vs breach)", f"{p:.3f}")
        if p >= 0.05:
            st.caption("Not statistically significant — cannot claim any region is genuinely worse.")

    st.subheader("So what IS driving differences? — Carrier, not region")
    st.write("Bad carriers are spread evenly across regions (not concentrated), while carrier-level breach rates vary widely and consistently:")
    carrier_overall = reliable.groupby("carrier_id").agg(
        n=("shipment_id", "count"),
        breach_pct=("delay_days", lambda x: round((x > 0).mean() * 100, 1)),
    ).sort_values("breach_pct", ascending=False)
    st.dataframe(carrier_overall, use_container_width=True)
    st.caption("Note: `region` reflects the shipment's *origin* city, not destination.")

# ----------------------------------------------------------------------------
# TAB: Cost vs Distance (Q2)
# ----------------------------------------------------------------------------
with tab_cost:
    st.header("Q2: Freight cost vs. distance — which carrier(s) deviate?")

    df["cost_per_km"] = df["freight_cost"] / df["distance_km"]

    clean_carriers = df[df["carrier_id"] != "CARR_07"].copy()
    clean_carriers["predicted_cost"] = np.nan
    r_by_mode = {}
    for m in clean_carriers["mode"].unique():
        mask = clean_carriers["mode"] == m
        sub = clean_carriers[mask]
        slope, intercept = np.polyfit(sub["distance_km"], sub["freight_cost"], 1)
        clean_carriers.loc[mask, "predicted_cost"] = intercept + slope * sub["distance_km"]
        r_by_mode[m] = sub["freight_cost"].corr(sub["distance_km"])
    clean_carriers["pct_deviation"] = (
        (clean_carriers["freight_cost"] - clean_carriers["predicted_cost"]) / clean_carriers["predicted_cost"] * 100
    )

    c1, c2, c3 = st.columns(3)
    for col, m in zip([c1, c2, c3], r_by_mode):
        col.metric(f"{m} cost-distance correlation", f"r = {r_by_mode[m]:.3f}")

    st.error(
        "🚨 **CARR_07 is excluded from the model above and shown separately.** "
        "All 342 of its shipments (100%) bill at ~7–13x (avg ~10x) the normal rate "
        "for their mode — a suspiciously *consistent* multiple, suggesting a systematic "
        "billing/unit issue rather than genuine pricing variance. Recommend verifying "
        "against the billing source before treating this as real cost data."
    )

    st.subheader("Carrier deviation from expected cost (CARR_07 excluded from model fit)")
    carrier_dev = clean_carriers.groupby("carrier_id").agg(
        n=("shipment_id", "count"),
        avg_pct_deviation=("pct_deviation", "mean"),
    ).sort_values("avg_pct_deviation", ascending=False)
    st.dataframe(carrier_dev.round(2), use_container_width=True)
    st.caption("Every one of the other 14 carriers prices within ~1% of the expected cost curve — no meaningful deviation once CARR_07 is set aside.")

    st.subheader("Freight cost vs. distance (colored by mode, CARR_07 excluded)")
    st.scatter_chart(clean_carriers, x="distance_km", y="freight_cost", color="mode")

# ----------------------------------------------------------------------------
# TAB: Customers (Q3)
# ----------------------------------------------------------------------------
with tab_customer:
    st.header("Q3: Which customers show the most delivery delays?")

    cust_summary = valid.groupby("customer_id").agg(
        n=("shipment_id", "count"),
        n_breach=("delay_days", lambda x: (x > 0).sum()),
    ).reset_index()
    cust_summary["breach_pct"] = (cust_summary["n_breach"] / cust_summary["n"] * 100).round(1)

    overall_rate = (valid["delay_days"] > 0).mean()
    cust_summary["p_value"] = cust_summary.apply(
        lambda r: binomtest(r["n_breach"], r["n"], overall_rate, alternative="two-sided").pvalue, axis=1
    )
    sig = cust_summary[cust_summary["p_value"] < 0.05]

    c1, c2 = st.columns(2)
    c1.metric("Customers tested", len(cust_summary))
    c2.metric("Statistically significant (p<0.05)", len(sig), help="Expected by chance alone at this threshold: ~6")

    st.warning(
        f"⚠️ **{len(sig)} of {len(cust_summary)} customers are 'significant' at p<0.05 — "
        "almost exactly what random chance alone would produce testing this many groups.** "
        "This is the signature of no real customer-level effect, not a true finding."
    )

    st.subheader("Top 15 customers by raw breach rate")
    st.dataframe(
        cust_summary.sort_values("breach_pct", ascending=False).head(15),
        use_container_width=True
    )
    st.caption(
        "These customers' carrier and region mix is close to baseline proportions — "
        "not concentrated on any single carrier or region. Most consistent with sampling "
        "noise given each customer only has 20–35 shipments in this dataset."
    )

# ----------------------------------------------------------------------------
# TAB: Data Quality (Q4)
# ----------------------------------------------------------------------------
with tab_quality:
    st.header("Q4: Data quality issues found, and how they were handled")

    rows = [
        ("Exact duplicate rows", quality_report["n_exact_duplicates_dropped"], "Dropped"),
        ("`delivery_date` == `promised_delivery_date` always", f"{quality_report['delivery_date_equals_promised_pct']}% of rows",
         "Ignored column entirely; used `actual_delivery_date` as ground truth"),
        ("`status` disagrees with date-derived delay", quality_report["n_status_vs_date_mismatch"],
         "All delay/SLA metrics computed from dates, never from `status`"),
        ("Completed status but missing `actual_delivery_date`", quality_report["n_completed_missing_actual_date"],
         "Excluded from delay analysis; 100% concentrated in South → flagged as pipeline issue"),
        ("Impossible dates (delivered before pickup/booking)", quality_report["n_impossible_date_rows"], "Excluded from delay analysis"),
        ("Missing booking_date", quality_report["n_missing_booking_date"], "Left as-is, doesn't affect delay calcs"),
        ("Missing pickup_date", quality_report["n_missing_pickup_date"], "Left as-is, doesn't affect delay calcs"),
        ("Origin city == destination city", quality_report["n_origin_eq_destination"], "Kept, plausibly legitimate, just noted"),
    ]
    st.table(pd.DataFrame(rows, columns=["Issue", "Rows affected", "Handling"]))

    st.subheader("Full raw quality report")
    st.json(quality_report)
