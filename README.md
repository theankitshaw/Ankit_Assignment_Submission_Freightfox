# Shipment Analytics — FreightFox Take-Home Assignment

Live dashboard: **[add your Streamlit Cloud URL here after deploying]**

## What's in this repo

```
.
├── data/shipments.csv              # raw dataset (as provided)
├── clean_data.py                   # single source of truth for cleaning + feature logic
├── notebooks/shipment_analysis.ipynb  # full exploration + all 5 business questions, worked
├── app.py                          # Streamlit dashboard
├── requirements.txt
├── docs/BUSINESS_ANSWERS.md        # written answers to the 5 business questions
└── README.md                       # this file
```

## Setup — run locally

```bash
git clone <this-repo-url>
cd shipment_analytics
pip install -r requirements.txt

# Run the analysis notebook
jupyter notebook notebooks/shipment_analysis.ipynb

# Run the dashboard
streamlit run app.py
```

## Deploy (Streamlit Community Cloud)

1. Push this repo to GitHub (public).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub.
3. "New app" → select this repo → main file path: `app.py` → Deploy.
4. Copy the generated URL into this README and into your submission.

## Approach

**Cleaning logic lives in one place.** `clean_data.py` is imported by both the
notebook and the dashboard, so the two can never disagree on how a metric is
defined — a common failure mode in take-homes where the notebook says one thing
and the dashboard shows another.

**I didn't trust the `status` column, and that changed the whole analysis.**
Early exploration showed `status` disagrees with what actually happened (computed
from `actual_delivery_date` vs `promised_delivery_date`) in 35% of rows — a
"Delivered" shipment is about as likely to have actually been late as a "Delayed"
one is to have actually been on time. Every on-time/SLA number in this project is
computed from dates, never from the status label.

**I let the data talk me out of my first answer more than once.** The most
interesting findings here weren't the ones the business questions were fishing
for on the surface:

- Q1 initially looked like "Central is the worst region" — until a chi-square test
  showed that spread isn't statistically significant, and the real, much larger
  effect is carrier-level, not regional. South, meanwhile, isn't underperforming
  at all — its data pipeline is silently broken (84% of "completed" shipments
  there have no delivery date logged).
- Q2 initially looked like a weak, noisy cost-distance relationship (r≈0.3) —
  until isolating one carrier (CARR_07, pricing at a suspiciously consistent
  ~10x multiple across literally every shipment) revealed the true relationship
  is nearly perfect (r=0.985) for the other 14 carriers.
- Q3's "worst customers" turned out to be statistically indistinguishable from
  noise once I accounted for testing 120 customers at once — a good reminder
  that eyeballing a sorted table is how false positives get shipped as insights.

**Caveats and things I'd want to verify with the FreightFox team before acting:**
- CARR_07's pricing anomaly should be checked against the actual billing system —
  it could be a data pipeline bug or a legitimately different service tier we
  don't have visibility into.
- South's missing-data issue needs a root-cause conversation with whoever owns
  that region's delivery tracking, since we can't say anything about its real
  performance until it's fixed.
- All analysis is a snapshot of ~5,000 shipments; the Q3 customer-level noise
  finding specifically would benefit from a longer rolling window before ruling
  it out completely.
