"""Hotelling T2 drift detector."""

import numpy as np
import pandas as pd

from framework.plugin.base import DriftDetector
from framework.events.schema import DriftEvent


class HotellingDetector(DriftDetector):
    """Hotelling T2 drift detector.

    Hotelling T2 다변량 제어 차트 기반 drift 탐지
    """

    # ╔══════════════════════════════════════════════════════╗
    # ║  STEP 1: 파라미터 정의                                ║
    # ║  이 알고리즘이 받을 파라미터를 선언하세요.               ║
    # ╚══════════════════════════════════════════════════════╝
    DEFAULT_PARAMS = {
        "alpha": 0.01,           # 유의수준 (0.01 = 99% 신뢰구간)
        "window_size": 50,        # 슬라이딩 윈도우 크기
        "reference_ratio": 0.5,   # 전체 데이터 중 기준 구간 비율
    }

    def detect(self, data, data_ids, stream, params):
        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]

        # ╔══════════════════════════════════════════════════╗
        # ║  STEP 2: 알고리즘 구현                            ║
        # ║                                                  ║
        # ║  입력:                                           ║
        # ║    series  — numpy 배열 [0.91, 0.88, 0.73, ...]  ║
        # ║    params  — STEP 1에서 정의한 파라미터 dict        ║
        # ║                                                  ║
        # ║  출력 (아래 4개 변수에 결과를 채우세요):             ║
        # ║    alarm_indices — 이상 포인트의 인덱스 리스트       ║
        # ║    score   — 이상 강도 (0.0~, 1.0이면 임계)        ║
        # ║    message — 사람이 읽을 한 줄 요약                 ║
        # ║    detail  — 알고리즘 고유 결과값 dict              ║
        # ╚══════════════════════════════════════════════════╝

        # ▼▼▼ 여기에 알고리즘을 구현하세요 ▼▼▼

        alarm_indices = []
        score = 0.0
        message = ""
        detail = {}

        alpha = params["alpha"]
        window_size = int(params["window_size"])
        ref_ratio = params["reference_ratio"]

        # 기준 구간 분리
        ref_end = int(len(series) * ref_ratio)
        reference = series[:ref_end]
        ref_mean = np.mean(reference)
        ref_std = np.std(reference, ddof=1)
        if ref_std <= 0:
            ref_std = 1e-8

        # T2 통계량 계산
        from scipy.stats import chi2
        threshold = chi2.ppf(1 - alpha, df=1)

        t2_values = np.zeros(len(series))
        for i in range(ref_end, len(series)):
            z = (series[i] - ref_mean) / ref_std
            t2 = z ** 2
            t2_values[i] = t2
            if t2 > threshold:
                alarm_indices.append(i)

        if alarm_indices:
            peak_idx = alarm_indices[np.argmax(t2_values[alarm_indices])]
            score = float(t2_values[peak_idx] / threshold)
            message = f"Hotelling T2={t2_values[peak_idx]:.2f}, threshold={threshold:.2f}"
            detail = {
                "algorithm": "hotelling_t2",
                "threshold": round(threshold, 4),
                "alpha": alpha,
                "ref_mean": round(float(ref_mean), 4),
                "ref_std": round(float(ref_std), 4),
                "t2_series": t2_values.tolist(),
                "alarm_mask": [1 if i in alarm_indices else 0 for i in range(len(series))],
            }

        # ▲▲▲ 여기까지 구현하세요 ▲▲▲

        # ═══ 수정하지 마세요: DriftEvent 생성 ═══
        if not alarm_indices:
            return []

        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            events.append(DriftEvent(
                stream=stream,
                plugin="hotelling",
                detected_at=timestamps.iloc[group_end],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=message,
                data_ids=data_ids[group_start:group_end + 1],
                data_count=group_end - group_start + 1,
                detail=detail,
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
        if score >= 2.0: return "critical"
        if score >= 1.0: return "warning"
        return "normal"
