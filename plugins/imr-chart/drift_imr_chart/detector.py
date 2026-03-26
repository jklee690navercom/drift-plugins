"""I-MR Chart drift detector — DriftPlugin 기반 운영 환경용."""

from datetime import timedelta

import numpy as np
import pandas as pd

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class ImrChartDetector(DriftPlugin):
    """I-MR Chart 기반 drift 탐지기.

    개별 관측값(Individual)과 연속 관측값 간의 이동범위(Moving Range)를
    동시에 모니터링하여 이상을 감지한다.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "reference_ratio": 0.5,
    }

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        if data.empty:
            return []

        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]

        n = len(series)
        ref_size = max(2, int(n * params["reference_ratio"]))

        # ── 이동범위(MR) 계산 ──
        mr = np.abs(np.diff(series))  # len = n-1
        mr_full = np.concatenate([[0.0], mr])  # 첫 번째는 0 (MR 없음)

        # ── 기준 구간 통계량 ──
        ref_values = series[:ref_size]
        ref_mr = mr[:ref_size - 1]  # 기준 구간의 MR

        ref_mean = float(np.mean(ref_values))
        mr_bar = float(np.mean(ref_mr))

        # ── I Chart 제어 한계 ──
        # 2.66 = 3/d2 where d2=1.128 for n=2
        ucl = ref_mean + 2.66 * mr_bar
        lcl = ref_mean - 2.66 * mr_bar
        cl = ref_mean

        # ── MR Chart 제어 한계 ──
        # D4 = 3.267 for n=2
        ucl_mr = 3.267 * mr_bar
        cl_mr = mr_bar

        # ── 알람 판정 ──
        alarm_i = (series > ucl) | (series < lcl)
        alarm_mr = np.zeros(n, dtype=bool)
        alarm_mr[1:] = mr > ucl_mr  # 첫 번째는 MR 없음
        alarm_mask = (alarm_i | alarm_mr).astype(int)

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

            # 가장 크게 벗어난 지점 찾기
            deviations = np.abs(series[group_start:group_end + 1] - cl)
            peak_idx = group_start + int(np.argmax(deviations))
            score = float(deviations.max()) / (2.66 * mr_bar) if mr_bar > 0 else 0.0

            events.append(DriftEvent(
                stream=stream,
                plugin="imr_chart",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"I-MR Chart alarm: value={series[peak_idx]:.4f}, UCL={ucl:.4f}, LCL={lcl:.4f}",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "imr_chart",
                    "i_values": series.tolist(),
                    "mr_values": mr_full.tolist(),
                    "ucl": ucl,
                    "lcl": lcl,
                    "cl": cl,
                    "ucl_mr": ucl_mr,
                    "cl_mr": cl_mr,
                    "alarm_mask": alarm_mask.tolist(),
                    "ref_mean": ref_mean,
                    "mr_bar": mr_bar,
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
