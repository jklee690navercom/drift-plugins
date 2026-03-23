"""C Chart drift detector — 건수(Count) 제어 차트 기반 이상 탐지."""

import numpy as np
import pandas as pd

from framework.plugin.base import DriftDetector
from framework.events.schema import DriftEvent


class CChartDetector(DriftDetector):
    """C Chart 기반 drift 탐지기.

    일정 단위(시간, 배치 등)에서 발생하는 결함/사건의 건수를 모니터링하는 제어 차트.
    포아송분포를 기반으로 한다.
    """

    DEFAULT_PARAMS = {
        "reference_ratio": 0.5,
    }

    def detect(self, data, data_ids, stream, params):
        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]
        reference_ratio = float(params["reference_ratio"])

        n = len(series)
        ref_size = max(2, int(n * reference_ratio))

        # ── 기준 구간 통계량 ──
        ref_counts = series[:ref_size]
        c_bar = float(np.mean(ref_counts))

        # ── 제어 한계 ──
        sqrt_c_bar = np.sqrt(c_bar) if c_bar > 0 else 1e-8
        ucl = c_bar + 3 * sqrt_c_bar
        lcl = max(0.0, c_bar - 3 * sqrt_c_bar)
        cl = c_bar

        # ── 알람 판정 ──
        alarm_mask = ((series > ucl) | (series < lcl)).astype(int)

        alarm_indices = list(np.where(alarm_mask == 1)[0])

        if not alarm_indices:
            return []

        # ── DriftEvent 생성 ──
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1]

            # 가장 크게 벗어난 지점
            deviations = np.abs(series[group_start:group_end + 1] - cl)
            peak_idx = group_start + int(np.argmax(deviations))
            score = float(deviations.max()) / (3 * sqrt_c_bar) if sqrt_c_bar > 0 else 0.0

            events.append(DriftEvent(
                stream=stream,
                plugin="c_chart",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"C Chart alarm: count={series[peak_idx]:.0f}, UCL={ucl:.2f}, LCL={lcl:.2f}",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "c_chart",
                    "c_values": series.tolist(),
                    "ucl": ucl,
                    "lcl": lcl,
                    "cl": cl,
                    "alarm_mask": alarm_mask.tolist(),
                    "c_bar": c_bar,
                },
            ))

        return events

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
