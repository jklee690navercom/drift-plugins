"""X-bar/R Chart drift detector — 서브그룹 평균(X-bar)과 범위(R) 제어 차트 기반 이상 탐지."""

import numpy as np
import pandas as pd

from framework.plugin.base import DriftDetector
from framework.events.schema import DriftEvent


class XbarRChartDetector(DriftDetector):
    """X-bar/R Chart 기반 drift 탐지기.

    데이터를 서브그룹으로 묶어 각 그룹의 평균(X-bar)과 범위(R)를
    모니터링하여 평균 이동과 산포 변화를 감지한다.
    """

    DEFAULT_PARAMS = {
        "subgroup_size": 5,
        "reference_ratio": 0.5,
    }

    def detect(self, data, data_ids, stream, params):
        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]
        subgroup_size = int(params["subgroup_size"])
        reference_ratio = float(params["reference_ratio"])

        # ── 서브그룹 생성 ──
        n = len(series)
        n_groups = n // subgroup_size
        trimmed = series[:n_groups * subgroup_size]
        groups = trimmed.reshape(n_groups, subgroup_size)

        # 각 서브그룹의 평균과 범위
        xbar_values = groups.mean(axis=1)
        r_values = groups.max(axis=1) - groups.min(axis=1)

        # 각 서브그룹의 대표 timestamp (그룹 마지막 시점)
        group_timestamps = [timestamps.iloc[min((i + 1) * subgroup_size - 1, n - 1)] for i in range(n_groups)]

        # ── 기준 구간 통계량 ──
        ref_size = max(2, int(n_groups * reference_ratio))
        ref_xbar = xbar_values[:ref_size]
        ref_r = r_values[:ref_size]

        x_double_bar = float(np.mean(ref_xbar))  # X-double-bar
        r_bar = float(np.mean(ref_r))

        # ── 제어 한계 (n=5 기준 상수) ──
        A2 = 0.577
        D4 = 2.114
        D3 = 0.0

        ucl_xbar = x_double_bar + A2 * r_bar
        lcl_xbar = x_double_bar - A2 * r_bar
        cl_xbar = x_double_bar

        ucl_r = D4 * r_bar
        lcl_r = D3 * r_bar
        cl_r = r_bar

        # ── 알람 판정 ──
        alarm_xbar = (xbar_values > ucl_xbar) | (xbar_values < lcl_xbar)
        alarm_r = (r_values > ucl_r) | (r_values < lcl_r)
        alarm_mask_xbar = alarm_xbar.astype(int)
        alarm_mask_r = alarm_r.astype(int)
        alarm_combined = (alarm_xbar | alarm_r).astype(int)

        alarm_indices = list(np.where(alarm_combined == 1)[0])

        if not alarm_indices:
            return []

        # ── DriftEvent 생성 ──
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            # 데이터 인덱스로 변환
            data_start = group_start * subgroup_size
            data_end = min((group_end + 1) * subgroup_size - 1, n - 1)
            group_ids = data_ids[data_start:data_end + 1]

            # 가장 크게 벗어난 서브그룹 찾기
            deviations = np.abs(xbar_values[group_start:group_end + 1] - cl_xbar)
            peak_group = group_start + int(np.argmax(deviations))
            score = float(deviations.max()) / (A2 * r_bar) if r_bar > 0 else 0.0

            events.append(DriftEvent(
                stream=stream,
                plugin="xbar_r_chart",
                detected_at=group_timestamps[peak_group],
                data_from=group_timestamps[group_start],
                data_to=group_timestamps[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"X-bar/R Chart alarm: X-bar={xbar_values[peak_group]:.4f}, UCL={ucl_xbar:.4f}, LCL={lcl_xbar:.4f}",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "xbar_r_chart",
                    "xbar_values": xbar_values.tolist(),
                    "r_values": r_values.tolist(),
                    "ucl_xbar": ucl_xbar,
                    "lcl_xbar": lcl_xbar,
                    "cl_xbar": cl_xbar,
                    "ucl_r": ucl_r,
                    "lcl_r": lcl_r,
                    "cl_r": cl_r,
                    "alarm_mask_xbar": alarm_mask_xbar.tolist(),
                    "alarm_mask_r": alarm_mask_r.tolist(),
                    "subgroup_size": subgroup_size,
                    "x_double_bar": x_double_bar,
                    "r_bar": r_bar,
                },
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
        if score >= 2.0:
            return "critical"
        if score >= 1.0:
            return "warning"
        return "normal"
