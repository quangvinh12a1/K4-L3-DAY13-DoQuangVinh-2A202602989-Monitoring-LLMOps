"""Dung dashboard 6 panel tu data/logs.jsonl theo contract config/dashboard.yaml.

Xuat mot file HTML tu chua (SVG inline, khong can thu vien ngoai):

    python scripts/build_dashboard.py            # ghi data/dashboard.html mot lan
    python scripts/build_dashboard.py --watch    # tai tao moi refresh_seconds (trang tu reload)
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio  # noqa: E402

COLORS = ["#2563eb", "#d97706", "#7c3aed", "#059669"]


# ---------------------------------------------------------------- data

def load_events(path: Path) -> list[dict]:
    events = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
            event["_ts"] = datetime.fromisoformat(event["ts"].replace("Z", "+00:00"))
            events.append(event)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return events


def percentile(values: list[float], p: float) -> float:
    """Cung cong thuc voi app/metrics.py de dashboard khop /metrics."""
    if not values:
        return 0.0
    items = sorted(values)
    idx = max(0, min(len(items) - 1, round((p / 100) * len(items) + 0.5) - 1))
    return float(items[idx])


def window_events(events: list[dict], minutes: int) -> tuple[list[dict], datetime, datetime, bool]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    in_window = [e for e in events if start <= e["_ts"] <= end]
    if in_window or not events:
        return in_window, start, end, False
    # Log cu hon 60 phut (xem lai offline): neo cua so vao log moi nhat.
    end = max(e["_ts"] for e in events)
    start = end - timedelta(minutes=minutes)
    return [e for e in events if start <= e["_ts"] <= end], start, end, True


def by_minute(events: list[dict]) -> dict[datetime, list[dict]]:
    buckets: dict[datetime, list[dict]] = defaultdict(list)
    for e in events:
        buckets[e["_ts"].replace(second=0, microsecond=0)].append(e)
    return dict(sorted(buckets.items()))


def compute(events: list[dict]) -> dict:
    received = [e for e in events if e.get("event") == "request_received"]
    sent = [e for e in events if e.get("event") == "response_sent"]
    failed = [e for e in events if e.get("event") == "request_failed"]
    tool = [e for e in events if e.get("tool_success") is not None]
    minutes = sorted(set(by_minute(received)) | set(by_minute(sent)) | set(by_minute(failed)))
    rec_m, sent_m, fail_m = by_minute(received), by_minute(sent), by_minute(failed)

    def series(fn, source):
        return [fn(source.get(m, [])) for m in minutes]

    lat = lambda rows, p: percentile([r["latency_ms"] for r in rows], p) if rows else None  # noqa: E731
    cum_cost = cum_in = cum_out = 0.0
    cost_cum, tin_cum, tout_cum = [], [], []
    for m in minutes:
        rows = sent_m.get(m, [])
        cum_cost += sum(r.get("cost_usd", 0) for r in rows)
        cum_in += sum(r.get("tokens_in", 0) for r in rows)
        cum_out += sum(r.get("tokens_out", 0) for r in rows)
        cost_cum.append(round(cum_cost, 6))
        tin_cum.append(cum_in)
        tout_cum.append(cum_out)

    return {
        "minutes": minutes,
        "latency": {
            "p50": series(lambda r: lat(r, 50), sent_m),
            "p95": series(lambda r: lat(r, 95), sent_m),
            "p99": series(lambda r: lat(r, 99), sent_m),
            "ttft_p95": series(lambda r: percentile([x["ttft_ms"] for x in r], 95) if r else None, sent_m),
            "stats": {
                "p50": percentile([e["latency_ms"] for e in sent], 50),
                "p95": percentile([e["latency_ms"] for e in sent], 95),
                "p99": percentile([e["latency_ms"] for e in sent], 99),
                "ttft_p95": percentile([e["ttft_ms"] for e in sent], 95),
            },
        },
        "traffic": {"rpm": series(len, rec_m), "count": len(received)},
        "errors": {
            "rate": [
                (len(fail_m.get(m, [])) / len(rec_m[m]) * 100) if rec_m.get(m) else None for m in minutes
            ],
            "error_rate_pct": (len(failed) / len(received) * 100) if received else 0.0,
            "breakdown": Counter(e.get("error_type") or "unknown" for e in failed),
            "tool_success_pct": (sum(e["tool_success"] is True for e in tool) / len(tool) * 100) if tool else 100.0,
        },
        "cost": {"per_min": series(lambda r: round(sum(x.get("cost_usd", 0) for x in r), 6), sent_m),
                 "cumulative": cost_cum, "total": round(cum_cost, 6)},
        "tokens": {"in_cum": tin_cum, "out_cum": tout_cum, "in": int(cum_in), "out": int(cum_out)},
        "quality": {
            "mean_per_min": series(lambda r: round(sum(x["quality_score"] for x in r) / len(r), 3) if r else None, sent_m),
            "mean": round(sum(e["quality_score"] for e in sent) / len(sent), 3) if sent else 0.0,
        },
    }


# ---------------------------------------------------------------- rendering

def svg_chart(minutes: list[datetime], series: dict[str, list], threshold: float, unit: str, *, bars: bool = False) -> str:
    w, h, left, bottom, top, right = 520, 210, 56, 26, 12, 12
    values = [v for s in series.values() for v in s if v is not None]
    ymax = max(values + [threshold]) * 1.15 or 1
    n = max(len(minutes), 1)
    x = lambda i: left + (w - left - right) * (i + 0.5) / n  # noqa: E731
    y = lambda v: top + (h - top - bottom) * (1 - v / ymax)  # noqa: E731
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
    for k in range(5):  # truc Y
        v = ymax * k / 4
        parts.append(f'<line x1="{left}" x2="{w - right}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 6}" y="{y(v) + 4:.1f}" class="axis" text-anchor="end">{v:,.4g}</text>')
    step = max(1, n // 6)
    for i, m in enumerate(minutes):
        if i % step == 0:
            parts.append(f'<text x="{x(i):.1f}" y="{h - 8}" class="axis" text-anchor="middle">{m:%H:%M}</text>')
    for idx, (name, vals) in enumerate(series.items()):
        color = COLORS[idx % len(COLORS)]
        if bars:
            bw = (w - left - right) / n / (len(series) + 0.5)
            for i, v in enumerate(vals):
                if v:
                    parts.append(
                        f'<rect x="{x(i) - bw * len(series) / 2 + idx * bw:.1f}" y="{y(v):.1f}" width="{bw:.1f}" '
                        f'height="{y(0) - y(v):.1f}" fill="{color}"><title>{name} {v:,.4g} {unit}</title></rect>'
                    )
        else:
            pts = [(x(i), y(v)) for i, v in enumerate(vals) if v is not None]
            if len(pts) > 1:
                parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}"/>')
            for (a, b), v in zip(pts, [v for v in vals if v is not None]):
                parts.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3" fill="{color}"><title>{name} {v:,.4g} {unit}</title></circle>')
    ty = y(threshold)
    parts.append(f'<line x1="{left}" x2="{w - right}" y1="{ty:.1f}" y2="{ty:.1f}" class="threshold"/>')
    parts.append(f'<text x="{w - right}" y="{ty - 5:.1f}" class="threshold-label" text-anchor="end">threshold {threshold:,.4g} {unit}</text>')
    parts.append("</svg>")
    legend = "".join(
        f'<span><i style="background:{COLORS[i % len(COLORS)]}"></i>{html.escape(name)}</span>' for i, name in enumerate(series)
    )
    return f'<div class="legend">{legend}</div>' + "".join(parts)


def status(value: float, threshold: dict) -> str:
    ok = value <= threshold["value"] if threshold["operator"] == "lte" else value >= threshold["value"]
    return "ok" if ok else "breach"


def render(config: dict, data: dict, start: datetime, end: datetime, anchored: bool) -> str:
    dash = config["dashboard"]
    panels = {p["id"]: p for p in dash["panels"]}
    m = data["minutes"]

    def card(pid: str, value: float, value_label: str, body: str, extra: str = "") -> str:
        p = panels[pid]
        th = p["threshold"]
        op = "≤" if th["operator"] == "lte" else "≥"
        return f"""
        <section class="panel {status(value, th)}">
          <header><h2>{html.escape(p['title'])}</h2><span class="unit">unit: {html.escape(p['unit'])}</span></header>
          <div class="stat"><b>{value_label}</b><span>SLO/threshold: {th['aggregation']} {op} {th['value']:,} {html.escape(p['unit'])}</span></div>
          {body}{extra}
        </section>"""

    lat, err, cost, tok, qual = data["latency"], data["errors"], data["cost"], data["tokens"], data["quality"]
    s = lat["stats"]
    breakdown = ", ".join(f"{k}: {v}" for k, v in err["breakdown"].most_common()) or "none"
    cards = [
        card("latency", s["p95"], f"P50 {s['p50']:.0f} · P95 {s['p95']:.0f} · P99 {s['p99']:.0f} · TTFT P95 {s['ttft_p95']:.0f} ms",
             svg_chart(m, {"p50": lat["p50"], "p95": lat["p95"], "p99": lat["p99"], "ttft_p95": lat["ttft_p95"]},
                       panels["latency"]["threshold"]["value"], "ms")),
        card("traffic", max(data["traffic"]["rpm"] or [0]), f"{data['traffic']['count']} requests · peak {max(data['traffic']['rpm'] or [0])}/min",
             svg_chart(m, {"requests/min": data["traffic"]["rpm"]}, panels["traffic"]["threshold"]["value"], "req/min", bars=True)),
        card("errors", err["error_rate_pct"], f"error rate {err['error_rate_pct']:.1f}% · retrieval success {err['tool_success_pct']:.1f}%",
             svg_chart(m, {"error rate %": err["rate"]}, panels["errors"]["threshold"]["value"], "%"),
             f'<p class="note">Breakdown by error_type: {html.escape(breakdown)}</p>'),
        card("cost", cost["total"], f"total ${cost['total']:.4f}",
             svg_chart(m, {"cumulative $": cost["cumulative"], "$ per minute": cost["per_min"]}, panels["cost"]["threshold"]["value"], "USD")),
        card("tokens", max(tok["in"], tok["out"]), f"input {tok['in']:,} · output {tok['out']:,} tokens",
             svg_chart(m, {"tokens_in (cumulative)": tok["in_cum"], "tokens_out (cumulative)": tok["out_cum"]}, panels["tokens"]["threshold"]["value"], "tokens")),
        card("quality", qual["mean"], f"mean quality {qual['mean']:.3f}",
             svg_chart(m, {"mean quality_score": qual["mean_per_min"]}, panels["quality"]["threshold"]["value"], "score")),
    ]
    note = " (anchored to latest log — logs older than 60 min)" if anchored else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="{dash['refresh_seconds']}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Day 13 Dashboard</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --fg:#111827; --muted:#6b7280; --grid:#e5e7eb; --ok:#059669; --bad:#dc2626; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1115; --card:#181b22; --fg:#e5e7eb; --muted:#9ca3af; --grid:#2a2f3a; }} }}
body {{ margin:0; padding:16px; background:var(--bg); color:var(--fg); font:14px/1.4 system-ui, sans-serif; }}
h1 {{ font-size:20px; margin:0 0 4px; }} .meta {{ color:var(--muted); margin-bottom:12px; }}
.grid6 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(360px,1fr)); gap:12px; }}
.panel {{ background:var(--card); border-radius:10px; padding:12px; border-top:4px solid var(--ok); }}
.panel.breach {{ border-top-color:var(--bad); }}
header {{ display:flex; justify-content:space-between; align-items:baseline; }} h2 {{ font-size:15px; margin:0; }}
.unit, .stat span, .note {{ color:var(--muted); font-size:12px; }}
.stat {{ display:flex; flex-direction:column; margin:6px 0; }} .stat b {{ font-size:15px; }}
.chart {{ width:100%; height:auto; }} .grid {{ stroke:var(--grid); }} .axis {{ fill:var(--muted); font-size:10px; }}
.threshold {{ stroke:var(--bad); stroke-dasharray:6 4; stroke-width:1.5; }} .threshold-label {{ fill:var(--bad); font-size:10px; }}
.legend span {{ margin-right:10px; font-size:12px; color:var(--muted); }} .legend i {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; }}
</style></head><body>
<h1>{html.escape(dash['title'])}</h1>
<div class="meta">Source: data/logs.jsonl · Time range: last {dash['time_range_minutes']} min
({start:%Y-%m-%d %H:%M} → {end:%H:%M} UTC){note} · Auto-refresh {dash['refresh_seconds']}s · Red dashed line = threshold/SLO</div>
<div class="grid6">{''.join(cards)}</div>
</body></html>"""


def build(config_path: Path, log_path: Path, out_path: Path) -> Path:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    events, start, end, anchored = window_events(load_events(log_path), config["dashboard"]["time_range_minutes"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(config, compute(events), start, end, anchored), encoding="utf-8")
    return out_path


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "config" / "dashboard.yaml")
    parser.add_argument("--logs", type=Path, default=REPO_ROOT / "data" / "logs.jsonl")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "dashboard.html")
    parser.add_argument("--watch", action="store_true", help="Tai tao lien tuc theo refresh_seconds")
    args = parser.parse_args()
    while True:
        path = build(args.config, args.logs, args.out)
        print(f"Dashboard -> {path}")
        if not args.watch:
            return 0
        time.sleep(yaml.safe_load(args.config.read_text(encoding="utf-8"))["dashboard"]["refresh_seconds"])


if __name__ == "__main__":
    raise SystemExit(main())
