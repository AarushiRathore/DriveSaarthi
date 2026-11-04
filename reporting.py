"""Pie chart showing how the issue time in a report window splits across factors."""
from __future__ import annotations

COLORS = {"Seatbelt": "#B8975A", "Speed": "#D2453F", "Drowsiness": "#6F8FB8",
          "Mobile phone": "#D6A24A", "Camera feed": "#94A0B4"}
BG, INK = "#0D1522", "#ECE8DF"


def save_pie(path: str, seconds: dict, title: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    items = [(k, v) for k, v in seconds.items() if v > 0]
    fig, ax = plt.subplots(figsize=(5.6, 5.6), facecolor=BG)
    ax.set_title(title, color=INK, fontsize=12, pad=16)
    if items:
        ax.pie([v for _, v in items], labels=[f"{k}\n{v:.0f}s" for k, v in items],
               colors=[COLORS.get(k, "#888888") for k, _ in items], autopct="%1.0f%%", startangle=90,
               counterclock=False, pctdistance=0.66, wedgeprops=dict(edgecolor=BG, linewidth=2),
               textprops=dict(color=INK, fontsize=10))
    else:
        ax.pie([1], colors=["#1B2A44"], wedgeprops=dict(edgecolor=BG, linewidth=2))
        ax.text(0, 0, "No issues recorded", ha="center", va="center", color=INK, fontsize=12)
    fig.savefig(path, dpi=140, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
