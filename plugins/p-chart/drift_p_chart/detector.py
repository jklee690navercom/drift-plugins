"""P Chart drift detector — DriftPlugin 기반 운영 환경용."""

from datetime import timedelta

import numpy as np
import pandas as pd

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class PChartDetector(DriftPlugin):
    """P Chart 기반 drift 탐지기.

    불량률(비율)을 모니터링하는 제어 차트. 이항분포를 기반으로 한다.
    각 검사 그룹에서 불량 비율 p를 계산하여 제어 한계를 벗어나면 alarm.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "sample_size": 50,
        "reference_ratio": 0.5,
    }

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        if data.empty:
            return []

        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]
        sample_size = int(params["sample_size"])
        reference_ratio = float(params["reference_ratio"])

        n = len(series)
        ref_size = max(2, int(n * reference_ratio))

        # ── 기준 구간 통계량 ──
        ref_proportions = series[:ref_size]
        p_bar = float(np.mean(ref_proportions))

        # ── 제어 한계 ──
        sigma = np.sqrt(p_bar * (1 - p_bar) / sample_size) if p_bar > 0 and p_bar < 1 else 1e-8
        ucl = p_bar + 3 * sigma
        lcl = max(0.0, p_bar - 3 * sigma)
        cl = p_bar

        # ── 알람 판정 ──
        alarm_mask = ((series > ucl) | (series < lcl)).astype(int)

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

            # 가장 크게 벗어난 지점
            deviations = np.abs(series[group_start:group_end + 1] - cl)
            peak_idx = group_start + int(np.argmax(deviations))
            score = float(deviations.max()) / (3 * sigma) if sigma > 0 else 0.0

            events.append(DriftEvent(
                stream=stream,
                plugin="p_chart",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"P Chart alarm: p={series[peak_idx]:.4f}, UCL={ucl:.4f}, LCL={lcl:.4f}",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "p_chart",
                    "p_values": series.tolist(),
                    "ucl": ucl,
                    "lcl": lcl,
                    "cl": cl,
                    "sigma": sigma,
                    "alarm_mask": alarm_mask.tolist(),
                    "p_bar": p_bar,
                    "sample_size": sample_size,
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
        if score >= 2.0:
            return "critical"
        if score >= 1.0:
            return "warning"
        return "normal"
