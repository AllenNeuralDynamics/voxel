"""Marimo explorer for the downsample benchmark. Run:

    uv run marimo edit bench/downsample/analysis.py

Click **pull** to gather every machine's results, then read the GB/s-vs-threads scaling (the plateau) and
the chart builder. Loaders are plain pandas (`bench.downsample.loaders`); only the pull button touches S3.
"""

import marimo

app = marimo.App(width="medium")


@app.cell
def _():
    import sys
    import warnings
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, so `bench.*` imports

    warnings.filterwarnings("ignore", message=".*write_feather is deprecated.*", category=FutureWarning)

    import altair as alt
    import marimo as mo

    from bench.downsample.loaders import load
    from bench.sync import pull

    return alt, load, mo, pull


@app.cell
def _(mo):
    mo.md(
        """
        # Downsample benchmark explorer
        Production pyramid kernel (`pyramids_3d_numba`), GB/s vs numba thread count. Click **pull** to
        gather every machine's results, then read the scaling plateau below.
        """
    )
    return


@app.cell
def _(mo):
    pull_btn = mo.ui.run_button(label="⟳ pull latest results from all machines")
    pull_btn
    return (pull_btn,)


@app.cell
def _(load, pull, pull_btn):
    if pull_btn.value:
        pull()
    df = load()
    return (df,)


@app.cell
def _(df, mo):
    hosts = sorted(df["machine.host"].dropna().unique())
    mo.md(f"**{len(df)} points** across **{len(hosts)} machine(s)**: {', '.join(hosts)}")
    return


@app.cell
def _(df, mo):
    cols = [
        "run.reduction",
        "run.threads",
        "run.pool_max",
        "run.threading_layer",
        "run.max_level",
        "run.block_z",
        "run.block_y",
        "run.block_x",
        "result.time_s",
        "gb_s",
        "machine.host",
        "git.commit",
    ]
    mo.ui.table(df[[c for c in cols if c in df.columns]], pagination=True)
    return


@app.cell
def _(alt, df, mo):
    # GB/s vs thread count -- the process-stage scaling plateau (memory-bandwidth bound near ~16 threads).
    chart = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X("run.threads:Q", title="numba threads", scale=alt.Scale(type="log", base=2)),
            y=alt.Y("gb_s:Q", title="GB/s"),
            color="run.reduction:N",
            strokeDash="machine.host:N",
            tooltip=["run.reduction", "run.threads", "gb_s", "run.threading_layer", "machine.host"],
        )
        .properties(title="downsample throughput vs thread count")
    )
    mo.ui.altair_chart(chart)
    return


@app.cell
def _(df, mo):
    mo.md("## Chart builder")
    mo.ui.data_explorer(df)
    return


if __name__ == "__main__":
    app.run()
