"""C Chart drift detector v3.0.

1.D 책임 분리 (design_principles 6장):
- analyze() 3단계 패턴, baseline 고정 포인트 수
"""

from datetime import timedelta

import numpy as np

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class CChartDetector(DriftPlugin):
    """C Chart 기반 drift 탐지기.

    일정 단위에서 발생하는 결함/사건 건수를 모니터링하는 제어 차트.
    포아송분포 기반: UCL = c̄ + 3√c̄, LCL = max(0, c̄ - 3√c̄).
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "baseline_points": 30,
    }

    def analyze(self, new_data, data_ids, stream, params,
                calculated_until=None, previous_events=None):
        if new_data.empty or self.cache is None:
            return []

        snapshot = self.cache.append_and_snapshot(
            new_data.to_dict("records")
        )
        n = len(snapshot)

        params = {**self.DEFAULT_PARAMS, **params}
        baseline_points = int(params["baseline_points"])
        baseline_end = min(baseline_points, n)

        if baseline_end < 2 or (n - baseline_end) < 1:
            return []

        all_events, layer_rows = self._run_c_chart(
            snapshot, stream, baseline_end,
        )
        new_events = self._dedupe_events(all_events, previous_events)

        self.cache.commit_analysis(
            layer_rows=layer_rows, events=all_events, replace_events=True,
        )
        return new_events

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        raise NotImplementedError("CChartDetector는 analyze()를 사용한다.")

    def _run_c_chart(self, snapshot, stream, baseline_end):
        timestamps = [row["timestamp"] for row in snapshot]
        series = np.array(
            [float(row["value"]) for row in snapshot], dtype=float,
        )
        n = len(series)

        ref_counts = series[:baseline_end]
        c_bar = float(np.mean(ref_counts))

        sqrt_c_bar = float(np.sqrt(c_bar)) if c_bar > 0 else 1e-8
        ucl = float(c_bar + 3 * sqrt_c_bar)
        lcl = float(max(0.0, c_bar - 3 * sqrt_c_bar))
        cl = float(c_bar)

        alarm_mask = ((series > ucl) | (series < lcl)).astype(int)
        alarm_indices = list(np.where(alarm_mask == 1)[0])

        layer_rows = [
            {
                "timestamp": timestamps[i],
                "ucl": ucl,
                "cl": cl,
                "lcl": lcl,
                "alarm": int(alarm_mask[i]),
            }
            for i in range(n)
        ]

        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            deviations = np.abs(series[group_start:group_end + 1] - cl)
            peak_idx = group_start + int(np.argmax(deviations))
            score = float(deviations.max()) / (3 * sqrt_c_bar) if sqrt_c_bar > 0 else 0.0

            events.append(DriftEvent(
                stream=stream,
                plugin="c_chart",
                detected_at=timestamps[peak_idx],
                data_from=timestamps[group_start],
                data_to=timestamps[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=f"C Chart alarm: count={series[peak_idx]:.0f}, UCL={ucl:.2f}, LCL={lcl:.2f}",
                data_ids=[
                    f"{stream}:{idx}"
                    for idx in range(group_start, group_end + 1)
                ],
                data_count=int(group_end - group_start + 1),
                detail={
                    "algorithm": "c_chart",
                    "ucl": float(ucl),
                    "lcl": float(lcl),
                    "cl": float(cl),
                    "c_bar": float(c_bar),
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
            "mainLabel": "Count",
            "yLabel": "Count",
            "layers": [
                {"type": "line", "field": "ucl", "label": "UCL", "color": "#d62728", "dash": [5, 5]},
                {"type": "line", "field": "cl", "label": "CL", "color": "#2ca02c"},
                {"type": "line", "field": "lcl", "label": "LCL", "color": "#d62728", "dash": [5, 5]},
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
