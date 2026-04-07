"""Hotelling T2 drift detector — DriftPlugin 기반 운영 환경용.

v2.0: 공분산 shrinkage 정규화, chi2 임계값, baseline 분리.
"""

from datetime import timedelta

import numpy as np
import pandas as pd

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class HotellingDetector(DriftPlugin):
    """Hotelling T2 drift detector.

    Hotelling T2 다변량 제어 차트 기반 drift 탐지.
    - Shrinkage 정규화로 수치 안정성 확보
    - Chi-squared 분포 기반 임계값 (univariate: df=1)
    - Baseline 분리로 기준 분포 설정
    - 슬라이딩 윈도우 T² 계산
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "alpha": 0.05,
        "window_size": 50,
        "baseline_ratio": 0.5,
        "shrinkage": 0.01,
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

        alpha = float(params["alpha"])
        window_size = int(params["window_size"])
        baseline_ratio = float(params["baseline_ratio"])
        shrinkage = float(params["shrinkage"])

        # ── Baseline 분리 ──
        baseline_end = int(len(series) * baseline_ratio)
        if baseline_end < 2 or (len(series) - baseline_end) < window_size:
            # 데이터가 너무 적어 Hotelling T²를 못 돌리지만, 차트가 멈추지
            # 않도록 raw value를 cache에 적재한다 (t2 등은 placeholder).
            if self.cache is not None:
                cache_rows = [
                    {
                        "timestamp": timestamps.iloc[i],
                        "value": float(series[i]),
                        "t2": 0.0,
                        "alarm": 0,
                        "threshold": 0.0,
                    }
                    for i in range(len(series))
                ]
                self.cache.append_data(cache_rows)
            return []

        baseline = series[:baseline_end]
        ref_mean = float(np.mean(baseline))
        ref_var = float(np.var(baseline, ddof=1))

        # Shrinkage 정규화: Σ_reg = (1-s)*Σ + s*I
        # univariate: σ²_reg = (1-s)*σ² + s
        reg_var = (1 - shrinkage) * ref_var + shrinkage
        if reg_var <= 0:
            reg_var = 1e-8

        # Chi-squared 임계값 (univariate: p=1)
        from scipy.stats import chi2
        p = 1  # univariate dimension
        threshold = float(chi2.ppf(1 - alpha, df=p))

        # ── 슬라이딩 윈도우 T² 계산 ──
        t2_values = np.zeros(len(series))
        alarm_mask = np.zeros(len(series), dtype=int)

        for i in range(baseline_end, len(series) - window_size + 1):
            window = series[i:i + window_size]
            window_mean = float(np.mean(window))
            diff = window_mean - ref_mean
            # T² = n * (x̄ - μ)² / σ²_reg (univariate Hotelling)
            t2 = float(window_size * (diff ** 2) / reg_var)
            mid = i + window_size // 2
            t2_values[mid] = t2
            if t2 > threshold:
                alarm_mask[mid] = 1
                alarm_indices.append(mid)

        # t2_series를 Python float 리스트로 변환
        t2_series = [float(v) for v in t2_values]
        alarm_mask_list = [int(v) for v in alarm_mask]

        if alarm_indices:
            peak_idx = alarm_indices[int(np.argmax(t2_values[alarm_indices]))]
            peak_t2 = float(t2_values[peak_idx])
            score = float(peak_t2 / threshold)
            message = (f"Hotelling T²={peak_t2:.2f}, "
                       f"threshold={threshold:.2f} (chi2, alpha={alpha}), "
                       f"shrinkage={shrinkage}")
            detail = {
                "algorithm": "hotelling_t2",
                "threshold": float(round(threshold, 4)),
                "alpha": float(alpha),
                "window_size": int(window_size),
                "baseline_ratio": float(baseline_ratio),
                "baseline_end": int(baseline_end),
                "shrinkage": float(shrinkage),
                "ref_mean": float(round(ref_mean, 4)),
                "ref_var": float(round(ref_var, 6)),
                "reg_var": float(round(reg_var, 6)),
                "peak_t2": float(round(peak_t2, 4)),
                "t2_series": t2_series,
                "alarm_mask": alarm_mask_list,
            }

        # ── Cache에 데이터 기록 ──
        # 전문가 차트가 cache.data에서 직접 series를 읽도록 t2/alarm/threshold 적재.
        cache_rows = []
        for i in range(len(series)):
            cache_rows.append({
                "timestamp": timestamps.iloc[i],
                "value": float(series[i]),
                "t2": float(t2_series[i]),
                "alarm": int(alarm_mask_list[i]),
                "threshold": float(threshold),
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
                score=float(round(score, 4)),
                message=message,
                data_ids=data_ids[group_start:group_end + 1],
                data_count=int(group_end - group_start + 1),
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
