"""Wasserstein distance drift detector — 기준 분포와 슬라이딩 윈도우 간 Wasserstein 거리로 drift를 탐지."""

import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance

from framework.plugin.base import DriftDetector
from framework.events.schema import DriftEvent


class WassersteinDetector(DriftDetector):
    """Wasserstein 거리 기반 drift 탐지기.

    기준 구간(reference)과 슬라이딩 윈도우(test)의 Wasserstein 거리를
    계산하여 임계값을 초과하면 drift로 판단한다.
    Score = wasserstein_distance / threshold.
    """

    DEFAULT_PARAMS = {
        "window_size": 50,
        "reference_ratio": 0.5,
        "threshold": 0.1,
    }

    def detect(self, data, data_ids, stream, params):
        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]
        n = len(series)

        window_size = int(params["window_size"])
        ref_ratio = float(params["reference_ratio"])
        threshold = float(params["threshold"])

        # ── 기준 구간과 테스트 구간 분리 ──
        ref_end = int(n * ref_ratio)
        if ref_end < window_size or (n - ref_end) < window_size:
            return []

        reference = series[:ref_end]

        # ── 슬라이딩 윈도우 Wasserstein 거리 ──
        w_distances = np.zeros(n)
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        for i in range(ref_end, n - window_size + 1):
            window = series[i:i + window_size]
            dist = wasserstein_distance(reference, window)
            mid = i + window_size // 2
            w_distances[mid] = dist
            if dist > threshold:
                alarm_mask[mid] = 1
                alarm_indices.append(mid)

        if not alarm_indices:
            return []

        # ── DriftEvent 생성 ──
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1]

            peak_idx = group_start + int(np.argmax(w_distances[group_start:group_end + 1]))
            peak_dist = float(w_distances[peak_idx])
            score = peak_dist / threshold

            events.append(DriftEvent(
                stream=stream,
                plugin="wasserstein",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"Wasserstein alarm: distance={peak_dist:.4f}, threshold={threshold:.4f}",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "wasserstein",
                    "peak_distance": round(peak_dist, 6),
                    "threshold": threshold,
                    "window_size": window_size,
                    "reference_size": ref_end,
                    "alarm_count": group_end - group_start + 1,
                    "distance_series": w_distances.tolist(),
                    "alarm_mask": alarm_mask.tolist(),
                    "ref_mean": round(float(np.mean(reference)), 4),
                    "ref_std": round(float(np.std(reference)), 4),
                },
            ))

        return events

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
