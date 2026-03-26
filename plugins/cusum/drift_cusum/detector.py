"""CUSUM drift detector — DriftPlugin 기반 운영 환경용."""

from datetime import timedelta

import numpy as np
import pandas as pd

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class CusumDetector(DriftPlugin):
    """누적합(CUSUM) 기반 drift 탐지기.

    양방향 CUSUM으로 평균의 상승/하락을 동시에 감지한다.
    입력 시계열을 표준화(median, MAD)한 후 CUSUM 통계량을 계산한다.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "k": 0.25,      # slack value (표준화된 단위)
        "h": 5.0,       # threshold (표준화된 단위)
        "reset": True,   # alarm 후 CUSUM 리셋 여부
    }

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        if data.empty:
            return []

        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]

        # ── 표준화 (robust: median + MAD) ──
        median = float(np.median(series))
        mad = float(np.median(np.abs(series - median)))
        sigma = 1.4826 * mad
        if sigma <= 0:
            sigma = 1e-8
        standardized = (series - median) / sigma

        # ── CUSUM 계산 ──
        k = params["k"]
        h = params["h"]
        reset = params["reset"]

        s_pos_arr, s_neg_arr, alarm_mask = self._cusum_traces(
            standardized, k=k, h=h, reset=reset,
        )

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

        # ── DriftEvent 생성 ──
        if not alarm_indices:
            return []

        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1] if data_ids else []

            peak_idx = group_start + int(np.argmax(
                np.maximum(s_pos_arr[group_start:group_end + 1],
                           s_neg_arr[group_start:group_end + 1])
            ))
            peak_s_pos = float(s_pos_arr[peak_idx])
            peak_s_neg = float(s_neg_arr[peak_idx])
            score = max(peak_s_pos, peak_s_neg) / h
            direction = "positive" if peak_s_pos >= peak_s_neg else "negative"

            ev = DriftEvent(
                stream=stream,
                plugin="cusum",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"CUSUM {direction}: S+={peak_s_pos:.2f}, S-={peak_s_neg:.2f}",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "cusum",
                    "s_pos": round(peak_s_pos, 4),
                    "s_neg": round(peak_s_neg, 4),
                    "threshold_h": h,
                    "k": k,
                    "alarm_direction": direction,
                    "median": round(median, 4),
                    "sigma": round(sigma, 4),
                },
            )
            events.append(ev)

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
    def _cusum_traces(y, k=0.25, h=5.0, reset=True):
        """양방향 CUSUM 통계량 계산."""
        s_pos_vals = []
        s_neg_vals = []
        alarms = []
        s_pos = 0.0
        s_neg = 0.0
        for v in y:
            s_pos = max(0.0, s_pos + v - k)
            s_neg = max(0.0, s_neg - v - k)
            alarm = int(s_pos > h or s_neg > h)
            s_pos_vals.append(s_pos)
            s_neg_vals.append(s_neg)
            alarms.append(alarm)
            if alarm and reset:
                s_pos = 0.0
                s_neg = 0.0
        return np.array(s_pos_vals), np.array(s_neg_vals), np.array(alarms, dtype=int)

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
