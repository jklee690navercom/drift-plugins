"""OCDD drift detector — IQR 기반 outlier ratio 방식 v3.0.

1.D 책임 분리 (design_principles 6장) 적용:
- analyze() 3단계 패턴
- 1.B placeholder 제거
- baseline 고정 포인트 수
"""

from datetime import timedelta

import numpy as np

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class OcddDetector(DriftPlugin):
    """One-Class Drift Detector (IQR-based).

    Baseline 구간에서 IQR(사분위 범위)을 계산한 뒤,
    슬라이딩 윈도우 내 outlier 비율(alpha)이 rho를 초과하면 drift로 판단.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "window_size": 100,
        "rho": 0.3,
        "baseline_points": 100,
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
        window_size = int(params["window_size"])
        rho = float(params["rho"])
        baseline_points = int(params["baseline_points"])
        baseline_end = min(baseline_points, n)

        if baseline_end < 10 or n <= baseline_end + window_size:
            return []

        all_events, layer_rows = self._run_ocdd(
            snapshot, stream, window_size, rho, baseline_end,
        )
        # 누적 재실행 패턴 — replace_events=True 로 cache 통째 교체.
        new_events = self._dedupe_events(all_events, previous_events)

        self.cache.commit_analysis(
            layer_rows=layer_rows, events=all_events, replace_events=True,
        )
        return new_events

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        raise NotImplementedError("OcddDetector는 analyze()를 사용한다.")

    def _run_ocdd(self, snapshot, stream, window_size, rho, baseline_end):
        timestamps = [row["timestamp"] for row in snapshot]
        series = np.array(
            [float(row["value"]) for row in snapshot], dtype=float,
        )
        n = len(series)

        baseline = series[:baseline_end]
        q1 = float(np.percentile(baseline, 25))
        q3 = float(np.percentile(baseline, 75))
        iqr = float(q3 - q1)
        if iqr <= 0:
            iqr = 1e-12

        lower_bound = float(q1 - 1.5 * iqr)
        upper_bound = float(q3 + 1.5 * iqr)

        is_outlier = np.array(
            [
                0 if lower_bound <= float(v) <= upper_bound else 1
                for v in series
            ],
            dtype=int,
        )

        outlier_ratio_series = np.zeros(n, dtype=float)
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        for i in range(baseline_end, n - window_size + 1):
            window_outliers = is_outlier[i:i + window_size]
            alpha = float(np.sum(window_outliers)) / window_size
            mid = i + window_size // 2
            outlier_ratio_series[mid] = alpha
            if alpha >= rho:
                alarm_mask[mid] = 1
                alarm_indices.append(mid)

        layer_rows = [
            {
                "timestamp": timestamps[i],
                "outlier_ratio": float(outlier_ratio_series[i]),
                "alarm": int(alarm_mask[i]),
                "is_outlier": int(is_outlier[i]),
                "rho": float(rho),
            }
            for i in range(n)
        ]

        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            peak_idx = group_start + int(
                np.argmax(outlier_ratio_series[group_start:group_end + 1])
            )
            peak_alpha = float(outlier_ratio_series[peak_idx])
            score = float(peak_alpha / rho) if rho > 0 else 0.0

            events.append(DriftEvent(
                stream=stream,
                plugin="ocdd",
                detected_at=timestamps[peak_idx],
                data_from=timestamps[group_start],
                data_to=timestamps[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=(
                    f"OCDD alarm: outlier_ratio={peak_alpha:.3f}, "
                    f"rho={rho:.2f}, IQR=[{lower_bound:.4f}, {upper_bound:.4f}]"
                ),
                data_ids=[
                    f"{stream}:{idx}"
                    for idx in range(group_start, group_end + 1)
                ],
                data_count=int(group_end - group_start + 1),
                detail={
                    "algorithm": "ocdd_iqr",
                    "q1": round(float(q1), 6),
                    "q3": round(float(q3), 6),
                    "iqr": round(float(iqr), 6),
                    "lower_bound": round(float(lower_bound), 6),
                    "upper_bound": round(float(upper_bound), 6),
                    "rho": float(rho),
                    "window_size": int(window_size),
                    "baseline_points": int(baseline_end),
                    "peak_alpha": round(float(peak_alpha), 4),
                    "alarm_count": int(group_end - group_start + 1),
                },
            ))

        return events, layer_rows

    @staticmethod
    def _dedupe_events(all_events, previous_events):
        import pandas as pd

        def to_key(dt):
            if dt is None:
                return None
            try:
                return pd.Timestamp(dt).isoformat()
            except (ValueError, TypeError):
                return str(dt)

        existing = set()
        for e in (previous_events or []):
            dt = (
                e.detected_at if hasattr(e, "detected_at")
                else e.get("detected_at")
            )
            k = to_key(dt)
            if k is not None:
                existing.add(k)
        return [
            ev for ev in all_events if to_key(ev.detected_at) not in existing
        ]

    def get_chart_config(self):
        return {
            "mainLabel": "Value",
            "yLabel": "Value",
            "layers": [
                {
                    "type": "line",
                    "field": "outlier_ratio",
                    "label": "outlier ratio",
                    "color": "#ff7f0e",
                    "yAxis": "right",
                },
                {
                    "type": "line",
                    "field": "rho",
                    "label": "rho",
                    "color": "#d62728",
                    "yAxis": "right",
                },
            ],
        }

    @staticmethod
    def _group_consecutive(indices, gap=5):
        if not indices:
            return []
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
        if score >= 2.0:
            return "critical"
        if score >= 1.0:
            return "warning"
        return "normal"
