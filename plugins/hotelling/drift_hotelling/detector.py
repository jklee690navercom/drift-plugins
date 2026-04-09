"""Hotelling T2 drift detector — DriftPlugin 기반 운영 환경용.

v3.0 (1.D 책임 분리, design_principles 6장):
- analyze() 3단계 패턴: append_and_snapshot → _run_hotelling → commit_analysis
- 1.B placeholder 제거 (raw 차트 표시는 cache 누적으로 자동 처리)
- baseline은 고정 포인트 수(`baseline_points`) — cycle마다 흔들리지 않음
"""

from datetime import timedelta

import numpy as np

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class HotellingDetector(DriftPlugin):
    """Hotelling T2 drift detector.

    Hotelling T2 다변량 제어 차트 기반 drift 탐지.
    - Shrinkage 정규화로 수치 안정성 확보
    - Chi-squared 분포 기반 임계값 (univariate: df=1)
    - Baseline 분리로 기준 분포 설정
    - 슬라이딩 윈도우 T² 계산
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "alpha": 0.05,
        "window_size": 50,
        # baseline은 고정 포인트 수. 1.D 누적 재실행 패턴에서 ratio를 쓰면
        # cycle마다 baseline 위치가 이동해 같은 데이터에 대해 다른 결과가 나온다.
        "baseline_points": 50,
        "shrinkage": 0.01,
    }

    # ── 1.D 새 진입점 ──

    def analyze(self, new_data, data_ids, stream, params,
                calculated_until=None, previous_events=None):
        if new_data.empty or self.cache is None:
            return []

        # ── 1단계: 누적 + 스냅샷 ──
        snapshot = self.cache.append_and_snapshot(
            new_data.to_dict("records")
        )
        n = len(snapshot)

        params = {**self.DEFAULT_PARAMS, **params}
        alpha = float(params["alpha"])
        window_size = int(params["window_size"])
        baseline_points = int(params["baseline_points"])
        shrinkage = float(params["shrinkage"])

        baseline_end = min(baseline_points, n)
        if baseline_end < 2 or (n - baseline_end) < window_size:
            return []

        # ── 2단계: 계산 (락 밖) ──
        all_events, layer_rows = self._run_hotelling(
            snapshot, stream, alpha, window_size, baseline_end, shrinkage,
        )
        # 누적 재실행 패턴 — 그룹화/peak가 snapshot 길이에 의존하므로 매 cycle
        # 전체 재계산 결과로 cache를 교체한다. dedup 결과만 호출자에게 반환한다.
        new_events = self._dedupe_events(all_events, previous_events)

        # ── 3단계: 커밋 ──
        self.cache.commit_analysis(
            layer_rows=layer_rows, events=all_events, replace_events=True,
        )
        return new_events

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        """Legacy 진입점 — analyze()로 이전됨. 호출되면 명시적으로 실패한다."""
        raise NotImplementedError(
            "HotellingDetector는 analyze()를 사용한다."
        )

    # ── 알고리즘 (락 밖에서 실행) ──

    def _run_hotelling(self, snapshot, stream, alpha, window_size,
                       baseline_end, shrinkage):
        from scipy.stats import chi2

        timestamps = [row["timestamp"] for row in snapshot]
        series = np.array(
            [float(row["value"]) for row in snapshot], dtype=float,
        )
        n = len(series)

        baseline = series[:baseline_end]
        ref_mean = float(np.mean(baseline))
        ref_var = float(np.var(baseline, ddof=1))

        # Shrinkage 정규화: σ²_reg = (1-s)*σ² + s
        reg_var = (1 - shrinkage) * ref_var + shrinkage
        if reg_var <= 0:
            reg_var = 1e-8

        # Chi-squared 임계값 (univariate: p=1)
        threshold = float(chi2.ppf(1 - alpha, df=1))

        # 슬라이딩 윈도우 T²
        t2_values = np.zeros(n)
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        for i in range(baseline_end, n - window_size + 1):
            window = series[i:i + window_size]
            window_mean = float(np.mean(window))
            diff = window_mean - ref_mean
            t2 = float(window_size * (diff ** 2) / reg_var)
            mid = i + window_size // 2
            t2_values[mid] = t2
            if t2 > threshold:
                alarm_mask[mid] = 1
                alarm_indices.append(mid)

        # layer_rows
        layer_rows = [
            {
                "timestamp": timestamps[i],
                "t2": float(t2_values[i]),
                "alarm": int(alarm_mask[i]),
                "threshold": float(threshold),
            }
            for i in range(n)
        ]

        events = []
        if alarm_indices:
            for group_start, group_end in self._group_consecutive(alarm_indices):
                # group 안에서 peak 찾기
                peak_idx = max(
                    range(group_start, group_end + 1),
                    key=lambda k: t2_values[k] if alarm_mask[k] else -1.0,
                )
                peak_t2 = float(t2_values[peak_idx])
                score = float(peak_t2 / threshold) if threshold > 0 else 0.0

                events.append(DriftEvent(
                    stream=stream,
                    plugin="hotelling",
                    detected_at=timestamps[peak_idx],
                    data_from=timestamps[group_start],
                    data_to=timestamps[group_end],
                    severity=self._score_to_severity(score),
                    detected=True,
                    score=float(round(score, 4)),
                    message=(
                        f"Hotelling T²={peak_t2:.2f}, "
                        f"threshold={threshold:.2f} (chi2, alpha={alpha}), "
                        f"shrinkage={shrinkage}"
                    ),
                    data_ids=[
                        f"{stream}:{idx}"
                        for idx in range(group_start, group_end + 1)
                    ],
                    data_count=int(group_end - group_start + 1),
                    detail={
                        "algorithm": "hotelling_t2",
                        "threshold": float(round(threshold, 4)),
                        "alpha": float(alpha),
                        "window_size": int(window_size),
                        "baseline_points": int(baseline_end),
                        "shrinkage": float(shrinkage),
                        "ref_mean": float(round(ref_mean, 4)),
                        "ref_var": float(round(ref_var, 6)),
                        "reg_var": float(round(reg_var, 6)),
                        "peak_t2": float(round(peak_t2, 4)),
                    },
                ))

        return events, layer_rows

    @staticmethod
    def _dedupe_events(all_events, previous_events):
        """detected_at 기준으로 중복 제거 (DriftEvent.to_dict는 ' ', isoformat은 'T')."""
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

        return [ev for ev in all_events if to_key(ev.detected_at) not in existing]

    def get_chart_config(self):
        return {
            "mainLabel": "Value",
            "yLabel": "Value",
            "layers": [
                {
                    "type": "line",
                    "field": "t2",
                    "label": "T²",
                    "color": "#1f77b4",
                    "yAxis": "right",
                },
                {
                    "type": "line",
                    "field": "threshold",
                    "label": "threshold",
                    "color": "#d62728",
                    "yAxis": "right",
                },
            ],
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
