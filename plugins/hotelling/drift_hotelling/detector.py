"""Hotelling T2 drift detector."""

import numpy as np
import pandas as pd

from framework.plugin.base import DriftDetector
from framework.events.schema import DriftEvent


class HotellingDetector(DriftDetector):
    """Hotelling T2 drift detector.

     Hotelling T2 제어 차트 기반 다변량 drift 탐지
    """

    # ╔══════════════════════════════════════════════════════╗
    # ║  STEP 1: 파라미터 정의                                ║
    # ║  이 알고리즘이 받을 파라미터를 선언하세요.               ║
    # ╚══════════════════════════════════════════════════════╝
    DEFAULT_PARAMS = {
        "threshold": 1.0,    # ← 파라미터 이름과 기본값을 수정하세요
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
