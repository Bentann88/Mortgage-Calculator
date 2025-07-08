"""
Shared Mortgage Amortization Calculator — Streamlit Web App
===========================================================
A quick‑share browser tool that lets two borrowers experiment with
un‑equal monthly payments and a one‑time down‑payment.  Metrics,
full amortization schedule, and charts are generated instantly.

Run locally:
    streamlit run streamlit_app.py

Deploy (example):
    • Streamlit Community Cloud (free) – just push this file to a GitHub repo.
    • Render.com / Railway / etc. – add `streamlit run streamlit_app.py` as the
      start command.
"""

from __future__ import annotations
from typing import List, Tuple

import pandas as pd
import streamlit as st


def amortization_shared(
    loan_amount: float,
    annual_rate: float,
    term_years: int,
    monthly_contrib: List[float],
    downpayments: List[float],
    rounding: int = 2,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (full_schedule_df, yearly_rollup_df).

    * *monthly_contrib* and *downpayments* must be the same length (one per borrower).
    """
    n = len(monthly_contrib)
    if len(downpayments) != n:
        raise ValueError("monthly_contrib and downpayments must have the same length")

    m_rate = annual_rate / 12
    sched_payment = (
        loan_amount
        * (m_rate * (1 + m_rate) ** (term_years * 12))
        / ((1 + m_rate) ** (term_years * 12) - 1)
    )

    balance = loan_amount
    cum_equity = downpayments[:]
    pmt_no = 0
    rows = []

    while balance > 1e-6:  # loop until the mortgage is gone
        pmt_no += 1
        interest_due = balance * m_rate
        contrib_sum = sum(monthly_contrib)

        if contrib_sum < interest_due:  # guard against negative amortization
            raise ValueError("Monthly contributions are insufficient to cover interest.")

        interest_parts = [c / contrib_sum * interest_due for c in monthly_contrib]
        principal_parts = [c - i for c, i in zip(monthly_contrib, interest_parts)]
        principal_paid = sum(principal_parts)

        # final month: trim so balance never goes negative
        if principal_paid > balance:
            scale = balance / principal_paid
            principal_parts = [p * scale for p in principal_parts]
            principal_paid = balance

        balance -= principal_paid
        cum_equity = [e + p for e, p in zip(cum_equity, principal_parts)]

        rows.append(
            [pmt_no, round(principal_paid, rounding), round(interest_due, rounding),
             round(balance, rounding)]
            + [round(e, rounding) for e in cum_equity]
        )

    cols = [
        "Payment #", "Principal Paid", "Interest Paid", "Loan Balance",
        *[f"Equity Borrower {i+1}" for i in range(n)],
    ]
    schedule = pd.DataFrame(rows, columns=cols)

    # yearly roll‑up
    schedule["Year"] = (schedule["Payment #"] - 1) // 12 + 1
    group = {f"Equity Borrower {i+1}": "last" for i in range(n)}
    group["Loan Balance"] = "last"
    yearly = schedule.groupby("Year").agg(group).reset_index()

    # ownership share columns
    eq_cols = [c for c in yearly if c.startswith("Equity")]
    yearly["Total Equity"] = yearly[eq_cols].sum(axis=1)
    for c in eq_cols:
        yearly[c.replace("Equity", "Share")] = yearly[c] / yearly["Total Equity"]

    return schedule, yearly


# ──────────────────────────────── Streamlit UI ────────────────────────────────
st.set_page_config(page_title="Shared Mortgage Amortization", layout="wide")
st.title("🏡 Shared Mortgage Amortization Calculator")

with st.sidebar:
    st.header("Loan parameters")
    loan = st.number_input("Loan amount ($)", value=362_316, step=1_000, min_value=1.0)
    rate_pct = st.number_input("Annual interest rate (%)", value=6.125, step=0.01, min_value=0.01)
    years = st.number_input("Term (years)", value=30, step=1, min_value=1)

    st.header("Borrower inputs")
    contrib_a = st.number_input("Borrower A monthly contribution ($)", value=700, step=50, min_value=0.0)
    contrib_b = st.number_input("Borrower B monthly contribution ($)", value=2100, step=50, min_value=0.0)
    down_a = st.number_input("Borrower A down‑payment ($)", value=13_000, step=1_000, min_value=0.0)
    down_b = st.number_input("Borrower B down‑payment ($)", value=0, step=1_000, min_value=0.0)

    rounding = st.select_slider("Decimal places", options=[0, 1, 2, 3], value=2)

    clicked = st.button("📊 Calculate / Update", type="primary")

if clicked:
    try:
        schedule_df, yearly_df = amortization_shared(
            loan_amount=float(loan),
            annual_rate=float(rate_pct) / 100.0,
            term_years=int(years),
            monthly_contrib=[float(contrib_a), float(contrib_b)],
            downpayments=[float(down_a), float(down_b)],
            rounding=int(rounding),
        )
    except ValueError as e:
        st.error(str(e))
        st.stop()

    # ── Key metrics ───────────────────────────────────────────────────────────
    k1, k2, k3 = st.columns(3)
    months_to_payoff = int(schedule_df["Payment #"].iat[-1])
    k1.metric("Months to payoff", f"{months_to_payoff}", help="≈ {:.2f} years".format(months_to_payoff / 12))
    k2.metric("Total interest paid", f"${schedule_df['Interest Paid'].sum():,.2f}")

    last = yearly_df.iloc[-1]
    share_a = last[[c for c in yearly_df.columns if c.startswith("Share")]][0]
    share_b = last[[c for c in yearly_df.columns if c.startswith("Share")]][1]
    k3.metric("Final ownership", f"A {share_a*100:.1f}% / B {share_b*100:.1f}%")

    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────────
    st.subheader("Loan balance over time")
    st.line_chart(schedule_df.set_index("Payment #")["Loan Balance"], use_container_width=True)

    st.subheader("Equity shares by year")
    shares = yearly_df[[c for c in yearly_df.columns if c.startswith("Share")]].copy()
    shares.columns = ["Borrower A", "Borrower B"]
    shares.index = yearly_df["Year"]
    st.area_chart(shares, use_container_width=True, stack="normalize")

    # ── Data views ────────────────────────────────────────────────────────────
    st.subheader("Year‑end snapshot")
    st.dataframe(yearly_df, use_container_width=True, height=300)

    st.subheader("Full amortization schedule")
    st.dataframe(schedule_df, use_container_width=True, height=400)

    csv = schedule_df.to_csv(index=False).encode("utf‑8")
    st.download_button(
        "⬇️ Download schedule as CSV",
        data=csv,
        file_name="amortization_schedule.csv",
        mime="text/csv",
    )

else:
    st.info("Use the sidebar to set parameters, then hit **Calculate / Update**.")
