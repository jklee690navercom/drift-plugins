"""EWMA drift detector v3.0.

1.D 책임 분리 (design_principles 6장):
- analyze() 3단계 패턴, 1.B placeholder 제거
- 누적 재실행 + replace_events=True 로 cache 통째 교체
- baseline 고정 포인트 수
"""

from datetime import timedelta

import numpy as np

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class EwmaDetector(DriftPlugin):
    """EWMA 관리도 기반 drift 탐지기.

    EWMA 평활화 후 관리한계(UCL/LCL)를 이용해 drift를 판단한다.
    UCL = μ0 + L * σ0 * sqrt(λ/(2-λ))
    LCL = μ0 - L * σ0 * sqrt(λ/(2-λ))
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "lambda_": 0.2,
        "L": 3.0,
        "baseline_points": 50,
        "cooldown": 5,
        "two_sided": True,
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
        lam = float(params["lambda_"])
        L = float(params["L"])
        baseline_points = int(params["baseline_points"])
        cooldown = int(params.get("cooldown", 5))
        two_sided = bool(params.get("two_sided", True))

        baseline_end = min(baseline_points, n)
        if baseline_end < 10 or (n - baseline_end) < 10:
            return []

        # ── 2단계: 계산 (락 밖) ──
        all_events, layer_rows = self._run_ewma(
            snapshot, stream, lam, L, baseline_end, cooldown, two_sided,
        )
        new_events = self._dedupe_events(all_events, previous_events)

        # ── 3단계: 커밋 (락 안, 짧음) ──
        self.cache.commit_analysis(
            layer_rows=layer_rows, events=all_events, replace_events=True,
        )
        return new_events

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        raise NotImplementedError("EwmaDetector는 analyze()를 사용한다.")

    # ── 알고리즘 (락 밖에서 실행되는 순수 함수) ──

    def _run_ewma(self, snapshot, stream, lam, L, baseline_end,
                  cooldown, two_sided):
        timestamps = [row["timestamp"] for row in snapshot]
        series = np.array(
            [float(row["value"]) for row in snapshot], dtype=float,
        )
        n = len(series)

        # Baseline 통계량
        baseline = series[:baseline_end]
        mu0 = float(np.mean(baseline))
        sigma0 = float(np.std(baseline, ddof=1))
        if sigma0 <= 0:
            sigma0 = 1e-8

        # EWMA 계산
        z = np.zeros(n)
        z[0] = mu0
        for t in range(1, n):
            z[t] = lam * series[t] + (1 - lam) * z[t - 1]

        # 관리 한계
        ewma_std = sigma0 * np.sqrt(lam / (2 - lam))
        ucl = mu0 + L * ewma_std
        lcl = mu0 - L * ewma_std

        # Alarm (baseline 이후, cooldown 적용)
        alarm_mask = np.zeros(n, dtype=int)
        direction_arr = [""] * n
        last_alarm = -cooldown - 1

        for t in range(baseline_end, n):
            if t - last_alarm <= cooldown:
                continue
            if z[t] > ucl:
                alarm_mask[t] = 1
                direction_arr[t] = "upper"
                last_alarm = t
            elif two_sided and z[t] < lcl:
                alarm_mask[t] = 1
                direction_arr[t] = "lower"
                last_alarm = t

        alarm_indices = list(np.where(alarm_mask == 1)[0])

        # layer_rows
        layer_rows = [
            {
                "timestamp": timestamps[i],
                "ewma": float(z[i]),
                "ucl": float(ucl),
                "lcl": float(lcl),
                "mu0": float(mu0),
                "alarm": int(alarm_mask[i]),
            }
            for i in range(n)
        ]

        # events
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            deviations = np.abs(z[group_start:group_end + 1] - mu0)
            peak_offset = int(np.argmax(deviations))
            peak_idx = group_start + peak_offset
            peak_z = float(z[peak_idx])
            peak_dev = abs(peak_z - mu0)
            score = peak_dev / (L * ewma_std) if ewma_std > 0 else 0.0
            direction = (
                direction_arr[peak_idx]
                or ("upper" if peak_z > mu0 else "lower")
            )

            events.append(DriftEvent(
                stream=stream,
                plugin="ewma",
                detected_at=timestamps[peak_idx],
                data_from=timestamps[group_start],
                data_to=timestamps[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=(
                    f"EWMA {direction}: z={peak_z:.4f}, "
                    f"UCL={ucl:.4f}, LCL={lcl:.4f}"
                ),
                data_ids=[
                    f"{stream}:{idx}"
                    for idx in range(group_start, group_end + 1)
                ],
                data_count=int(group_end - group_start + 1),
                detail={
                    "algorithm": "ewma",
                    "ewma_value": round(float(peak_z), 4),
                    "ucl": round(float(ucl), 4),
                    "lcl": round(float(lcl), 4),
                    "mu0": round(float(mu0), 4),
                    "sigma0": round(float(sigma0), 4),
                    "lambda": float(lam),
                    "L": float(L),
                    "direction": direction,
                    "baseline_points": int(baseline_end),
                    "ewma_std": round(float(ewma_std), 4),
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
                    "field": "ewma",
                    "label": "EWMA",
                    "color": "#1f77b4",
                },
                {
                    "type": "line",
                    "field": "ucl",
                    "label": "UCL",
                    "color": "#d62728",
                    "dash": [5, 5],
                },
                {
                    "type": "line",
                    "field": "lcl",
                    "label": "LCL",
                    "color": "#d62728",
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
