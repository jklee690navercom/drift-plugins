"""SHAP drift detector — Statistical Profile Drift Detection v3.0.

단변량 데이터에서 rolling window의 통계 프로파일(mean, std, skewness, kurtosis)을
추출하고, 기준 구간 대비 모니터링 구간의 프로파일 변화를
정규화된 유클리드 거리로 측정하여 drift를 탐지한다.

1.D 책임 분리(design_principles 6장): analyze() 3단계 패턴, 1.B placeholder 제거.
"""

from datetime import timedelta

import numpy as np
from scipy import stats as sp_stats

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class ShapDetector(DriftPlugin):
    """Statistical Profile Drift 탐지기."""

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "window_size": 100,
        # 누적 재실행 안정성을 위해 baseline 윈도우 수를 고정한다.
        "baseline_windows": 50,
        "threshold": 3.0,
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
        baseline_windows = int(params["baseline_windows"])
        threshold = float(params["threshold"])

        if n < window_size * 2:
            return []

        num_windows = n - window_size + 1
        baseline_end = min(baseline_windows, num_windows)
        if baseline_end < 2 or baseline_end >= num_windows:
            return []

        all_events, layer_rows = self._run_shap(
            snapshot, stream, window_size, baseline_end, threshold,
        )
        # 누적 재실행 패턴 — replace_events=True 로 cache 통째 교체.
        new_events = self._dedupe_events(all_events, previous_events)

        self.cache.commit_analysis(
            layer_rows=layer_rows, events=all_events, replace_events=True,
        )
        return new_events

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        raise NotImplementedError("ShapDetector는 analyze()를 사용한다.")

    def _run_shap(self, snapshot, stream, window_size, baseline_end, threshold):
        timestamps = [row["timestamp"] for row in snapshot]
        series = np.array(
            [float(row["value"]) for row in snapshot], dtype=float,
        )
        n = len(series)
        num_windows = n - window_size + 1

        # 각 윈도우의 통계 프로파일
        profile_names = ["mean", "std", "skewness", "kurtosis"]
        profiles = np.zeros((num_windows, 4))
        for i in range(num_windows):
            window = series[i:i + window_size]
            profiles[i, 0] = float(np.mean(window))
            profiles[i, 1] = (
                float(np.std(window, ddof=1)) if len(window) > 1 else 0.0
            )
            profiles[i, 2] = float(sp_stats.skew(window, bias=False))
            profiles[i, 3] = float(sp_stats.kurtosis(window, bias=False))

        baseline_profiles = profiles[:baseline_end]
        baseline_mean = np.mean(baseline_profiles, axis=0)
        baseline_std = np.std(baseline_profiles, axis=0, ddof=1)
        baseline_std[baseline_std < 1e-10] = 1.0

        profile_distances = np.zeros(n)
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        for i in range(baseline_end, num_windows):
            center_idx = min(i + window_size // 2, n - 1)
            diff = (profiles[i] - baseline_mean) / baseline_std
            dist = float(np.sqrt(np.sum(diff ** 2)))
            profile_distances[center_idx] = dist
            if dist > threshold:
                alarm_mask[center_idx] = 1
                alarm_indices.append(center_idx)

        layer_rows = [
            {
                "timestamp": timestamps[i],
                "profile_distance": float(profile_distances[i]),
                "alarm": int(alarm_mask[i]),
                "threshold": float(threshold),
            }
            for i in range(n)
        ]

        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            peak_idx = group_start + int(np.argmax(
                profile_distances[group_start:group_end + 1]))
            peak_distance = float(profile_distances[peak_idx])
            score = float(peak_distance / threshold)

            win_idx = max(0, min(peak_idx - window_size // 2, num_windows - 1))
            profile_detail = {}
            for j, name in enumerate(profile_names):
                profile_detail[f"current_{name}"] = round(
                    float(profiles[win_idx, j]), 4,
                )
                profile_detail[f"baseline_{name}"] = round(
                    float(baseline_mean[j]), 4,
                )

            events.append(DriftEvent(
                stream=stream,
                plugin="shap",
                detected_at=timestamps[peak_idx],
                data_from=timestamps[group_start],
                data_to=timestamps[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=(
                    f"SHAP profile drift: distance={peak_distance:.4f} "
                    f"> threshold={threshold:.1f}"
                ),
                data_ids=[
                    f"{stream}:{idx}"
                    for idx in range(group_start, group_end + 1)
                ],
                data_count=int(group_end - group_start + 1),
                detail={
                    "algorithm": "shap",
                    "peak_distance": round(float(peak_distance), 4),
                    "threshold": float(threshold),
                    "window_size": int(window_size),
                    "baseline_windows": int(baseline_end),
                    "alarm_count": int(group_end - group_start + 1),
                    "baseline_mean_profile": {
                        name: round(float(baseline_mean[j]), 4)
                        for j, name in enumerate(profile_names)
                    },
                    **profile_detail,
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
                    "field": "profile_distance",
                    "label": "profile distance",
                    "color": "#1f77b4",
                    "yAxis": "right",
                },
                {
                    "type": "line",
                    "field": "threshold",
                    "label": "threshold",
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
