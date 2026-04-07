"""OCDD drift detector — IQR 기반 outlier ratio 방식 v2.0."""

from datetime import timedelta

import numpy as np
import pandas as pd

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class OcddDetector(DriftPlugin):
    """One-Class Drift Detector (IQR-based).

    Baseline 구간에서 IQR(사분위 범위)을 계산한 뒤,
    슬라이딩 윈도우 내 outlier 비율(alpha)이 rho를 초과하면 drift로 판단.
    Drift 감지 시 최근 inlier 중 상위 (1-rho)*100%만 남기고 재학습.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "window_size": 100,
        "rho": 0.3,
        "baseline_ratio": 0.3333,
    }

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        if data.empty:
            return []

        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]
        n = len(series)

        window_size = int(params["window_size"])
        rho = float(params["rho"])
        baseline_ratio = float(params["baseline_ratio"])

        # -- Baseline: IQR 계산 --
        baseline_end = int(n * baseline_ratio)
        if baseline_end < 10 or n <= baseline_end + window_size:
            return []

        baseline = series[:baseline_end]
        q1 = float(np.percentile(baseline, 25))
        q3 = float(np.percentile(baseline, 75))
        iqr = float(q3 - q1)
        if iqr <= 0:
            iqr = 1e-12

        lower_bound = float(q1 - 1.5 * iqr)
        upper_bound = float(q3 + 1.5 * iqr)

        # -- Outlier 판별 (전체 시리즈) --
        is_outlier = np.array(
            [(0 if lower_bound <= float(v) <= upper_bound else 1) for v in series],
            dtype=int,
        )

        # -- 슬라이딩 윈도우로 outlier ratio 계산 --
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

        # -- Cache에 데이터 기록 --
        # 전문가 차트가 cache.data에서 직접 series를 읽도록
        # outlier_ratio, alarm, is_outlier, rho를 row마다 적재한다.
        cache_rows = []
        for i in range(n):
            cache_rows.append({
                "timestamp": timestamps.iloc[i],
                "value": float(series[i]),
                "outlier_ratio": float(outlier_ratio_series[i]),
                "alarm": int(alarm_mask[i]),
                "is_outlier": int(is_outlier[i]),
                "rho": float(rho),
            })

        if self.cache is not None:
            self.cache.append_data(cache_rows)

        if not alarm_indices:
            return []

        # -- DriftEvent 생성 --
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1]

            # peak: outlier ratio가 가장 높은 지점
            peak_idx = group_start + int(
                np.argmax(outlier_ratio_series[group_start:group_end + 1])
            )
            peak_alpha = float(outlier_ratio_series[peak_idx])
            score = float(peak_alpha / rho) if rho > 0 else 0.0

            events.append(DriftEvent(
                stream=stream,
                plugin="ocdd",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=(
                    f"OCDD alarm: outlier_ratio={peak_alpha:.3f}, "
                    f"rho={rho:.2f}, IQR=[{lower_bound:.4f}, {upper_bound:.4f}]"
                ),
                data_ids=group_ids,
                data_count=int(len(group_ids)),
                detail={
                    "algorithm": "ocdd_iqr",
                    "q1": round(float(q1), 6),
                    "q3": round(float(q3), 6),
                    "iqr": round(float(iqr), 6),
                    "lower_bound": round(float(lower_bound), 6),
                    "upper_bound": round(float(upper_bound), 6),
                    "rho": float(rho),
                    "window_size": int(window_size),
                    "baseline_end": int(baseline_end),
                    "peak_alpha": round(float(peak_alpha), 4),
                    "alarm_count": int(group_end - group_start + 1),
                    "outlier_ratio_series": [float(x) for x in outlier_ratio_series.tolist()],
                    "alarm_mask": [int(x) for x in alarm_mask.tolist()],
                    "is_outlier": [int(x) for x in is_outlier.tolist()],
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
