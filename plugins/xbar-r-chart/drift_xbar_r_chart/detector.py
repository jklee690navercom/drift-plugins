"""X-bar/R Chart drift detector v3.0.

1.D 책임 분리 (design_principles 6장):
- analyze() 3단계 패턴, baseline 고정 포인트 수
- R chart layer 추가
"""

from datetime import timedelta

import numpy as np

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class XbarRChartDetector(DriftPlugin):
    """X-bar/R Chart 기반 drift 탐지기.

    데이터를 서브그룹으로 묶어 각 그룹의 평균(X-bar)과 범위(R)를
    모니터링하여 평균 이동과 산포 변화를 감지한다.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "subgroup_size": 5,
        "baseline_points": 30,
    }

    _A2_TABLE = {2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483, 7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308}
    _D4_TABLE = {2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114, 6: 2.004, 7: 1.924, 8: 1.864, 9: 1.816, 10: 1.777}
    _D3_TABLE = {2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0, 7: 0.076, 8: 0.136, 9: 0.184, 10: 0.223}

    def analyze(self, new_data, data_ids, stream, params,
                calculated_until=None, previous_events=None):
        if new_data.empty or self.cache is None:
            return []

        snapshot = self.cache.append_and_snapshot(
            new_data.to_dict("records")
        )
        n = len(snapshot)

        params = {**self.DEFAULT_PARAMS, **params}
        subgroup_size = int(params["subgroup_size"])
        baseline_points = int(params["baseline_points"])

        # 서브그룹으로 나눌 수 있는 최소 데이터
        n_groups = n // subgroup_size
        if n_groups < 2:
            return []

        baseline_end = min(baseline_points, n_groups)
        if baseline_end < 2 or (n_groups - baseline_end) < 1:
            return []

        all_events, layer_rows = self._run_xbar_r_chart(
            snapshot, stream, subgroup_size, baseline_end,
        )
        new_events = self._dedupe_events(all_events, previous_events)

        self.cache.commit_analysis(
            layer_rows=layer_rows, events=all_events, replace_events=True,
        )
        return new_events

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        raise NotImplementedError("XbarRChartDetector는 analyze()를 사용한다.")

    def _run_xbar_r_chart(self, snapshot, stream, subgroup_size, baseline_end):
        timestamps = [row["timestamp"] for row in snapshot]
        series = np.array(
            [float(row["value"]) for row in snapshot], dtype=float,
        )
        n = len(series)
        n_groups = n // subgroup_size
        trimmed = series[:n_groups * subgroup_size]
        groups = trimmed.reshape(n_groups, subgroup_size)

        xbar_values = groups.mean(axis=1)
        r_values = groups.max(axis=1) - groups.min(axis=1)

        # Baseline 통계량
        ref_xbar = xbar_values[:baseline_end]
        ref_r = r_values[:baseline_end]

        x_double_bar = float(np.mean(ref_xbar))
        r_bar = float(np.mean(ref_r))
        if r_bar <= 0:
            r_bar = 1e-8

        A2 = float(self._A2_TABLE.get(subgroup_size, 0.577))
        D4 = float(self._D4_TABLE.get(subgroup_size, 2.114))
        D3 = float(self._D3_TABLE.get(subgroup_size, 0.0))

        ucl_xbar = float(x_double_bar + A2 * r_bar)
        lcl_xbar = float(x_double_bar - A2 * r_bar)
        cl_xbar = float(x_double_bar)

        ucl_r = float(D4 * r_bar)
        lcl_r = float(D3 * r_bar)
        cl_r = float(r_bar)

        # Alarm (그룹 단위)
        alarm_xbar = (xbar_values > ucl_xbar) | (xbar_values < lcl_xbar)
        alarm_r = (r_values > ucl_r) | (r_values < lcl_r)
        alarm_combined = (alarm_xbar | alarm_r).astype(int)
        alarm_indices = list(np.where(alarm_combined == 1)[0])

        # layer_rows — 원본 row 단위 (서브그룹 대표값을 그룹 내 모든 row에 복사)
        layer_rows = []
        for i in range(n):
            group_idx = min(i // subgroup_size, n_groups - 1)
            layer_rows.append({
                "timestamp": timestamps[i],
                "xbar": float(xbar_values[group_idx]),
                "r_value": float(r_values[group_idx]),
                "ucl_xbar": ucl_xbar,
                "cl_xbar": cl_xbar,
                "lcl_xbar": lcl_xbar,
                "ucl_r": ucl_r,
                "cl_r": cl_r,
                "lcl_r": lcl_r,
                "alarm": int(alarm_combined[group_idx]),
            })

        # events (그룹 인덱스 기반)
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            data_start = group_start * subgroup_size
            data_end = min((group_end + 1) * subgroup_size - 1, n - 1)

            deviations = np.abs(xbar_values[group_start:group_end + 1] - cl_xbar)
            peak_group = group_start + int(np.argmax(deviations))
            score = float(deviations.max()) / (A2 * r_bar) if r_bar > 0 else 0.0

            # 그룹 대표 timestamp
            peak_ts_idx = min((peak_group + 1) * subgroup_size - 1, n - 1)

            events.append(DriftEvent(
                stream=stream,
                plugin="xbar_r_chart",
                detected_at=timestamps[peak_ts_idx],
                data_from=timestamps[data_start],
                data_to=timestamps[data_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=(
                    f"X-bar/R Chart alarm: X-bar={float(xbar_values[peak_group]):.4f}, "
                    f"UCL={ucl_xbar:.4f}, LCL={lcl_xbar:.4f}"
                ),
                data_ids=[
                    f"{stream}:{idx}"
                    for idx in range(data_start, data_end + 1)
                ],
                data_count=int(data_end - data_start + 1),
                detail={
                    "algorithm": "xbar_r_chart",
                    "ucl_xbar": float(ucl_xbar),
                    "lcl_xbar": float(lcl_xbar),
                    "cl_xbar": float(cl_xbar),
                    "ucl_r": float(ucl_r),
                    "lcl_r": float(lcl_r),
                    "cl_r": float(cl_r),
                    "subgroup_size": int(subgroup_size),
                    "x_double_bar": float(x_double_bar),
                    "r_bar": float(r_bar),
                    "baseline_points": int(baseline_end),
                    "alarm_count": int(group_end - group_start + 1),
                },
            ))

        return events, layer_rows

    @staticmethod
    def _dedupe_events(all_events, previous_events):
        import pandas as pd
        def to_key(dt):
            if dt is None: return None
            try: return pd.Timestamp(dt).isoformat()
            except (ValueError, TypeError): return str(dt)
        existing = set()
        for e in (previous_events or []):
            dt = e.detected_at if hasattr(e, "detected_at") else e.get("detected_at")
            k = to_key(dt)
            if k is not None: existing.add(k)
        return [ev for ev in all_events if to_key(ev.detected_at) not in existing]

    def get_chart_config(self):
        return {
            "mainLabel": "Value",
            "yLabel": "Value",
            "layers": [
                {"type": "line", "field": "ucl_xbar", "label": "UCL (X̄)", "color": "#d62728", "dash": [5, 5]},
                {"type": "line", "field": "cl_xbar", "label": "CL (X̄)", "color": "#2ca02c"},
                {"type": "line", "field": "lcl_xbar", "label": "LCL (X̄)", "color": "#d62728", "dash": [5, 5]},
                {"type": "line", "field": "r_value", "label": "R", "color": "#9467bd", "yAxis": "right"},
            ],
        }

    @staticmethod
    def _group_consecutive(indices, gap=3):
        if not indices: return []
        groups = []
        start = prev = indices[0]
        for idx in indices[1:]:
            if idx - prev > gap:
                groups.append((start, prev))
                start = idx
            prev = idx
        groups.append((start, prev))
        return groups

    @staticmethod
    def _score_to_severity(score):
        if score >= 2.0: return "critical"
        if score >= 1.0: return "warning"
        return "normal"
