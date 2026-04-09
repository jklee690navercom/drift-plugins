"""EWMA detector analyze() 패턴 단위 검증."""

import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from framework.plugin.cache import PluginCache
from plugins.ewma.drift_ewma.detector import EwmaDetector


def make_data(n_points, drift_at=None, seed=42):
    rng = np.random.RandomState(seed)
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(n_points):
        ts = base + timedelta(minutes=5 * i)
        mean = 0.0 if (drift_at is None or i < drift_at) else 3.0
        rows.append({"timestamp": ts, "value": float(rng.normal(mean, 1.0)), "count": 1})
    return rows


def test_empty_input():
    det = EwmaDetector()
    det.cache = PluginCache()
    result = det.analyze(pd.DataFrame(), [], "s", {})
    assert result == []
    assert det.cache.size == 0
    print("  [PASS] empty input")


def test_insufficient_data():
    det = EwmaDetector()
    det.cache = PluginCache()
    rows = make_data(10)
    result = det.analyze(pd.DataFrame(rows), [], "s", {})
    assert result == []
    assert det.cache.size == 10
    print("  [PASS] insufficient data, raw cached")


def test_incremental_5_cycles():
    det = EwmaDetector()
    det.cache = PluginCache()
    all_rows = make_data(200, drift_at=80)
    prev = None
    collected = []
    for cycle in range(5):
        chunk = all_rows[cycle * 40:(cycle + 1) * 40]
        new_events = det.analyze(pd.DataFrame(chunk), [], "s", {}, previous_events=prev)
        collected.extend(new_events)
        prev = [type("E", (), {"detected_at": e["detected_at"]}) for e in det.cache.drift_events]

    assert det.cache.size == 200
    print(f"  [PASS] 5 cycles: {det.cache.size} raw, {len(det.cache.drift_events)} events, {len(collected)} new")
    return det


def test_layer_merge(det):
    snap = det.cache.snapshot_for_display()
    data = snap["data"]
    assert len(data) == 200
    has_ewma = any("ewma" in r for r in data)
    has_ucl = any("ucl" in r for r in data)
    has_lcl = any("lcl" in r for r in data)
    assert has_ewma and has_ucl and has_lcl
    print(f"  [PASS] layer merge: ewma={has_ewma}, ucl={has_ucl}, lcl={has_lcl}")


def test_determinism():
    all_rows = make_data(200, drift_at=80)

    # one-shot
    d1 = EwmaDetector(); d1.cache = PluginCache()
    d1.analyze(pd.DataFrame(all_rows), [], "s", {})
    one_events = d1.cache.drift_events

    # incremental
    d2 = EwmaDetector(); d2.cache = PluginCache()
    for c in range(5):
        d2.analyze(pd.DataFrame(all_rows[c*40:(c+1)*40]), [], "s", {})
    inc_events = d2.cache.drift_events

    one_dts = sorted([e["detected_at"] for e in one_events])
    inc_dts = sorted([e["detected_at"] for e in inc_events])
    assert len(one_dts) == len(inc_dts), f"Count mismatch: {len(one_dts)} vs {len(inc_dts)}"
    for a, b in zip(one_dts, inc_dts):
        assert str(a) == str(b), f"Mismatch: {a} vs {b}"
    print(f"  [PASS] determinism: {len(one_dts)} events match")


def test_chart_config():
    det = EwmaDetector()
    cfg = det.get_chart_config()
    fields = [l["field"] for l in cfg["layers"]]
    assert "ewma" in fields and "ucl" in fields and "lcl" in fields
    print(f"  [PASS] chart_config: {fields}")


if __name__ == "__main__":
    print("=== EWMA analyze() 단위 검증 ===\n")
    print("1. 빈 입력"); test_empty_input()
    print("\n2. 데이터 부족"); test_insufficient_data()
    print("\n3. 5 cycles 누적"); det = test_incremental_5_cycles()
    print("\n4. layer merge"); test_layer_merge(det)
    print("\n5. 결정성"); test_determinism()
    print("\n6. chart_config"); test_chart_config()
    print("\n=== 모든 검증 통과 ===")
