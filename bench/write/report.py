"""Render a standalone HTML report for the write benchmark.

The report starts with cross-run comparisons, then gives every recorded sweep point its own detail
section with configuration, stage-duration trends, and a batch-pipeline Gantt.

    uv run --project bench --group analysis -m bench.write.report [--open]
"""

import argparse
import html
import json
import webbrowser
from pathlib import Path
from typing import cast

import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

from bench.config import RESULTS_DIR
from bench.write.loaders import batch_timeline, load

REPORT_PATH = RESULTS_DIR / "write" / "report.html"
_STAGES = ("collect", "process", "flush", "transfer")
_STAGE_COLOR = {"collect": "#4C78A8", "process": "#F58518", "flush": "#E45756", "transfer": "#72B7B2"}
FigureContent = go.Figure | str
FigureBlock = tuple[str, FigureContent]
ReportSection = tuple[str, list[FigureBlock]]


def _summary_table(df) -> go.Figure:
    cols = {
        "record_id": "record",
        "machine.host": "host",
        "git.commit": "commit",
        "run.backend": "backend",
        "run.mode": "mode",
        "run.fps_target": "target fps",
        "run.target_shard_gb": "shard GB",
        "run.downscale": "downscale",
        "run.compression": "codec",
        "run.max_level": "level",
        "run.slots": "slots",
        "eff_fps": "eff fps",
        "fps_attainment": "attain %",
        "mb_s": "MB/s",
        "ratio": "ratio",
        "drain_s": "drain s",
        "flush_p95_s": "flush p95 s",
    }
    present = [c for c in cols if c in df.columns]
    view = df[present].copy()
    for c in ("eff_fps", "mb_s", "ratio", "drain_s", "flush_p95_s"):
        if c in view:
            view[c] = view[c].round(1)
    if "fps_attainment" in view:
        view["fps_attainment"] = (100 * view["fps_attainment"]).round(1)
    fig = go.Figure(
        go.Table(
            header={"values": [cols[c] for c in present], "fill_color": "#eaeaea", "align": "left"},
            cells={"values": [view[c] for c in present], "align": "left"},
        )
    )
    fig.update_layout(margin={"t": 20, "b": 0})
    return fig


def _gantt(sub, title: str = "Batch pipeline") -> go.Figure:
    """Show each batch stage on one shared run-relative time axis."""
    fig = go.Figure()
    for stage, color in _STAGE_COLOR.items():
        start, dur = sub[f"{stage}_start"], sub[f"{stage}_s"]
        mask = start.notna() & dur.notna()
        if mask.any():
            fig.add_bar(
                y=sub.loc[mask, "batch"],
                x=dur[mask],
                base=start[mask],
                orientation="h",
                name=stage,
                marker_color=color,
                customdata=sub.loc[mask, f"{stage}_end"],
                hovertemplate=f"batch %{{y}}<br>{stage}: %{{base:.1f}}-%{{customdata:.1f}}s"
                "<br>duration: %{x:.1f}s<extra></extra>",
            )
    fig.update_layout(
        barmode="overlay",
        title=title,
        xaxis_title="seconds from run start",
        yaxis_title="batch",
        yaxis={"autorange": "reversed", "dtick": 1},
        legend_title="stage",
        margin={"t": 45},
    )
    return fig


def _stage_durations(sub) -> go.Figure:
    fig = go.Figure()
    for stage, color in _STAGE_COLOR.items():
        values = sub[f"{stage}_s"]
        mask = values.notna()
        if mask.any():
            fig.add_scatter(
                x=sub.loc[mask, "batch"],
                y=values[mask],
                mode="lines+markers",
                name=stage,
                marker_color=color,
                hovertemplate=f"batch %{{x}}<br>{stage}: %{{y:.1f}}s<extra></extra>",
            )
    fig.update_layout(
        title="Stage duration by batch (growth indicates accumulating pressure)",
        xaxis_title="batch",
        yaxis_title="duration (s)",
        legend_title="stage",
        margin={"t": 45},
    )
    return fig


def _add_derived(df, bt):
    df = df.copy()
    df["fps_attainment"] = df["eff_fps"] / df["run.fps_target"]
    for stage in _STAGES:
        stats = bt.groupby("record_id")[f"{stage}_s"].agg(
            **{f"{stage}_median_s": "median", f"{stage}_p95_s": lambda s: s.quantile(0.95)}
        )
        df = df.merge(stats, how="left", left_on="record_id", right_index=True)
    return df


def _attainment_color(value) -> str:
    if value != value:
        return "#f1f3f5"
    if value >= 1:
        return "#76c893"
    if value >= 0.95:
        return "#b7e4c7"
    if value >= 0.8:
        return "#ffe08a"
    return "#f5a3a3"


def _attainment_tables(df) -> list[tuple[str, go.Figure]]:
    """One non-overlapping FPS matrix per host/backend/mode; repeated measurements are averaged."""
    figures = []
    group = ["machine.host", "run.backend", "run.mode"]
    for (host, backend, mode), group_df in df.groupby(group, sort=True, dropna=False):
        sub = group_df.copy()
        sub["config"] = sub.apply(
            lambda row: f"{row['run.target_shard_gb']:g} GB<br>{row['run.downscale']}<br>{row['run.compression']}",
            axis=1,
        )
        summary = (
            sub.groupby(["run.fps_target", "config"], sort=True)
            .agg(eff_fps=("eff_fps", "mean"), attainment=("fps_attainment", "mean"), samples=("record_id", "size"))
            .reset_index()
        )
        targets = sorted(summary["run.fps_target"].unique())
        configs = sorted(summary["config"].unique())
        values = [[f"{target:g}" for target in targets]]
        fills = [["#e9ecef"] * len(targets)]
        for config in configs:
            cells, colors = [], []
            for target in targets:
                match = summary[(summary["run.fps_target"] == target) & (summary["config"] == config)]
                if match.empty:
                    cells.append("—")
                    colors.append("#f1f3f5")
                    continue
                item = match.iloc[0]
                count = f" · n={int(item['samples'])}" if item["samples"] > 1 else ""
                cells.append(f"{item['eff_fps']:.2f} fps<br>{item['attainment']:.1%}{count}")
                colors.append(_attainment_color(item["attainment"]))
            values.append(cells)
            fills.append(colors)
        fig = go.Figure(
            go.Table(
                columnwidth=[65] + [125] * len(configs),
                header={"values": ["target fps", *configs], "fill_color": "#dee2e6", "align": "center"},
                cells={"values": values, "fill_color": fills, "align": "center", "height": 38},
            )
        )
        fig.update_layout(margin={"t": 15, "b": 0}, height=max(180, 85 + 38 * len(targets)))
        figures.append((f"FPS attainment — {host} / {backend} / {mode}", fig))
    return figures


def _comparison_figures(df, bt) -> list[FigureBlock]:
    out: list[FigureBlock] = [("All recorded runs", _summary_table(df))]
    out.append(
        (
            "Recorded sweep coverage (zero/blank cells are missing points)",
            px.density_heatmap(
                df,
                x="run.target_shard_gb",
                y="run.fps_target",
                facet_col="run.backend",
                facet_row="downscale_compression",
                histfunc="count",
                text_auto=True,
                labels={
                    "run.target_shard_gb": "target shard GB",
                    "run.fps_target": "target fps",
                    "count": "recorded runs",
                },
            ),
        )
    )

    out.extend(_attainment_tables(df))

    out.append(
        (
            "Drain tail vs target FPS (lower is better)",
            px.line(
                df.sort_values("run.fps_target"),
                x="run.fps_target",
                y="drain_s",
                color="run.target_shard_gb",
                line_dash="run.compression",
                symbol="run.mode",
                line_group="comparison_group",
                markers=True,
                facet_col="run.backend",
                facet_row="run.downscale",
                hover_data=["record_id", "eff_fps", "flush_p95_s"],
                labels={
                    "run.fps_target": "target fps",
                    "drain_s": "drain tail (s)",
                    "run.target_shard_gb": "shard GB",
                    "run.compression": "compression",
                },
            ),
        )
    )
    out.append(
        (
            "Throughput vs shard size",
            px.line(
                df.sort_values("run.target_shard_gb"),
                x="run.target_shard_gb",
                y="mb_s",
                color="fps_label",
                line_dash="run.compression",
                symbol="run.mode",
                line_group="comparison_group",
                markers=True,
                facet_col="run.backend",
                facet_row="run.downscale",
                hover_data=["record_id", "run.mode", "run.compression", "eff_fps", "ratio"],
                labels={
                    "run.target_shard_gb": "target shard GB",
                    "mb_s": "MB/s",
                    "fps_label": "target fps",
                    "run.compression": "compression",
                },
            ),
        )
    )
    out.append(
        (
            "Flush duration by batch",
            px.line(
                bt,
                x="batch",
                y="flush_s",
                color="fps_label",
                line_dash="compression",
                symbol="mode",
                line_group="record_id",
                facet_col="target_shard_gb",
                facet_row="backend_downscale",
                hover_data=["record_id", "run_id", "mode", "slots"],
                labels={
                    "flush_s": "flush duration (s)",
                    "fps_label": "target fps",
                    "target_shard_gb": "shard GB",
                    "backend_downscale": "backend / downscale",
                    "compression": "compression",
                },
            ),
        )
    )
    if df["run.compression"].nunique() > 1:
        out.append(
            (
                "Compression ratio vs throughput (upper-right is better)",
                px.scatter(
                    df,
                    x="ratio",
                    y="mb_s",
                    color="run.compression",
                    symbol="run.backend",
                    hover_data=[
                        "record_id",
                        "run.target_shard_gb",
                        "run.downscale",
                        "run.fps_target",
                        "machine.host",
                    ],
                    labels={"mb_s": "MB/s", "run.compression": "codec"},
                ),
            )
        )
    if df["machine.host"].nunique() > 1:
        out.append(
            (
                "Cross-machine effective FPS",
                px.bar(
                    df,
                    x="machine.host",
                    y="eff_fps",
                    color="fps_label",
                    barmode="group",
                    facet_col="run.backend",
                    hover_data=["record_id", "run.target_shard_gb", "run.downscale", "mb_s", "git.commit"],
                    labels={"eff_fps": "effective fps", "fps_label": "target fps"},
                ),
            )
        )
    return out


def _run_title(row) -> str:
    return (
        f"{row['run.backend']}/{row['run.mode']} · {row['run.fps_target']:g} fps · "
        f"{row['run.target_shard_gb']:g} GB shard · {row['run.downscale']} · "
        f"{row['run.compression']} · {row['record_id']}"
    )


def _json_value(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        return None if value != value else round(value, 3)
    return value


def _run_json(row) -> str:
    timing = {}
    for stage in _STAGES:
        timing[stage] = {
            "median_s": _json_value(row.get(f"{stage}_median_s")),
            "p95_s": _json_value(row.get(f"{stage}_p95_s")),
        }
    payload = {
        "record_id": _json_value(row.get("record_id")),
        "sweep_run_id": _json_value(row.get("run_id")),
        "provenance": {
            "host": _json_value(row.get("machine.host")),
            "git_commit": _json_value(row.get("git.commit")),
            "git_dirty": _json_value(row.get("git.dirty")),
        },
        "configuration": {
            key.removeprefix("run."): _json_value(value) for key, value in row.items() if key.startswith("run.")
        },
        "outcome": {
            "effective_fps": _json_value(row.get("eff_fps")),
            "fps_attainment": _json_value(row.get("fps_attainment")),
            "mb_s": _json_value(row.get("mb_s")),
            "compression_ratio": _json_value(row.get("ratio")),
            "drain_s": _json_value(row.get("drain_s")),
            "wall_s": _json_value(row.get("result.wall_s")),
            "collect_s": _json_value(row.get("result.collect_s")),
            "stage_timing": timing,
        },
    }
    rendered = html.escape(json.dumps(payload, indent=2, sort_keys=True))
    return f"<details><summary>Show configuration JSON</summary><pre><code>{rendered}</code></pre></details>"


def _run_detail(row, sub) -> list[FigureBlock]:
    return [
        ("Configuration and outcome", _run_json(row)),
        ("Stage behavior", _stage_durations(sub)),
        ("Pipeline timeline", _gantt(sub)),
    ]


def report_sections(df, bt) -> list[ReportSection]:
    df = _add_derived(df, bt)
    group_cols = [
        "run_id",
        "machine.host",
        "run.backend",
        "run.mode",
        "run.compression",
        "run.slots",
        "run.downscale",
        "run.max_level",
    ]
    df["comparison_group"] = df[group_cols].astype(str).agg("|".join, axis=1)
    df["fps_label"] = df["run.fps_target"].map(lambda value: f"{value:g}")
    df["downscale_compression"] = df["run.downscale"].astype(str) + " / " + df["run.compression"].astype(str)
    bt = bt.copy()
    bt["fps_label"] = bt["fps_target"].map(lambda value: f"{value:g}")
    bt["backend_downscale"] = bt["backend"].astype(str) + " / " + bt["downscale"].astype(str)

    sections: list[ReportSection] = [("Cross-run comparisons", _comparison_figures(df, bt))]
    order = ["run.backend", "run.mode", "run.compression", "run.target_shard_gb", "run.fps_target", "record_id"]
    for _, row in df.sort_values(order).iterrows():
        sub = bt[bt["record_id"] == row["record_id"]].sort_values("batch")
        sections.append((_run_title(row), _run_detail(row, sub)))
    return sections


def write_report(path: Path = REPORT_PATH) -> Path:
    df, bt = load(), batch_timeline()
    sections = report_sections(df, bt)
    blocks = []
    figure_index = 0
    for section_title, figures in sections:
        inner = []
        for title, content in figures:
            if isinstance(content, str):
                rendered = content
            else:
                js = "cdn" if figure_index == 0 else False
                rendered = pio.to_html(content, full_html=False, include_plotlyjs=cast("bool", js))
                figure_index += 1
            inner.append(f"<h3>{title}</h3>{rendered}")
        blocks.append(f"<section><h2>{section_title}</h2>{''.join(inner)}</section>")
    hosts = ", ".join(sorted(df["machine.host"].dropna().unique()))
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'><title>write bench report</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:1400px;margin:2rem auto;padding:0 1rem}"
        "h1{margin-bottom:0}section{margin:3rem 0;padding-top:1rem;border-top:1px solid #ddd}"
        "summary{cursor:pointer;font-weight:600;color:#245;}details[open] summary{margin-bottom:.75rem}"
        "h3{margin-top:2rem}pre{background:#f6f8fa;border:1px solid #ddd;border-radius:6px;padding:1rem;"
        "overflow:auto;line-height:1.4}</style></head><body>"
        f"<h1>Write benchmark</h1><p>{len(df)} recorded runs across {df['machine.host'].nunique()} machine(s): "
        f"{hosts}</p>{''.join(blocks)}</body></html>"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="render the curated write-benchmark HTML report")
    parser.add_argument("--open", action="store_true", help="open the report in a browser when done")
    args = parser.parse_args()
    output = write_report()
    print(f"wrote {output}")
    if args.open:
        webbrowser.open(output.as_uri())
