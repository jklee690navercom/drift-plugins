"""Hotelling T2 drift detector — DriftPlugin 기반 운영 환경용."""

from datetime import timedelta

import numpy as np
import pandas as pd

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class HotellingDetector(DriftPlugin):
    """Hotelling T2 drift detector.

    Hotelling T2 다변량 제어 차트 기반 drift 탐지
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "alpha": 0.01,
        "window_size": 50,
        "reference_ratio": 0.5,
    }

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        if data.empty:
            return []

        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]

        alarm_indices = []
        score = 0.0
        message = ""
        detail = {}

        alpha = params["alpha"]
        window_size = int(params["window_size"])
        ref_ratio = params["reference_ratio"]

        # 기준 구간 분리
        ref_end = int(len(series) * ref_ratio)
        if ref_end < window_size or (len(series) - ref_end) < window_size:
            return []

        reference = series[:ref_end]
        ref_mean = float(np.mean(reference))
        ref_var = float(np.var(reference, ddof=1))
        if ref_var <= 0:
            ref_var = 1e-8

        from scipy.stats import chi2
        threshold = float(chi2.ppf(1 - alpha, df=1))

        t2_values = np.zeros(len(series))
        alarm_mask = np.zeros(len(series), dtype=int)

        for i in range(ref_end, len(series) - window_size + 1):
            window = series[i:i + window_size]
            window_mean = np.mean(window)
            diff = window_mean - ref_mean
            t2 = window_size * (diff ** 2) / ref_var
            mid = i + window_size // 2
            t2_values[mid] = t2
            if t2 > threshold:
                alarm_mask[mid] = 1
                alarm_indices.append(mid)

        if alarm_indices:
            peak_idx = alarm_indices[int(np.argmax(t2_values[alarm_indices]))]
            peak_t2 = float(t2_values[peak_idx])
            score = peak_t2 / threshold
            message = f"Hotelling T²={peak_t2:.2f}, threshold={threshold:.2f} (alpha={alpha})"
            detail = {
                "algorithm": "hotelling_t2",
                "threshold": round(threshold, 4),
                "alpha": alpha,
                "window_size": window_size,
                "ref_mean": round(ref_mean, 4),
                "ref_var": round(ref_var, 6),
                "t2_series": t2_values.tolist(),
                "alarm_mask": alarm_mask.tolist(),
            }

        # ── Cache에 데이터 기록 ──
        cache_rows = []
        for i in range(len(series)):
            cache_rows.append({
                "timestamp": timestamps.iloc[i],
                "value": float(series[i]),
            })

        if self.cache is not None:
            self.cache.append_data(cache_rows)

        if not alarm_indices:
            return []

        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            events.append(DriftEvent(
                stream=stream,
                plugin="hotelling",
                detected_at=timestamps.iloc[group_end],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=message,
                data_ids=data_ids[group_start:group_end + 1],
                data_count=group_end - group_start + 1,
                detail=detail,
            ))

        # Cache에 DriftEvent 기록
        if self.cache is not None and events:
            self.cache.append_events(events)

        return events

    def get_chart_config(self):
        return {
            "mainLabel": "Value",
            "yLabel": "Value",
            "layers": [],
        }

    @staticmethod
    def _group_consecutive(indices, gap=3):
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
        if score >= 2.0: return "critical"
        if score >= 1.0: return "warning"
        return "normal"
