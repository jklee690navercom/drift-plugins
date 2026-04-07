"""HAT drift detector — ADWIN 기반 적응형 윈도우 drift 탐지기 v2.0."""

from datetime import timedelta
import math

import numpy as np
import pandas as pd

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class HatDetector(DriftPlugin):
    """ADWIN(ADaptive WINdowing) 기반 drift 탐지기.

    값 스트림에 대해 적응형 윈도우를 유지하면서 분포 변화를 감지한다.
    윈도우를 두 부분(W_old, W_recent)으로 분할하여 평균 차이가
    통계적으로 유의미한지 검사한다.

    threshold = sqrt(1/(2*m) * ln(4*|W|/delta))
    여기서 m = 두 부분윈도우 크기의 조화평균.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "delta": 0.002,
        "baseline_ratio": 0.3,
    }

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        if data.empty:
            return []

        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]
        n = len(series)

        delta = float(params["delta"])
        baseline_ratio = float(params["baseline_ratio"])

        baseline_end = int(n * baseline_ratio)
        if baseline_end < 5 or (n - baseline_end) < 5:
            # 데이터가 너무 적어 ADWIN을 못 돌리지만, 차트가 멈추지 않도록
            # raw value를 cache에 적재한다 (running_mean/window_size는 placeholder).
            if self.cache is not None:
                cache_rows = [
                    {
                        "timestamp": timestamps.iloc[i],
                        "value": float(series[i]),
                        "running_mean": float(series[i]),
                        "window_size": 0,
                    }
                    for i in range(n)
                ]
                self.cache.append_data(cache_rows)
            return []

        # -- ADWIN 기반 순차 처리 --
        window = list(series[:baseline_end])
        window_sum = float(sum(window))

        mean_series = np.zeros(n)
        window_size_series = np.zeros(n, dtype=int)
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        # baseline 구간의 running mean / window size 기록
        for i in range(baseline_end):
            mean_series[i] = float(window_sum / len(window))
            window_size_series[i] = int(len(window))

        for i in range(baseline_end, n):
            # 새 값을 윈도우에 추가
            val = float(series[i])
            window.append(val)
            window_sum += val

            # ADWIN 분할 검사
            drift_found, cut_point = self._adwin_check(window, delta)

            if drift_found and cut_point is not None:
                # 드리프트 감지: 오래된 부분 제거하여 윈도우 축소
                window = window[cut_point:]
                window_sum = float(sum(window))
                alarm_mask[i] = 1
                alarm_indices.append(i)

            mean_series[i] = float(window_sum / len(window)) if len(window) > 0 else 0.0
            window_size_series[i] = int(len(window))

        # -- Cache 기록 (running mean, window size 포함) --
        cache_rows = []
        for i in range(n):
            cache_rows.append({
                "timestamp": timestamps.iloc[i],
                "value": float(series[i]),
                "running_mean": float(mean_series[i]),
                "window_size": int(window_size_series[i]),
            })

        if self.cache is not None:
            self.cache.append_data(cache_rows)

        if not alarm_indices:
            return []

        # -- DriftEvent 생성 --
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1]
            peak_idx = group_start

            # peak = 가장 큰 윈도우 크기 변화가 일어난 지점
            max_drop = 0
            for idx in range(group_start, group_end + 1):
                if alarm_mask[idx] == 1:
                    prev_ws = int(window_size_series[idx - 1]) if idx > 0 else 0
                    curr_ws = int(window_size_series[idx])
                    drop = prev_ws - curr_ws
                    if drop > max_drop:
                        max_drop = drop
                        peak_idx = idx

            # Score: 윈도우 축소 비율
            prev_ws = int(window_size_series[peak_idx - 1]) if peak_idx > 0 else int(window_size_series[peak_idx])
            curr_ws = int(window_size_series[peak_idx])
            if prev_ws > 0:
                score = float(prev_ws - curr_ws) / float(prev_ws)
            else:
                score = 0.0
            score = max(score, 0.01)  # 최소 score

            # 심각도에 맞게 score 조정 (0~1 -> severity mapping)
            adj_score = score * 3.0  # 스케일업

            events.append(DriftEvent(
                stream=stream,
                plugin="hat",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(adj_score),
                detected=True,
                score=round(float(adj_score), 4),
                message=(
                    f"ADWIN drift: window shrunk {prev_ws}->{curr_ws} "
                    f"(delta={delta})"
                ),
                data_ids=group_ids,
                data_count=int(len(group_ids)),
                detail={
                    "algorithm": "hat_adwin",
                    "delta": float(delta),
                    "baseline_ratio": float(baseline_ratio),
                    "window_before": int(prev_ws),
                    "window_after": int(curr_ws),
                    "alarm_count": int(group_end - group_start + 1),
                    "mean_series": [float(x) for x in mean_series.tolist()],
                    "window_size_series": [int(x) for x in window_size_series.tolist()],
                    "alarm_mask": [int(x) for x in alarm_mask.tolist()],
                },
            ))

        # Cache에 DriftEvent 기록
        if self.cache is not None and events:
            self.cache.append_events(events)

        return events

    @staticmethod
    def _adwin_check(window, delta):
        """ADWIN 분할 검사.

        윈도우 W를 가능한 모든 지점에서 (W_old, W_recent)로 분할하여
        두 부분의 평균 차이가 임계값을 초과하는지 검사한다.

        threshold = sqrt(1/(2*m) * ln(4*|W|/delta))
        m = 조화평균(|W_old|, |W_recent|)

        Returns:
            (drift_found, cut_point): drift 감지 여부와 분할 지점
        """
        n = len(window)
        if n < 6:
            return False, None

        total_sum = sum(window)
        best_cut = None
        best_diff = 0.0

        ln_val = math.log(4.0 * n / delta)

        # prefix_sum = sum(window[0:i]), 점진적으로 계산
        prefix_sum = sum(window[:3])

        # 최소 3개씩은 양쪽에 있어야 의미 있는 분할
        # i = 분할 지점: W_old = window[0:i], W_recent = window[i:n]
        for i in range(3, n - 2):
            if i > 3:
                prefix_sum += window[i - 1]
            n_old = i
            n_recent = n - i
            mean_old = prefix_sum / n_old
            mean_recent = (total_sum - prefix_sum) / n_recent
            diff = abs(mean_old - mean_recent)

            # 조화평균
            m = 2.0 * n_old * n_recent / (n_old + n_recent)
            threshold = math.sqrt(ln_val / (2.0 * m))

            if diff >= threshold and diff > best_diff:
                best_diff = diff
                best_cut = i

        if best_cut is not None:
            return True, best_cut
        return False, None

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
