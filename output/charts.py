"""Plotly chart builders for Streamlit dashboard."""

import plotly.express as px
import plotly.graph_objects as go

COLOURS = {
    "generous": "#1A5276",
    "comfortable": "#2980B9",
    "frugal": "#85C1E9",
    "positive": "#1E8449",
    "negative": "#C0392B",
    "neutral": "#7F8C8D",
    "scenarios": ["#1A5276", "#2980B9", "#85C1E9"],
}

CITY_COLOURS = [
    "#1A5276",
    "#1E8449",
    "#6E2F8E",
    "#B7950B",
    "#A93226",
    "#17A589",
    "#D35400",
    "#839192",
]


def surplus_bar_chart(scenarios: list[dict]) -> go.Figure:
    """
    Bar chart comparing monthly surplus across cities + scenarios.
    scenarios: list of {label, surplus_eur, scenario}
    """
    labels = [s["label"] for s in scenarios]
    values = [s["surplus_eur"] for s in scenarios]
    colours = [COLOURS["positive"] if v >= 0 else COLOURS["negative"] for v in values]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=colours,
            text=[f"€{v:+,.0f}" for v in values],
            textposition="outside",
        )
    )
    fig.add_hline(y=0, line_dash="dash", line_color=COLOURS["neutral"])
    fig.update_layout(
        title="Monthly Surplus / Deficit (EUR)",
        yaxis_title="EUR / month",
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=400,
    )
    return fig


def trajectory_line_chart(trajectories: list[dict]) -> go.Figure:
    """
    Line chart of cumulative savings over 10 years for multiple city+scenario combinations.

    trajectories: list of {
        label: str,
        data: list[{year, cumulative_savings_eur, events}],
        city_idx: int  (determines colour),
        scenario_idx: int  (determines line style: 0=solid, 1=dashed, 2=dotted),
    }
    city_idx and scenario_idx are optional; if absent, colour cycles by trace order.
    """
    DASH_STYLES = ["solid", "dash", "dot"]

    fig = go.Figure()
    for i, traj in enumerate(trajectories):
        city_idx = traj.get("city_idx", i)
        scenario_idx = traj.get("scenario_idx", 0)
        colour = CITY_COLOURS[city_idx % len(CITY_COLOURS)]
        dash = DASH_STYLES[scenario_idx % len(DASH_STYLES)]

        years = [d["year"] for d in traj["data"]]
        values = [d["cumulative_savings_eur"] for d in traj["data"]]
        events = [d.get("events", []) for d in traj["data"]]

        fig.add_trace(
            go.Scatter(
                x=years,
                y=values,
                mode="lines+markers",
                name=traj["label"],
                line={"color": colour, "width": 2, "dash": dash},
                marker={"size": 5},
                hovertemplate="%{text}<br>Year %{x}: €%{y:,.0f}<extra></extra>",
                text=[", ".join(e) if e else traj["label"] for e in events],
            )
        )

    fig.update_layout(
        title="10-Year Cumulative Savings (EUR)",
        xaxis_title="Year",
        yaxis_title="Cumulative savings (EUR)",
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=500,
        legend={"yanchor": "top", "y": 0.99, "xanchor": "left", "x": 0.01},
    )
    fig.add_hline(y=0, line_dash="dash", line_color=COLOURS["neutral"])
    return fig


def budget_breakdown_chart(budgets: list[dict]) -> go.Figure:
    """
    Stacked bar showing expense breakdown per city.
    budgets: list of {label, items: {key: {label, value_eur}}}
    """
    from engine.budget import DISPLAY_LABELS

    all_keys = list(DISPLAY_LABELS.keys())

    fig = go.Figure()
    palette = px.colors.qualitative.Pastel

    for key in all_keys:
        label = DISPLAY_LABELS.get(key, key)
        values = []
        for b in budgets:
            item = b["items"].get(key)
            values.append(item["value_eur"] if item else 0)

        fig.add_trace(
            go.Bar(
                name=label,
                x=[b["label"] for b in budgets],
                y=values,
                marker_color=palette[all_keys.index(key) % len(palette)],
            )
        )

    fig.update_layout(
        barmode="stack",
        title="Monthly Expense Breakdown (EUR equiv.)",
        yaxis_title="EUR / month",
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=450,
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.4},
    )
    return fig


def negotiation_ladder_chart(ladder: list[dict], reference_surplus: float) -> go.Figure:
    """
    Horizontal bar chart showing surplus at each gross salary level vs reference.
    ladder: list of {gross, net_monthly_eur, surplus_eur}
    """
    labels = [f"{d['gross']:,}" for d in ladder]
    surpluses = [d["surplus_eur"] for d in ladder]
    colours = [
        COLOURS["positive"] if s >= reference_surplus else COLOURS["negative"] for s in surpluses
    ]

    fig = go.Figure(
        go.Bar(
            y=labels,
            x=surpluses,
            orientation="h",
            marker_color=colours,
            text=[f"€{s:+,.0f}/mo" for s in surpluses],
            textposition="outside",
        )
    )
    fig.add_vline(
        x=reference_surplus,
        line_dash="dash",
        line_color="#E67E22",
        annotation_text=f"Reference: €{reference_surplus:+,.0f}/mo",
    )
    fig.update_layout(
        title="Salary Ladder — Monthly Surplus (EUR)",
        xaxis_title="EUR surplus / month",
        yaxis_title="Gross salary (local currency)",
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=400,
    )
    return fig
