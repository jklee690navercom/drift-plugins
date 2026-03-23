"""OCDD drift detector — 기준 분포 통계량과 슬라이딩 윈도우를 비교하여 drift를 탐지."""

import numpy as np
import pandas as pd

from framework.plugin.base import DriftDetector
from framework.events.schema import DriftEvent


class OcddDetector(DriftDetector):
    """One-Class Drift Detector.

    기준 구간(reference)의 평균/표준편차와 슬라이딩 윈도우(test)의
    평균/표준편차를 비교하여 z-score가 임계값을 초과하면 drift로 판단.
    평균 변화와 표준편차 변화를 모두 감지하며, 둘 다 임계값을 넘으면 alarm.
    Score = max(z_mean, z_std).
    """

    DEFAULT_PARAMS = {
        "window_size": 50,
        "reference_ratio": 0.5,
        "z_threshold": 3.0,
    }

    def detect(self, data, data_ids, stream, params):
        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]
        n = len(series)

        window_size = int(params["window_size"])
        ref_ratio = float(params["reference_ratio"])
        z_threshold = float(params["z_threshold"])

        # ── 기준 구간 ──
        ref_end = int(n * ref_ratio)
        if ref_end < window_size or (n - ref_end) < window_size:
            return []

        reference = series[:ref_end]
        ref_mean = float(np.mean(reference))
        ref_std = float(np.std(reference))
        if ref_std <= 0:
            ref_std = 1e-12

        # 기준 구간에서 윈도우 평균/표준편차의 분포 추정
        ref_win_means = []
        ref_win_stds = []
        for i in range(0, ref_end - window_size + 1, max(1, window_size // 5)):
            w = reference[i:i + window_size]
            ref_win_means.append(np.mean(w))
            ref_win_stds.append(np.std(w))
        ref_win_mean_mu = float(np.mean(ref_win_means))
        ref_win_mean_sigma = float(np.std(ref_win_means))
        ref_win_std_mu = float(np.mean(ref_win_stds))
        ref_win_std_sigma = float(np.std(ref_win_stds))
        if ref_win_mean_sigma <= 0:
            ref_win_mean_sigma = 1e-12
        if ref_win_std_sigma <= 0:
            ref_win_std_sigma = 1e-12

        # ── 슬라이딩 윈도우 Z-score ──
        z_mean_series = np.zeros(n)
        z_std_series = np.zeros(n)
        z_max_series = np.zeros(n)
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        for i in range(ref_end, n - window_size + 1):
            window = series[i:i + window_size]
            win_mean = float(np.mean(window))
            win_std = float(np.std(window))

            z_mean = abs(win_mean - ref_win_mean_mu) / ref_win_mean_sigma
            z_std = abs(win_std - ref_win_std_mu) / ref_win_std_sigma

            mid = i + window_size // 2
            z_mean_series[mid] = z_mean
            z_std_series[mid] = z_std
            z_max_series[mid] = max(z_mean, z_std)

            # 둘 다 임계값 초과 시 alarm
            if z_mean > z_threshold and z_std > z_threshold:
                alarm_mask[mid] = 1
                alarm_indices.append(mid)

        if not alarm_indices:
            return []

        # ── DriftEvent 생성 ──
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1]

            peak_idx = group_start + int(np.argmax(z_max_series[group_start:group_end + 1]))
            peak_z_mean = float(z_mean_series[peak_idx])
            peak_z_std = float(z_std_series[peak_idx])
            score = max(peak_z_mean, peak_z_std) / z_threshold

            events.append(DriftEvent(
                stream=stream,
                plugin="ocdd",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"OCDD alarm: z_mean={peak_z_mean:.2f}, z_std={peak_z_std:.2f}, threshold={z_threshold:.1f}",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "ocdd",
                    "z_mean_peak": round(peak_z_mean, 4),
                    "z_std_peak": round(peak_z_std, 4),
                    "z_threshold": z_threshold,
                    "window_size": window_size,
                    "reference_size": ref_end,
                    "ref_mean": round(ref_mean, 4),
                    "ref_std": round(ref_std, 4),
                    "alarm_count": group_end - group_start + 1,
                    "z_mean_series": z_mean_series.tolist(),
                    "z_std_series": z_std_series.tolist(),
                    "z_max_series": z_max_series.tolist(),
                    "alarm_mask": alarm_mask.tolist(),
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
