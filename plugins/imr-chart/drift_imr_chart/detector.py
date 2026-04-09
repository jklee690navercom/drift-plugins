"""I-MR Chart drift detector v3.0.

1.D 책임 분리 (design_principles 6장):
- analyze() 3단계 패턴, baseline 고정 포인트 수
- MR 값을 layer에 추가하여 I Chart + MR Chart 동시 표시
"""

from datetime import timedelta

import numpy as np

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class ImrChartDetector(DriftPlugin):
    """I-MR Chart 기반 drift 탐지기.

    개별 관측값(Individual)과 이동범위(Moving Range)를 동시에 모니터링.
    I Chart: UCL = X̄ + 2.66·MR̄, LCL = X̄ - 2.66·MR̄
    MR Chart: UCL = 3.267·MR̄
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

        if baseline_end < 3 or (n - baseline_end) < 1:
            return []

        all_events, layer_rows = self._run_imr_chart(
            snapshot, stream, baseline_end,
        )
        new_events = self._dedupe_events(all_events, previous_events)

        self.cache.commit_analysis(
            layer_rows=layer_rows, events=all_events, replace_events=True,
        )
        return new_events

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        raise NotImplementedError("ImrChartDetector는 analyze()를 사용한다.")

    def _run_imr_chart(self, snapshot, stream, baseline_end):
        timestamps = [row["timestamp"] for row in snapshot]
        series = np.array(
            [float(row["value"]) for row in snapshot], dtype=float,
        )
        n = len(series)

        # 이동범위
        mr = np.abs(np.diff(series))
        mr_full = np.concatenate([[0.0], mr])

        # Baseline 통계량
        ref_values = series[:baseline_end]
        ref_mr = mr[:baseline_end - 1]

        ref_mean = float(np.mean(ref_values))
        mr_bar = float(np.mean(ref_mr)) if len(ref_mr) > 0 else 1e-8
        if mr_bar <= 0:
            mr_bar = 1e-8

        # I Chart 한계
        ucl = float(ref_mean + 2.66 * mr_bar)
        lcl = float(ref_mean - 2.66 * mr_bar)
        cl = float(ref_mean)

        # MR Chart 한계
        ucl_mr = float(3.267 * mr_bar)
        cl_mr = float(mr_bar)

        # Alarm
        alarm_i = (series > ucl) | (series < lcl)
        alarm_mr = np.zeros(n, dtype=bool)
        alarm_mr[1:] = mr > ucl_mr
        alarm_mask = (alarm_i | alarm_mr).astype(int)
        alarm_indices = list(np.where(alarm_mask == 1)[0])

        # layer_rows — MR 포함
        layer_rows = [
            {
                "timestamp": timestamps[i],
                "mr": float(mr_full[i]),
                "ucl": ucl,
                "cl": cl,
                "lcl": lcl,
                "ucl_mr": ucl_mr,
                "cl_mr": cl_mr,
                "alarm": int(alarm_mask[i]),
            }
            for i in range(n)
        ]

        # events
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            deviations = np.abs(series[group_start:group_end + 1] - cl)
            peak_idx = group_start + int(np.argmax(deviations))
            score = float(deviations.max()) / (2.66 * mr_bar) if mr_bar > 0 else 0.0

            events.append(DriftEvent(
                stream=stream,
                plugin="imr_chart",
                detected_at=timestamps[peak_idx],
                data_from=timestamps[group_start],
                data_to=timestamps[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=f"I-MR Chart alarm: value={series[peak_idx]:.4f}, UCL={ucl:.4f}, LCL={lcl:.4f}",
                data_ids=[
                    f"{stream}:{idx}"
                    for idx in range(group_start, group_end + 1)
                ],
                data_count=int(group_end - group_start + 1),
                detail={
                    "algorithm": "imr_chart",
                    "ucl": float(ucl),
                    "lcl": float(lcl),
                    "cl": float(cl),
                    "ucl_mr": float(ucl_mr),
                    "cl_mr": float(cl_mr),
                    "ref_mean": float(ref_mean),
                    "mr_bar": float(mr_bar),
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
                {"type": "line", "field": "ucl", "label": "UCL", "color": "#d62728", "dash": [5, 5]},
                {"type": "line", "field": "cl", "label": "CL", "color": "#2ca02c"},
                {"type": "line", "field": "lcl", "label": "LCL", "color": "#d62728", "dash": [5, 5]},
                {"type": "line", "field": "mr", "label": "MR", "color": "#9467bd", "yAxis": "right"},
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
