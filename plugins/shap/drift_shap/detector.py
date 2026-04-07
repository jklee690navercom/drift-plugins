"""SHAP drift detector — Statistical Profile Drift Detection v2.0.

단변량 데이터에서 rolling window의 통계 프로파일(mean, std, skewness, kurtosis)을
추출하고, 기준 구간 대비 모니터링 구간의 프로파일 변화를
정규화된 유클리드 거리로 측정하여 drift를 탐지한다.
"""

from datetime import timedelta

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class ShapDetector(DriftPlugin):
    """Statistical Profile Drift 탐지기.

    단변량 시계열에서 rolling window statistics(mean, std, skewness, kurtosis)를
    프로파일로 추출한 뒤, 기준 구간의 평균 프로파일과 모니터링 구간의
    프로파일 간 정규화 유클리드 거리를 측정한다.
    거리가 threshold를 초과하면 drift alarm을 발생시킨다.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "window_size": 100,
        "baseline_ratio": 0.5,
        "threshold": 3.0,
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
        baseline_ratio = float(params["baseline_ratio"])
        threshold = float(params["threshold"])

        if n < window_size * 2:
            # 데이터가 너무 적어 SHAP을 못 돌리지만, 차트가 멈추지 않도록
            # raw value를 cache에 적재한다 (profile_distance 등은 placeholder).
            if self.cache is not None:
                cache_rows = [
                    {
                        "timestamp": timestamps.iloc[i],
                        "value": float(series[i]),
                        "profile_distance": 0.0,
                        "alarm": 0,
                        "threshold": float(threshold),
                    }
                    for i in range(n)
                ]
                self.cache.append_data(cache_rows)
            return []

        # ── 각 윈도우의 통계 프로파일 계산 ──
        profile_names = ["mean", "std", "skewness", "kurtosis"]
        num_windows = n - window_size + 1
        profiles = np.zeros((num_windows, 4))

        for i in range(num_windows):
            window = series[i:i + window_size]
            profiles[i, 0] = float(np.mean(window))
            profiles[i, 1] = float(np.std(window, ddof=1)) if len(window) > 1 else 0.0
            profiles[i, 2] = float(sp_stats.skew(window, bias=False))
            profiles[i, 3] = float(sp_stats.kurtosis(window, bias=False))

        # ── 기준 구간의 평균 프로파일과 표준편차 ──
        baseline_end = int(num_windows * baseline_ratio)
        if baseline_end < 2:
            # baseline 윈도우가 부족해 비교 불가지만, 차트가 멈추지 않도록
            # raw value를 cache에 적재한다.
            if self.cache is not None:
                cache_rows = [
                    {
                        "timestamp": timestamps.iloc[i],
                        "value": float(series[i]),
                        "profile_distance": 0.0,
                        "alarm": 0,
                        "threshold": float(threshold),
                    }
                    for i in range(n)
                ]
                self.cache.append_data(cache_rows)
            return []

        baseline_profiles = profiles[:baseline_end]
        baseline_mean = np.mean(baseline_profiles, axis=0)
        baseline_std = np.std(baseline_profiles, axis=0, ddof=1)
        # 0으로 나누기 방지
        baseline_std[baseline_std < 1e-10] = 1.0

        # ── 모니터링 구간: 정규화 유클리드 거리 ──
        profile_distances = np.zeros(n)
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        for i in range(baseline_end, num_windows):
            # 윈도우 중심 인덱스
            center_idx = i + window_size // 2
            if center_idx >= n:
                center_idx = n - 1

            # 정규화 유클리드 거리
            diff = (profiles[i] - baseline_mean) / baseline_std
            dist = float(np.sqrt(np.sum(diff ** 2)))
            profile_distances[center_idx] = dist

            if dist > threshold:
                alarm_mask[center_idx] = 1
                alarm_indices.append(center_idx)

        # ── Cache에 데이터 기록 ──
        # 전문가 차트가 cache.data에서 직접 series를 읽도록
        # profile_distance, alarm, threshold를 row마다 적재한다.
        cache_rows = []
        for i in range(n):
            cache_rows.append({
                "timestamp": timestamps.iloc[i],
                "value": float(series[i]),
                "profile_distance": float(profile_distances[i]),
                "alarm": int(alarm_mask[i]),
                "threshold": float(threshold),
            })

        if self.cache is not None:
            self.cache.append_data(cache_rows)

        if not alarm_indices:
            return []

        # ── DriftEvent 생성 ──
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1]

            peak_idx = group_start + int(np.argmax(
                profile_distances[group_start:group_end + 1]))
            peak_distance = float(profile_distances[peak_idx])
            score = float(peak_distance / threshold)

            # 해당 윈도우의 프로파일 상세
            win_idx = peak_idx - window_size // 2
            if win_idx < 0:
                win_idx = 0
            if win_idx >= num_windows:
                win_idx = num_windows - 1

            profile_detail = {}
            for j, name in enumerate(profile_names):
                profile_detail[f"current_{name}"] = round(float(profiles[win_idx, j]), 4)
                profile_detail[f"baseline_{name}"] = round(float(baseline_mean[j]), 4)

            events.append(DriftEvent(
                stream=stream,
                plugin="shap",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=(
                    f"SHAP profile drift: distance={peak_distance:.4f} "
                    f"> threshold={threshold:.1f}"
                ),
                data_ids=group_ids,
                data_count=int(len(group_ids)),
                detail={
                    "algorithm": "shap",
                    "peak_distance": round(float(peak_distance), 4),
                    "threshold": float(threshold),
                    "window_size": int(window_size),
                    "baseline_windows": int(baseline_end),
                    "alarm_count": int(group_end - group_start + 1),
                    "profile_distance_series": [
                        round(float(v), 4) for v in profile_distances.tolist()
                    ],
                    "alarm_mask": [int(v) for v in alarm_mask.tolist()],
                    "baseline_mean_profile": {
                        name: round(float(baseline_mean[j]), 4)
                        for j, name in enumerate(profile_names)
                    },
                    **profile_detail,
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
