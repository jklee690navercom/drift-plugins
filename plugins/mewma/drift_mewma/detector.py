"""MEWMA drift detector — DriftPlugin 기반 운영 환경용."""

from datetime import timedelta

import numpy as np
import pandas as pd

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class MewmaDetector(DriftPlugin):
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
        "baseline_ratio": 0.5,
        "cooldown": 5,
        "two_sided": True,
    }

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        if data.empty:
            return []

        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]
        n = len(series)

        lam = float(params["lambda_"])
        L = float(params["L"])
        baseline_ratio = float(params["baseline_ratio"])
        cooldown = int(params.get("cooldown", 5))
        two_sided = bool(params.get("two_sided", True))

        # ── Baseline estimation ──
        baseline_end = int(n * baseline_ratio)
        if baseline_end < 10 or (n - baseline_end) < 10:
            return []

        baseline = series[:baseline_end]
        mu0 = float(np.mean(baseline))
        sigma0 = float(np.std(baseline, ddof=1))
        if sigma0 <= 0:
            sigma0 = 1e-8

        # ── EWMA calculation ──
        z = np.zeros(n)
        z[0] = mu0  # initialize to baseline mean
        for t in range(1, n):
            z[t] = lam * series[t] + (1 - lam) * z[t - 1]

        # ── Control Limits ──
        ewma_std = sigma0 * np.sqrt(lam / (2 - lam))
        ucl = mu0 + L * ewma_std
        lcl = mu0 - L * ewma_std

        # ── Alarm detection (after baseline, with cooldown) ──
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

        # ── Cache ──
        cache_rows = []
        for i in range(n):
            cache_rows.append({
                "timestamp": timestamps.iloc[i],
                "value": float(series[i]),
                "ewma": float(z[i]),
            })
        if self.cache is not None:
            self.cache.append_data(cache_rows)

        if not alarm_indices:
            return []

        # ── DriftEvent generation ──
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1]

            # Peak = point with max deviation from mean
            deviations = np.abs(z[group_start:group_end + 1] - mu0)
            peak_offset = int(np.argmax(deviations))
            peak_idx = group_start + peak_offset
            peak_z = float(z[peak_idx])
            peak_dev = abs(peak_z - mu0)
            score = peak_dev / (L * ewma_std) if ewma_std > 0 else 0
            direction = direction_arr[peak_idx] or ("upper" if peak_z > mu0 else "lower")

            events.append(DriftEvent(
                stream=stream,
                plugin="mewma",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"EWMA {direction}: z={peak_z:.4f}, UCL={ucl:.4f}, LCL={lcl:.4f}",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "mewma",
                    "ewma_value": round(peak_z, 4),
                    "ucl": round(ucl, 4),
                    "lcl": round(lcl, 4),
                    "mu0": round(mu0, 4),
                    "sigma0": round(sigma0, 4),
                    "lambda": lam,
                    "L": L,
                    "direction": direction,
                    "baseline_end": int(baseline_end),
                    "ewma_std": round(float(ewma_std), 4),
                    "alarm_count": int(group_end - group_start + 1),
                    "ewma_series": z.tolist(),
                    "alarm_mask": alarm_mask.tolist(),
                },
            ))

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
