"""
clean_data.py
Shared cleaning + feature logic for shipments.csv.
Used identically by the analysis notebook and the Streamlit dashboard
so both stay in sync on how metrics are defined.
"""

import pandas as pd
import numpy as np

DATE_COLS = ["booking_date", "pickup_date", "delivery_date",
             "promised_delivery_date", "actual_delivery_date"]


def load_and_clean(path="data/shipments.csv"):
    """
    Returns:
        df_clean : DataFrame with duplicates removed, dates parsed,
                    delay_days computed, and quality flags added.
        quality_report : dict summarizing issues found (for BUSINESS_ANSWERS.md / dashboard).
    """
    df = pd.read_csv(path)
    n_raw = len(df)

    # --- Parse dates ---
    for c in DATE_COLS:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    # --- 1. Exact duplicate rows ---
    n_dupes = df.duplicated().sum()
    df = df.drop_duplicates().reset_index(drop=True)

    # --- 2. delivery_date is redundant (== promised_delivery_date always) ---
    # Confirmed: mean/std of (delivery_date - promised_delivery_date) == 0 in exploration.
    # We drop it from analysis rather than treat it as "actual" delivery.
    delivery_date_matches_promised = (
        (df["delivery_date"] - df["promised_delivery_date"]).dt.days == 0
    ).mean()

    # --- 3. Compute ground-truth delay from dates, not from `status` label ---
    df["delay_days"] = (df["actual_delivery_date"] - df["promised_delivery_date"]).dt.days

    # --- 4. Flag logically impossible rows: delivered before pickup/booking ---
    df["flag_impossible_dates"] = (
        (df["actual_delivery_date"] < df["pickup_date"]) |
        (df["actual_delivery_date"] < df["booking_date"])
    )
    n_impossible = df["flag_impossible_dates"].sum()

    # --- 5. Flag "completed" status rows with missing actual_delivery_date ---
    df["flag_missing_actual_when_completed"] = (
        df["status"].isin(["Delivered", "Delayed"]) & df["actual_delivery_date"].isna()
    )
    n_missing_actual_completed = df["flag_missing_actual_when_completed"].sum()

    # --- 6. Status label vs date-derived reality mismatch ---
    has_delay = df["delay_days"].notna()
    df["is_late_by_date"] = np.where(has_delay, df["delay_days"] > 0, np.nan)
    status_vs_date_mismatch = (
        has_delay & (
            ((df["status"] == "Delivered") & (df["delay_days"] > 0)) |
            ((df["status"] == "Delayed") & (df["delay_days"] <= 0))
        )
    ).sum()

    # --- 7. Valid rows for delay-based analysis (Q1, Q2 timing side, Q3) ---
    # Exclude: no delay_days computable, impossible dates, missing-actual-but-completed
    df["valid_for_delay_analysis"] = (
        df["delay_days"].notna() &
        (~df["flag_impossible_dates"]) &
        (~df["flag_missing_actual_when_completed"])
    )

    # --- 8. cost per km (for Q2), guard divide by zero ---
    df["cost_per_km"] = np.where(df["distance_km"] > 0,
                                  df["freight_cost"] / df["distance_km"],
                                  np.nan)

    quality_report = {
        "n_raw_rows": n_raw,
        "n_exact_duplicates_dropped": int(n_dupes),
        "n_after_dedup": len(df),
        "delivery_date_equals_promised_pct": round(delivery_date_matches_promised * 100, 1),
        "n_impossible_date_rows": int(n_impossible),
        "n_completed_missing_actual_date": int(n_missing_actual_completed),
        "n_status_vs_date_mismatch": int(status_vs_date_mismatch),
        "n_missing_booking_date": int(df["booking_date"].isna().sum()),
        "n_missing_pickup_date": int(df["pickup_date"].isna().sum()),
        "n_valid_for_delay_analysis": int(df["valid_for_delay_analysis"].sum()),
        "n_origin_eq_destination": int((df["origin_city"] == df["destination_city"]).sum()),
    }

    return df, quality_report


if __name__ == "__main__":
    df, report = load_and_clean()
    print("Quality report:")
    for k, v in report.items():
        print(f"  {k}: {v}")
