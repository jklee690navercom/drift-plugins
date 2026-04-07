"""Wasserstein distance drift detector — DriftPlugin 기반 운영 환경용."""

from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class WassersteinDetector(DriftPlugin):
    """Wasserstein 거리 기반 drift 탐지기.

    기준 구간(reference)과 슬라이딩 윈도우(test)의 Wasserstein 거리를
    EWMA 평활화하여 임계값을 초과하면 drift로 판단한다.
    D_t = λ * W_t + (1 - λ) * D_{t-1}
    Score = smoothed_distance / threshold.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "window_size": 50,
        "reference_ratio": 0.5,
        "threshold": 0.1,
        "lambda_smooth": 0.3,
        "update_reference": True,
        "baseline_ratio": 0.5,
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
        ref_ratio = float(params["reference_ratio"])
        threshold = float(params["threshold"])
        lambda_smooth = float(params["lambda_smooth"])
        update_reference = bool(params.get("update_reference", True))
        baseline_ratio = float(params.get("baseline_ratio", 0.5))

        # ── 기준 구간과 테스트 구간 분리 ──
        ref_end = int(n * ref_ratio)
        if ref_end < window_size or (n - ref_end) < window_size:
            # 데이터가 너무 적어 Wasserstein을 못 돌리지만, 차트가 멈추지
            # 않도록 raw value를 cache에 적재한다 (distance 등은 placeholder).
            if self.cache is not None:
                cache_rows = [
                    {
                        "timestamp": timestamps.iloc[i],
                        "value": float(series[i]),
                        "w_distance": 0.0,
                        "w_smoothed": 0.0,
                        "alarm": 0,
                        "threshold": float(threshold),
                    }
                    for i in range(n)
                ]
                self.cache.append_data(cache_rows)
            return []

        reference = series[:ref_end].copy()

        # ── Baseline 통계 (적응형 임계값용) ──
        baseline_end = int(n * baseline_ratio)
        if baseline_end < window_size * 2:
            baseline_end = min(ref_end, n)
        baseline_distances = []
        for i in range(window_size, baseline_end - window_size + 1, max(1, window_size // 2)):
            w = series[i:i + window_size]
            bd = wasserstein_distance(series[:i], w)
            baseline_distances.append(bd)

        if baseline_distances:
            baseline_mean = float(np.mean(baseline_distances))
            baseline_std = float(np.std(baseline_distances))
        else:
            baseline_mean = 0.0
            baseline_std = 1.0

        # ── 슬라이딩 윈도우 Wasserstein 거리 ──
        distance_series = np.zeros(n)
        smoothed_series = np.zeros(n)
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        prev_smoothed = 0.0

        for i in range(ref_end, n - window_size + 1):
            window = series[i:i + window_size]
            dist = wasserstein_distance(reference, window)
            mid = i + window_size // 2

            distance_series[mid] = float(dist)

            # EWMA smoothing: D_t = λ * W_t + (1-λ) * D_{t-1}
            smoothed = lambda_smooth * dist + (1 - lambda_smooth) * prev_smoothed
            smoothed_series[mid] = float(smoothed)
            prev_smoothed = smoothed

            if smoothed > threshold:
                alarm_mask[mid] = 1
                alarm_indices.append(mid)

                # 드리프트 후 기준 윈도우 업데이트
                if update_reference:
                    reference = window.copy()

        # ── Cache에 데이터 기록 ──
        # 전문가 차트가 cache.data에서 직접 series를 읽도록
        # distance, smoothed, alarm, threshold를 row마다 적재한다.
        cache_rows = []
        for i in range(len(series)):
            cache_rows.append({
                "timestamp": timestamps.iloc[i],
                "value": float(series[i]),
                "w_distance": float(distance_series[i]),
                "w_smoothed": float(smoothed_series[i]),
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

            peak_idx = group_start + int(np.argmax(smoothed_series[group_start:group_end + 1]))
            peak_dist = float(smoothed_series[peak_idx])
            raw_dist = float(distance_series[peak_idx])
            score = peak_dist / threshold if threshold > 0 else 0.0

            events.append(DriftEvent(
                stream=stream,
                plugin="wasserstein",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=f"Wasserstein alarm: smoothed={peak_dist:.4f}, raw={raw_dist:.4f}, threshold={threshold:.4f}",
                data_ids=group_ids,
                data_count=int(len(group_ids)),
                detail={
                    "algorithm": "wasserstein",
                    "peak_distance": round(float(raw_dist), 6),
                    "peak_smoothed": round(float(peak_dist), 6),
                    "threshold": float(threshold),
                    "lambda_smooth": float(lambda_smooth),
                    "window_size": int(window_size),
                    "reference_size": int(ref_end),
                    "update_reference": update_reference,
                    "alarm_count": int(group_end - group_start + 1),
                    "distance_series": [float(x) for x in distance_series.tolist()],
                    "smoothed_series": [float(x) for x in smoothed_series.tolist()],
                    "alarm_mask": [int(x) for x in alarm_mask.tolist()],
                    "ref_mean": round(float(np.mean(reference)), 4),
                    "ref_std": round(float(np.std(reference)), 4),
                    "baseline_mean": round(float(baseline_mean), 4),
                    "baseline_std": round(float(baseline_std), 4),
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
