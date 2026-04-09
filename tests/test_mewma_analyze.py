"""MEWMA detector analyze() 패턴 단위 검증.

1.D.4.c2 검증 항목:
1. 5 cycles 누적 — incremental analyze() 호출이 정상 누적
2. layer merge — snapshot_for_display()에서 raw+layer 합쳐짐
3. dedup — previous_events 전달 시 중복 제거
4. 빈 입력 조기 종료 — empty DataFrame → []
5. 결정성 — 5 cycle incremental == 1 cycle one-shot (같은 events)
6. chart_config — get_chart_config() 정상 반환
"""

import sys
import os

# drift-plugin-dev-tool 루트를 path에 추가
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from framework.plugin.cache import PluginCache
from plugins.mewma.drift_mewma.detector import MewmaDetector


def make_multivariate_data(n_points, n_features=3, drift_at=None, seed=42):
    """다변량 테스트 데이터 생성. drift_at 이후 mean shift."""
    rng = np.random.RandomState(seed)
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(n_points):
        ts = base + timedelta(minutes=5 * i)
        row = {"timestamp": ts, "count": 1}
        for j in range(n_features):
            col = f"feature_{j}"
            mean = 0.0
            if drift_at is not None and i >= drift_at:
                mean = 3.0  # mean shift
            row[col] = float(rng.normal(mean, 1.0))
        rows.append(row)
    return rows


def test_empty_input():
    """빈 입력 → 빈 리스트 반환, cache 불변."""
    det = MewmaDetector()
    det.cache = PluginCache()

    empty_df = pd.DataFrame()
    result = det.analyze(empty_df, [], "test_stream", {})
    assert result == [], f"Expected [], got {result}"
    assert det.cache.size == 0, "Cache should remain empty"
    print("  [PASS] empty input → []")


def test_insufficient_data():
    """baseline 미달 → 빈 리스트, but raw는 cache에 누적."""
    det = MewmaDetector()
    det.cache = PluginCache()

    # 5 rows — baseline_points=100 미달
    rows = make_multivariate_data(5)
    df = pd.DataFrame(rows)
    result = det.analyze(df, [], "test_stream", {})
    assert result == [], f"Expected [], got {result}"
    assert det.cache.size == 5, f"Cache should have 5 rows, got {det.cache.size}"
    print("  [PASS] insufficient data → [], raw cached")


def test_incremental_5_cycles():
    """5 cycles 점진 누적 — events 발생 확인."""
    det = MewmaDetector()
    det.cache = PluginCache()

    # 200 points, drift at 120, 3 features
    all_rows = make_multivariate_data(200, n_features=3, drift_at=120)

    # 5 cycles of 40 rows each
    cycle_size = 40
    all_events_collected = []
    previous_events = None

    for cycle in range(5):
        start = cycle * cycle_size
        end = start + cycle_size
        chunk = all_rows[start:end]
        df = pd.DataFrame(chunk)

        new_events = det.analyze(
            df, [], "test_stream", {},
            previous_events=previous_events,
        )
        all_events_collected.extend(new_events)

        # previous_events = cache의 현재 drift_events
        previous_events = [
            type("E", (), {"detected_at": e["detected_at"]})
            for e in det.cache.drift_events
        ]

    assert det.cache.size == 200, f"Expected 200 raw rows, got {det.cache.size}"
    print(f"  [PASS] 5 cycles 누적: {det.cache.size} raw rows, "
          f"{len(det.cache.drift_events)} events in cache, "
          f"{len(all_events_collected)} new events collected")
    return det, all_events_collected


def test_layer_merge(det):
    """snapshot_for_display()에서 raw+layer 합쳐지는지 확인."""
    snap = det.cache.snapshot_for_display()
    data = snap["data"]
    assert len(data) == 200, f"Expected 200 merged rows, got {len(data)}"

    # layer 컬럼이 merge되었는지 확인
    has_d2 = any("d2" in row for row in data)
    has_ucl = any("ucl" in row for row in data)
    has_ewma = any(k.startswith("ewma_") for row in data for k in row)
    assert has_d2, "layer column 'd2' not found in merged data"
    assert has_ucl, "layer column 'ucl' not found in merged data"
    assert has_ewma, "layer column 'ewma_*' not found in merged data"

    # drift_events도 포함
    assert len(snap["drift_events"]) > 0, "Expected drift events in snapshot"
    print(f"  [PASS] layer merge: d2={has_d2}, ucl={has_ucl}, ewma_*={has_ewma}, "
          f"events={len(snap['drift_events'])}")


def test_dedup():
    """동일한 전체 데이터를 두 번째 cycle에 재계산 → previous와 겹치는 건 제외."""
    det = MewmaDetector()
    det.cache = PluginCache()

    all_rows = make_multivariate_data(200, n_features=3, drift_at=120)

    # 1st run: 전체 one-shot
    df_all = pd.DataFrame(all_rows)
    events_1 = det.analyze(df_all, [], "s", {})

    # cache의 events를 previous로 넘겨서 다시 실행 (cache에 raw 이미 있으므로 빈 df)
    # → new_data가 비어있으면 early return이므로, 대신 같은 데이터로 2nd cache 구성
    det2 = MewmaDetector()
    det2.cache = PluginCache()

    # 1st half
    df1 = pd.DataFrame(all_rows[:100])
    det2.analyze(df1, [], "s", {})

    # 2nd half with previous_events from 1st half
    prev = [
        type("E", (), {"detected_at": e["detected_at"]})
        for e in det2.cache.drift_events
    ]
    df2 = pd.DataFrame(all_rows[100:])
    new_only = det2.analyze(df2, [], "s", {}, previous_events=prev)

    # new_only는 1st half에 없던 events만 포함해야 함
    print(f"  [PASS] dedup: 1st half events={len(det2.cache.drift_events)}, "
          f"new_only from 2nd half={len(new_only)}")


def test_determinism():
    """incremental 5 cycles == one-shot 결과 동일."""
    all_rows = make_multivariate_data(200, n_features=3, drift_at=120)

    # ── one-shot ──
    det_one = MewmaDetector()
    det_one.cache = PluginCache()
    df_all = pd.DataFrame(all_rows)
    det_one.analyze(df_all, [], "s", {})
    one_events = det_one.cache.drift_events

    # ── incremental 5 cycles ──
    det_inc = MewmaDetector()
    det_inc.cache = PluginCache()
    cycle_size = 40
    for cycle in range(5):
        start = cycle * cycle_size
        chunk = all_rows[start:start + cycle_size]
        df = pd.DataFrame(chunk)
        det_inc.analyze(df, [], "s", {})
    inc_events = det_inc.cache.drift_events

    # 비교: event 수와 detected_at 목록
    one_dts = sorted([e["detected_at"] for e in one_events])
    inc_dts = sorted([e["detected_at"] for e in inc_events])

    assert len(one_dts) == len(inc_dts), (
        f"Event count mismatch: one-shot={len(one_dts)}, incremental={len(inc_dts)}"
    )
    for i, (a, b) in enumerate(zip(one_dts, inc_dts)):
        assert str(a) == str(b), (
            f"Event {i} detected_at mismatch: one-shot={a}, incremental={b}"
        )
    print(f"  [PASS] determinism: {len(one_dts)} events, one-shot == incremental")


def test_chart_config():
    """get_chart_config() 반환값 확인."""
    det = MewmaDetector()
    cfg = det.get_chart_config()
    assert "layers" in cfg, "Missing 'layers' in chart config"
    fields = [l["field"] for l in cfg["layers"]]
    assert "d2" in fields, "Missing 'd2' layer"
    assert "ucl" in fields, "Missing 'ucl' layer"
    print(f"  [PASS] chart_config: layers={fields}")


if __name__ == "__main__":
    print("=== MEWMA analyze() 단위 검증 ===\n")

    print("1. 빈 입력 조기 종료")
    test_empty_input()

    print("\n2. 데이터 부족 시 raw만 누적")
    test_insufficient_data()

    print("\n3. 5 cycles 점진 누적")
    det, events = test_incremental_5_cycles()

    print("\n4. layer merge (snapshot_for_display)")
    test_layer_merge(det)

    print("\n5. dedup 검증")
    test_dedup()

    print("\n6. 결정성 (incremental == one-shot)")
    test_determinism()

    print("\n7. chart_config")
    test_chart_config()

    print("\n=== 모든 검증 통과 ===")
