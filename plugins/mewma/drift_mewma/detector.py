"""MEWMA drift detector — DriftPlugin 기반 운영 환경용."""

from datetime import timedelta

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class MewmaDetector(DriftPlugin):
    """MEWMA(Multivariate EWMA) 기반 drift 탐지기 (단변량 적용).

    EWMA 평활화: z_t = lambda * x_t + (1 - lambda) * z_{t-1}
    D² 통계량: (z_t - ref_mean)² / ref_var
    chi2(1) 임계값을 초과하면 drift로 판단한다.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "lambda_": 0.1,
        "reference_ratio": 0.5,
        "alpha": 0.01,
    }

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        if data.empty:
            return []

        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]
        n = len(series)

        lam = float(params["lambda_"])
        ref_ratio = float(params["reference_ratio"])
        alpha = float(params["alpha"])

        # ── 기준 구간 ──
        ref_end = int(n * ref_ratio)
        if ref_end < 10 or (n - ref_end) < 10:
            return []

        reference = series[:ref_end]
        ref_mean = float(np.mean(reference))
        ref_var = float(np.var(reference))
        if ref_var <= 0:
            ref_var = 1e-12

        # ── EWMA 평활화 ──
        z = np.zeros(n)
        z[0] = series[0]
        for t in range(1, n):
            z[t] = lam * series[t] + (1 - lam) * z[t - 1]

        # ── D² 통계량 ──
        d_squared = (z - ref_mean) ** 2 / ref_var

        # ── chi2(1) 임계값 ──
        threshold = sp_stats.chi2.ppf(1 - alpha, df=1)

        alarm_mask = np.zeros(n, dtype=int)
        alarm_mask[ref_end:] = (d_squared[ref_end:] > threshold).astype(int)
        alarm_indices = list(np.where(alarm_mask == 1)[0])

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

        # ── DriftEvent 생성 ──
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1]

            peak_idx = group_start + int(np.argmax(d_squared[group_start:group_end + 1]))
            peak_d2 = float(d_squared[peak_idx])
            score = peak_d2 / threshold

            events.append(DriftEvent(
                stream=stream,
                plugin="mewma",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"MEWMA alarm: D²={peak_d2:.2f}, threshold={threshold:.2f} (alpha={alpha})",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "mewma",
                    "d_squared_peak": round(peak_d2, 4),
                    "threshold": round(threshold, 4),
                    "lambda": lam,
                    "alpha": alpha,
                    "ref_mean": round(ref_mean, 4),
                    "ref_var": round(ref_var, 6),
                    "alarm_count": group_end - group_start + 1,
                    "ewma_series": z.tolist(),
                    "d_squared_series": d_squared.tolist(),
                    "alarm_mask": alarm_mask.tolist(),
                },
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
