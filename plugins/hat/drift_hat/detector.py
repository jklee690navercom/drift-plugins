"""HAT drift detector — Hoeffding bound 기반 두 윈도우 평균 비교로 drift를 탐지."""

import numpy as np
import pandas as pd

from framework.plugin.base import DriftDetector
from framework.events.schema import DriftEvent


class HatDetector(DriftDetector):
    """Hoeffding Adaptive Tree 기반 ADWIN-like drift 탐지기.

    데이터를 순차적으로 처리하면서 두 윈도우(W0, W1)를 유지하고,
    두 윈도우 평균의 차이가 Hoeffding bound를 초과하면 drift로 판단.
    Score = |mean_diff| / hoeffding_bound.
    """

    DEFAULT_PARAMS = {
        "min_window": 30,
        "delta": 0.01,
        "reference_ratio": 0.5,
    }

    def detect(self, data, data_ids, stream, params):
        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]
        n = len(series)

        min_window = int(params["min_window"])
        delta = float(params["delta"])
        ref_ratio = float(params["reference_ratio"])

        ref_end = int(n * ref_ratio)
        if ref_end < min_window or (n - ref_end) < min_window:
            return []

        # ── 데이터 범위 (Hoeffding bound에 필요) ──
        data_range = float(np.max(series) - np.min(series))
        if data_range <= 0:
            data_range = 1e-8

        # ── 슬라이딩 윈도우 비교 (ADWIN-like) ──
        mean_diff_series = np.zeros(n)
        bound_series = np.zeros(n)
        score_series = np.zeros(n)
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        for i in range(ref_end + min_window, n):
            # W0: reference window (고정 또는 adaptive)
            w0_start = max(0, i - 2 * min_window)
            w0_end = i - min_window
            if w0_end <= w0_start:
                continue
            # W1: recent window
            w1_start = i - min_window
            w1_end = i

            w0 = series[w0_start:w0_end]
            w1 = series[w1_start:w1_end]

            n0 = len(w0)
            n1 = len(w1)
            if n0 < 2 or n1 < 2:
                continue

            mean0 = float(np.mean(w0))
            mean1 = float(np.mean(w1))
            mean_diff = abs(mean1 - mean0)

            # Hoeffding bound: epsilon = R * sqrt(ln(2/delta) / (2*m))
            # where m = harmonic mean of n0, n1
            m = 2.0 * n0 * n1 / (n0 + n1)
            epsilon = data_range * np.sqrt(np.log(2.0 / delta) / (2.0 * m))

            mean_diff_series[i] = mean_diff
            bound_series[i] = epsilon

            if epsilon > 0:
                score_series[i] = mean_diff / epsilon
            else:
                score_series[i] = 0.0

            if mean_diff > epsilon:
                alarm_mask[i] = 1
                alarm_indices.append(i)

        if not alarm_indices:
            return []

        # ── DriftEvent 생성 ──
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1]

            peak_idx = group_start + int(np.argmax(score_series[group_start:group_end + 1]))
            peak_diff = float(mean_diff_series[peak_idx])
            peak_bound = float(bound_series[peak_idx])
            score = float(score_series[peak_idx])

            events.append(DriftEvent(
                stream=stream,
                plugin="hat",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"HAT alarm: |mean_diff|={peak_diff:.4f}, bound={peak_bound:.4f} (delta={delta})",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "hat",
                    "peak_mean_diff": round(peak_diff, 6),
                    "peak_bound": round(peak_bound, 6),
                    "delta": delta,
                    "min_window": min_window,
                    "data_range": round(data_range, 4),
                    "alarm_count": group_end - group_start + 1,
                    "mean_diff_series": mean_diff_series.tolist(),
                    "bound_series": bound_series.tolist(),
                    "score_series": score_series.tolist(),
                    "alarm_mask": alarm_mask.tolist(),
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
