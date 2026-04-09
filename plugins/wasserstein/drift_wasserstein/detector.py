"""Wasserstein distance drift detector v3.0.

1.D 책임 분리 (design_principles 6장):
- analyze() 3단계 패턴, 1.B placeholder 제거
- 누적 재실행 + replace_events=True
- baseline 고정 포인트 수
- reference mutation은 순차 결정적 (baseline_points 고정이 전제)
"""

from datetime import timedelta

import numpy as np
from scipy.stats import wasserstein_distance

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class WassersteinDetector(DriftPlugin):
    """Wasserstein 거리 기반 drift 탐지기.

    기준 구간(reference)과 슬라이딩 윈도우(test)의 Wasserstein 거리를
    EWMA 평활화하여 임계값을 초과하면 drift로 판단한다.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "window_size": 50,
        "baseline_points": 100,
        "threshold": 0.1,
        "lambda_smooth": 0.3,
        "update_reference": True,
    }

    def analyze(self, new_data, data_ids, stream, params,
                calculated_until=None, previous_events=None):
        if new_data.empty or self.cache is None:
            return []

        # ── 1단계: 누적 + 스냅샷 (락 안, 짧음) ──
        snapshot = self.cache.append_and_snapshot(
            new_data.to_dict("records")
        )
        n = len(snapshot)

        params = {**self.DEFAULT_PARAMS, **params}
        window_size = int(params["window_size"])
        baseline_points = int(params["baseline_points"])
        threshold = float(params["threshold"])
        lambda_smooth = float(params["lambda_smooth"])
        update_reference = bool(params.get("update_reference", True))

        ref_end = min(baseline_points, n)
        if ref_end < window_size or (n - ref_end) < window_size:
            return []

        # ── 2단계: 계산 (락 밖) ──
        all_events, layer_rows = self._run_wasserstein(
            snapshot, stream, window_size, ref_end, threshold,
            lambda_smooth, update_reference,
        )
        new_events = self._dedupe_events(all_events, previous_events)

        # ── 3단계: 커밋 (락 안, 짧음) ──
        self.cache.commit_analysis(
            layer_rows=layer_rows, events=all_events, replace_events=True,
        )
        return new_events

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        raise NotImplementedError("WassersteinDetector는 analyze()를 사용한다.")

    # ── 알고리즘 (락 밖에서 실행) ──

    def _run_wasserstein(self, snapshot, stream, window_size, ref_end,
                         threshold, lambda_smooth, update_reference):
        timestamps = [row["timestamp"] for row in snapshot]
        series = np.array(
            [float(row["value"]) for row in snapshot], dtype=float,
        )
        n = len(series)

        reference = series[:ref_end].copy()

        # 슬라이딩 윈도우 Wasserstein 거리
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

            smoothed = lambda_smooth * dist + (1 - lambda_smooth) * prev_smoothed
            smoothed_series[mid] = float(smoothed)
            prev_smoothed = smoothed

            if smoothed > threshold:
                alarm_mask[mid] = 1
                alarm_indices.append(mid)

                # Reference 갱신 (순차 결정적 — baseline_points 고정이 전제)
                if update_reference:
                    reference = window.copy()

        # layer_rows
        layer_rows = [
            {
                "timestamp": timestamps[i],
                "w_distance": float(distance_series[i]),
                "w_smoothed": float(smoothed_series[i]),
                "alarm": int(alarm_mask[i]),
                "threshold": float(threshold),
            }
            for i in range(n)
        ]

        # events
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            peak_idx = group_start + int(
                np.argmax(smoothed_series[group_start:group_end + 1]))
            peak_dist = float(smoothed_series[peak_idx])
            raw_dist = float(distance_series[peak_idx])
            score = peak_dist / threshold if threshold > 0 else 0.0

            events.append(DriftEvent(
                stream=stream,
                plugin="wasserstein",
                detected_at=timestamps[peak_idx],
                data_from=timestamps[group_start],
                data_to=timestamps[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=(
                    f"Wasserstein alarm: smoothed={peak_dist:.4f}, "
                    f"raw={raw_dist:.4f}, threshold={threshold:.4f}"
                ),
                data_ids=[
                    f"{stream}:{idx}"
                    for idx in range(group_start, group_end + 1)
                ],
                data_count=int(group_end - group_start + 1),
                detail={
                    "algorithm": "wasserstein",
                    "peak_distance": round(float(raw_dist), 6),
                    "peak_smoothed": round(float(peak_dist), 6),
                    "threshold": float(threshold),
                    "lambda_smooth": float(lambda_smooth),
                    "window_size": int(window_size),
                    "baseline_points": int(ref_end),
                    "update_reference": update_reference,
                    "alarm_count": int(group_end - group_start + 1),
                },
            ))

        return events, layer_rows

    @staticmethod
    def _dedupe_events(all_events, previous_events):
        import pandas as pd

        def to_key(dt):
            if dt is None:
                return None
            try:
                return pd.Timestamp(dt).isoformat()
            except (ValueError, TypeError):
                return str(dt)

        existing = set()
        for e in (previous_events or []):
            dt = (
                e.detected_at if hasattr(e, "detected_at")
                else e.get("detected_at")
            )
            k = to_key(dt)
            if k is not None:
                existing.add(k)
        return [
            ev for ev in all_events if to_key(ev.detected_at) not in existing
        ]

    def get_chart_config(self):
        return {
            "mainLabel": "Value",
            "yLabel": "Value",
            "layers": [
                {
                    "type": "line",
                    "field": "w_smoothed",
                    "label": "Smoothed distance",
                    "color": "#1f77b4",
                    "yAxis": "right",
                },
                {
                    "type": "line",
                    "field": "threshold",
                    "label": "Threshold",
                    "color": "#d62728",
                    "yAxis": "right",
                    "dash": [5, 5],
                },
            ],
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
