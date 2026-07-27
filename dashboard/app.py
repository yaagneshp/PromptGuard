import pandas as pd
import plotly.express as px
import streamlit as st

from auth import require_password
from colors import PLATFORM_COLORS, PLATFORM_ORDER, RISK_LEVEL_ORDER, SEQUENTIAL_BLUE, STATUS_COLORS
from db import load_compliance_tags, load_detections, load_events

st.set_page_config(page_title="PromptGuard Dashboard", layout="wide")
require_password()

st.title("PromptGuard Dashboard")


@st.cache_data(ttl=10)
def get_data():
    return load_events(), load_detections(), load_compliance_tags()


events, detections, compliance_tags = get_data()

if events.empty:
    st.info("No events captured yet. Submit a prompt via the extension, or POST to /events/ingest.")
    st.stop()

# --- Sidebar filters (shared across all tabs) ---
st.sidebar.header("Filters")

platforms_present = [p for p in PLATFORM_ORDER if p in events["platform"].unique()]
selected_platforms = st.sidebar.multiselect("Platform", platforms_present, default=platforms_present)

users_present = sorted(events["external_user_id"].unique())
selected_users = st.sidebar.multiselect("User", users_present, default=users_present)

risk_levels_present = [r for r in RISK_LEVEL_ORDER if r in events["risk_level"].unique()]
selected_risk_levels = st.sidebar.multiselect("Risk level", risk_levels_present, default=risk_levels_present)

policy_only = st.sidebar.checkbox("Policy violations only", value=False)

min_date = events["received_at"].min().date()
max_date = events["received_at"].max().date()
date_range = st.sidebar.date_input(
    "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
)

filtered = events[
    events["platform"].isin(selected_platforms)
    & events["external_user_id"].isin(selected_users)
    & events["risk_level"].isin(selected_risk_levels)
].copy()

if policy_only:
    filtered = filtered[filtered["policy_violation"]]

if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[(filtered["received_at"].dt.date >= start) & (filtered["received_at"].dt.date <= end)]

filtered_ids = set(filtered["event_id"])
filtered_detections = detections[detections["event_id"].isin(filtered_ids)]
filtered_tags = compliance_tags[compliance_tags["event_id"].isin(filtered_ids)]

tab_overview, tab_audit, tab_trends = st.tabs(["Overview", "Audit Log", "Trends & Compliance"])

# ------------------------------------------------------------------
# Overview: usage statistics
# ------------------------------------------------------------------
with tab_overview:
    if filtered.empty:
        st.warning("No events match the current filters.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total events", len(filtered))
        col2.metric("Policy violations", int(filtered["policy_violation"].sum()))
        col3.metric("Avg combined score", f"{filtered['combined_score'].mean():.1f}")
        high_critical_pct = (filtered["risk_level"].isin(["high", "critical"]).mean()) * 100
        col4.metric("High/critical %", f"{high_critical_pct:.0f}%")

        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            st.subheader("Events by platform")
            by_platform = filtered.groupby("platform", as_index=False).size()
            fig = px.bar(
                by_platform,
                x="platform",
                y="size",
                color="platform",
                color_discrete_map=PLATFORM_COLORS,
                category_orders={"platform": platforms_present},
                labels={"size": "Events", "platform": "Platform"},
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, width="stretch")

        with chart_col2:
            st.subheader("Risk level distribution")
            by_risk = filtered.groupby("risk_level", as_index=False).size()
            fig = px.bar(
                by_risk,
                x="risk_level",
                y="size",
                color="risk_level",
                color_discrete_map=STATUS_COLORS,
                category_orders={"risk_level": RISK_LEVEL_ORDER},
                labels={"size": "Events", "risk_level": "Risk level"},
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, width="stretch")

        st.subheader("Per-user breakdown")
        per_user = (
            filtered.groupby("external_user_id")
            .agg(
                events=("event_id", "count"),
                avg_score=("combined_score", "mean"),
                policy_violations=("policy_violation", "sum"),
                platforms_used=("platform", lambda s: ", ".join(sorted(s.unique()))),
            )
            .reset_index()
            .sort_values("events", ascending=False)
        )
        per_user["avg_score"] = per_user["avg_score"].round(1)
        st.dataframe(per_user, width="stretch", hide_index=True)

# ------------------------------------------------------------------
# Audit log
# ------------------------------------------------------------------
with tab_audit:
    if filtered.empty:
        st.warning("No events match the current filters.")
    else:
        display_cols = [
            "event_id",
            "received_at",
            "platform",
            "external_user_id",
            "risk_level",
            "combined_score",
            "policy_violation",
            "redacted_text",
        ]
        st.dataframe(
            filtered[display_cols].sort_values("received_at", ascending=False),
            width="stretch",
            hide_index=True,
        )

        csv_bytes = filtered[display_cols].to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download filtered audit log (CSV)",
            data=csv_bytes,
            file_name="promptguard_audit_log.csv",
            mime="text/csv",
        )

        st.subheader("Event detail")
        selected_event_id = st.selectbox("Select an event ID to inspect", filtered["event_id"].tolist())
        if selected_event_id is not None:
            event_detections = filtered_detections[filtered_detections["event_id"] == selected_event_id]
            event_tags = filtered_tags[filtered_tags["event_id"] == selected_event_id]

            detail_col1, detail_col2 = st.columns(2)
            with detail_col1:
                st.markdown("**Detections**")
                if event_detections.empty:
                    st.caption("None.")
                else:
                    st.dataframe(
                        event_detections[["category", "match_count", "detector_source"]],
                        hide_index=True,
                        width="stretch",
                    )
            with detail_col2:
                st.markdown("**GDPR compliance tags**")
                if event_tags.empty:
                    st.caption("None.")
                else:
                    st.dataframe(
                        event_tags[["category", "gdpr_article", "rationale"]],
                        hide_index=True,
                        width="stretch",
                    )

# ------------------------------------------------------------------
# Trends & compliance
# ------------------------------------------------------------------
with tab_trends:
    if filtered.empty:
        st.warning("No events match the current filters.")
    else:
        st.subheader("Events over time by risk level")
        trend = filtered.copy()
        # Cast to string so Plotly treats each day as a category rather than
        # a continuous time axis - with a single day of data (common in
        # early testing), a continuous date axis collapses to a near-zero
        # range and renders meaningless sub-second tick labels.
        trend["day"] = trend["received_at"].dt.date.astype(str)
        trend_grouped = trend.groupby(["day", "risk_level"], as_index=False).size()
        # Stacked bar rather than area: an area chart needs >=2 x-points to
        # draw a visible filled shape, so it renders as an empty plot for
        # the (common, early-testing) case of a single day of data. Bars
        # render correctly regardless of how many distinct days exist.
        fig = px.bar(
            trend_grouped,
            x="day",
            y="size",
            color="risk_level",
            color_discrete_map=STATUS_COLORS,
            category_orders={"risk_level": RISK_LEVEL_ORDER},
            labels={"size": "Events", "day": "Date", "risk_level": "Risk level"},
        )
        fig.update_xaxes(type="category")
        st.plotly_chart(fig, width="stretch")

        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            st.subheader("PII category frequency")
            if filtered_detections.empty:
                st.caption("No detections in the current selection.")
            else:
                cat_counts = (
                    filtered_detections.groupby("category")["match_count"]
                    .sum()
                    .reset_index()
                    .sort_values("match_count", ascending=True)
                )
                fig = px.bar(
                    cat_counts,
                    x="match_count",
                    y="category",
                    orientation="h",
                    labels={"match_count": "Matches", "category": "Category"},
                )
                fig.update_traces(marker_color=SEQUENTIAL_BLUE)
                st.plotly_chart(fig, width="stretch")

        with chart_col2:
            st.subheader("GDPR article breakdown")
            if filtered_tags.empty:
                st.caption("No compliance tags in the current selection.")
            else:
                article_counts = (
                    filtered_tags.groupby("gdpr_article")["event_id"]
                    .nunique()
                    .reset_index(name="events")
                    .sort_values("events", ascending=True)
                )
                fig = px.bar(
                    article_counts,
                    x="events",
                    y="gdpr_article",
                    orientation="h",
                    labels={"events": "Events tagged", "gdpr_article": "GDPR article"},
                )
                fig.update_traces(marker_color=SEQUENTIAL_BLUE)
                st.plotly_chart(fig, width="stretch")
