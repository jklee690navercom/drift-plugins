"""KS Test drift detector — 슬라이딩 윈도우 KS 검정으로 분포 변화를 탐지."""

import numpy as np
import pandas as pd
from scipy import stats

from framework.plugin.base import DriftDetector
from framework.events.schema import DriftEvent


class KsTestDetector(DriftDetector):
    """Kolmogorov-Smirnov 검정 기반 drift 탐지기.

    기준 구간(reference)과 슬라이딩 윈도우(test)의 분포를 비교하여
    p-value가 유의수준 이하이면 drift로 판단한다.
    """

    DEFAULT_PARAMS = {
        "window_size": 50,
        "alpha": 0.05,
        "reference_ratio": 0.5,
    }

    def detect(self, data, data_ids, stream, params):
        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]
        n = len(series)

        window_size = int(params["window_size"])
        alpha = float(params["alpha"])
        ref_ratio = float(params["reference_ratio"])

        # ── 기준 구간과 테스트 구간 분리 ──
        ref_end = int(n * ref_ratio)
        if ref_end < window_size or (n - ref_end) < window_size:
            return []

        reference = series[:ref_end]

        # ── 슬라이딩 윈도우 KS 검정 ──
        ks_stats = np.zeros(n)
        p_values = np.ones(n)
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        for i in range(ref_end, n - window_size + 1):
            window = series[i:i + window_size]
            stat, pval = stats.ks_2samp(reference, window)
            mid = i + window_size // 2
            ks_stats[mid] = stat
            p_values[mid] = pval
            if pval < alpha:
                alarm_mask[mid] = 1
                alarm_indices.append(mid)

        if not alarm_indices:
            return []

        # ── DriftEvent 생성 ──
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1]

            # 그룹 내 최소 p-value 지점
            peak_idx = group_start + int(np.argmin(p_values[group_start:group_end + 1]))
            peak_stat = float(ks_stats[peak_idx])
            peak_pval = float(p_values[peak_idx])

            # score: -log10(p-value)를 정규화 (높을수록 심각)
            score = min(-np.log10(max(peak_pval, 1e-300)) / 10.0, 5.0)

            events.append(DriftEvent(
                stream=stream,
                plugin="ks_test",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"KS test: D={peak_stat:.4f}, p={peak_pval:.2e} (alpha={alpha})",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "ks_test",
                    "d_statistic": round(peak_stat, 6),
                    "p_value": peak_pval,
                    "alpha": alpha,
                    "window_size": window_size,
                    "reference_size": ref_end,
                    "alarm_count": group_end - group_start + 1,
                    "ks_series": ks_stats.tolist(),
                    "pvalue_series": p_values.tolist(),
                    "alarm_mask": alarm_mask.tolist(),
                    "ref_mean": round(float(np.mean(reference)), 4),
                    "ref_std": round(float(np.std(reference)), 4),
                    "test_mean": round(float(np.mean(series[group_start:group_end + 1])), 4),
                    "test_std": round(float(np.std(series[group_start:group_end + 1])), 4),
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
