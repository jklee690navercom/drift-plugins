"""KS-test / Wasserstein detector analyze() 패턴 단위 검증."""

import sys, os, importlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 하이픈 디렉토리 import 우회
sys.path.insert(0, os.path.join(ROOT, "plugins", "ks-test"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "wasserstein"))

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from framework.plugin.cache import PluginCache
from drift_ks_test.detector import KsTestDetector
from drift_wasserstein.detector import WassersteinDetector


def make_data(n_points, drift_at=None, seed=42):
    rng = np.random.RandomState(seed)
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(n_points):
        ts = base + timedelta(minutes=5 * i)
        mean = 0.0 if (drift_at is None or i < drift_at) else 3.0
        rows.append({"timestamp": ts, "value": float(rng.normal(mean, 1.0)), "count": 1})
    return rows


def run_suite(name, DetectorClass, extra_params=None):
    print(f"\n{'='*50}")
    print(f"  {name} analyze()")
    print(f"{'='*50}")
    params = extra_params or {}

    # 1. empty
    det = DetectorClass(); det.cache = PluginCache()
    assert det.analyze(pd.DataFrame(), [], "s", params) == []
    print("  [PASS] empty input")

    # 2. insufficient
    det = DetectorClass(); det.cache = PluginCache()
    rows = make_data(20)
    det.analyze(pd.DataFrame(rows), [], "s", params)
    assert det.cache.size == 20
    print("  [PASS] insufficient data, raw cached")

    # 3. 5 cycles
    det = DetectorClass(); det.cache = PluginCache()
    all_rows = make_data(400, drift_at=150)
    prev = None
    collected = []
    for c in range(5):
        chunk = all_rows[c*80:(c+1)*80]
        new_ev = det.analyze(pd.DataFrame(chunk), [], "s", params, previous_events=prev)
        collected.extend(new_ev)
        prev = [type("E", (), {"detected_at": e["detected_at"]}) for e in det.cache.drift_events]
    assert det.cache.size == 400
    print(f"  [PASS] 5 cycles: {det.cache.size} raw, {len(det.cache.drift_events)} events, {len(collected)} new")

    # 4. layer merge
    snap = det.cache.snapshot_for_display()
    assert len(snap["data"]) == 400
    print(f"  [PASS] layer merge: {len(snap['data'])} merged rows")

    # 5. determinism
    d1 = DetectorClass(); d1.cache = PluginCache()
    d1.analyze(pd.DataFrame(all_rows), [], "s", params)
    one_events = d1.cache.drift_events

    d2 = DetectorClass(); d2.cache = PluginCache()
    for c in range(5):
        d2.analyze(pd.DataFrame(all_rows[c*80:(c+1)*80]), [], "s", params)
    inc_events = d2.cache.drift_events

    one_dts = sorted([e["detected_at"] for e in one_events])
    inc_dts = sorted([e["detected_at"] for e in inc_events])
    assert len(one_dts) == len(inc_dts), f"Count mismatch: {len(one_dts)} vs {len(inc_dts)}"
    for a, b in zip(one_dts, inc_dts):
        assert str(a) == str(b), f"Mismatch: {a} vs {b}"
    print(f"  [PASS] determinism: {len(one_dts)} events match")

    # 6. chart_config
    cfg = DetectorClass().get_chart_config()
    assert len(cfg["layers"]) >= 1
    fields = [l["field"] for l in cfg["layers"]]
    print(f"  [PASS] chart_config: {fields}")

    print(f"\n  === {name} ALL PASS ===")


if __name__ == "__main__":
    run_suite("KS-test", KsTestDetector)
    run_suite("Wasserstein", WassersteinDetector)
