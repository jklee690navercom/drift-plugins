"""Non-windowed 5개 plugin analyze() 패턴 단위 검증.
cusum, c-chart, p-chart, imr-chart, xbar-r-chart
"""

import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "plugins", "c-chart"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "p-chart"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "imr-chart"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "xbar-r-chart"))

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from framework.plugin.cache import PluginCache

from plugins.cusum.drift_cusum.detector import CusumDetector
from drift_c_chart.detector import CChartDetector
from drift_p_chart.detector import PChartDetector
from drift_imr_chart.detector import ImrChartDetector
from drift_xbar_r_chart.detector import XbarRChartDetector


def make_data(n_points, drift_at=None, seed=42, base_mean=10.0, drift_shift=5.0):
    rng = np.random.RandomState(seed)
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(n_points):
        ts = base + timedelta(minutes=5 * i)
        mean = base_mean if (drift_at is None or i < drift_at) else base_mean + drift_shift
        rows.append({"timestamp": ts, "value": float(rng.normal(mean, 1.0)), "count": 1})
    return rows


def make_proportion_data(n_points, drift_at=None, seed=42):
    """p-chart용 비율 데이터"""
    rng = np.random.RandomState(seed)
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(n_points):
        ts = base + timedelta(minutes=5 * i)
        p = 0.05 if (drift_at is None or i < drift_at) else 0.20
        rows.append({"timestamp": ts, "value": float(rng.binomial(50, p) / 50.0), "count": 1})
    return rows


def make_count_data(n_points, drift_at=None, seed=42):
    """c-chart용 카운트 데이터"""
    rng = np.random.RandomState(seed)
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(n_points):
        ts = base + timedelta(minutes=5 * i)
        lam = 5.0 if (drift_at is None or i < drift_at) else 15.0
        rows.append({"timestamp": ts, "value": float(rng.poisson(lam)), "count": 1})
    return rows


def run_suite(name, DetectorClass, data_fn, n_points=200, drift_at=80):
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")

    # 1. empty
    det = DetectorClass(); det.cache = PluginCache()
    assert det.analyze(pd.DataFrame(), [], "s", {}) == []
    print("  [PASS] empty input")

    # 2. insufficient
    det = DetectorClass(); det.cache = PluginCache()
    rows = data_fn(5)
    det.analyze(pd.DataFrame(rows), [], "s", {})
    assert det.cache.size == 5
    print("  [PASS] insufficient data, raw cached")

    # 3. 5 cycles
    all_rows = data_fn(n_points, drift_at=drift_at)
    det = DetectorClass(); det.cache = PluginCache()
    prev = None
    collected = []
    cycle_size = n_points // 5
    for c in range(5):
        chunk = all_rows[c * cycle_size:(c + 1) * cycle_size]
        new_ev = det.analyze(pd.DataFrame(chunk), [], "s", {}, previous_events=prev)
        collected.extend(new_ev)
        prev = [type("E", (), {"detected_at": e["detected_at"]}) for e in det.cache.drift_events]
    assert det.cache.size == n_points
    print(f"  [PASS] 5 cycles: {det.cache.size} raw, {len(det.cache.drift_events)} events")

    # 4. layer merge
    snap = det.cache.snapshot_for_display()
    assert len(snap["data"]) == n_points
    print(f"  [PASS] layer merge: {len(snap['data'])} rows")

    # 5. determinism
    d1 = DetectorClass(); d1.cache = PluginCache()
    d1.analyze(pd.DataFrame(all_rows), [], "s", {})
    one_events = d1.cache.drift_events

    d2 = DetectorClass(); d2.cache = PluginCache()
    for c in range(5):
        d2.analyze(pd.DataFrame(all_rows[c * cycle_size:(c + 1) * cycle_size]), [], "s", {})
    inc_events = d2.cache.drift_events

    one_dts = sorted([e["detected_at"] for e in one_events])
    inc_dts = sorted([e["detected_at"] for e in inc_events])
    assert len(one_dts) == len(inc_dts), f"Count: {len(one_dts)} vs {len(inc_dts)}"
    for a, b in zip(one_dts, inc_dts):
        assert str(a) == str(b), f"Mismatch: {a} vs {b}"
    print(f"  [PASS] determinism: {len(one_dts)} events match")

    # 6. chart_config
    cfg = DetectorClass().get_chart_config()
    assert len(cfg["layers"]) >= 1
    fields = [l["field"] for l in cfg["layers"]]
    print(f"  [PASS] chart_config: {fields}")

    print(f"  === {name} ALL PASS ===")


if __name__ == "__main__":
    run_suite("CUSUM", CusumDetector, make_data)
    run_suite("C-Chart", CChartDetector, make_count_data)
    run_suite("P-Chart", PChartDetector, make_proportion_data)
    run_suite("IMR-Chart", ImrChartDetector, make_data)
    run_suite("X-bar/R-Chart", XbarRChartDetector, make_data, n_points=250, drift_at=100)
