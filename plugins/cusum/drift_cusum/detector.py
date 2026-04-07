"""CUSUM drift detector — DriftPlugin 기반 운영 환경용. v2.1"""

from datetime import timedelta

import numpy as np
import pandas as pd

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class CusumDetector(DriftPlugin):
    """누적합(CUSUM) 기반 drift 탐지기.

    양방향 CUSUM으로 평균의 상승/하락을 동시에 감지한다.
    Baseline 구간에서 μ0, σ0를 계산한 후 모니터링 구간에 CUSUM을 적용한다.
    robust(median/MAD) 또는 standard(mean/std) 표준화를 지원한다.
    FIR(Fast Initial Response) 옵션으로 초기 감지 속도를 향상할 수 있다.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "k": 0.25,              # slack value (표준화된 단위)
        "h": "auto",            # threshold: "auto"이면 bootstrap 캘리브레이션
        "reset": True,          # alarm 후 CUSUM 리셋 여부
        "baseline_ratio": 0.5,  # baseline 구간 비율
        "robust": True,         # True: median/MAD, False: mean/std
        "calibration_B": 500,   # bootstrap 반복 횟수
        "calibration_q": 0.995, # bootstrap 분위수
        "calibration_block": None,  # 블록 부트스트랩 블록 크기 (None=iid)
    }

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        if data.empty:
            return []

        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]

        # ── Baseline 분리 ──
        baseline_ratio = params.get("baseline_ratio", 0.5)
        baseline_end = max(1, int(len(series) * baseline_ratio))
        baseline = series[:baseline_end]
        robust = params.get("robust", True)

        # ── 표준화 파라미터 계산 (baseline 구간) ──
        if robust:
            mu0 = float(np.median(baseline))
            mad = float(np.median(np.abs(baseline - mu0)))
            sigma0 = 1.4826 * mad
        else:
            mu0 = float(np.mean(baseline))
            sigma0 = float(np.std(baseline, ddof=1))

        if sigma0 <= 0:
            sigma0 = 1e-8

        # ── 전체 시계열 표준화 ──
        standardized = (series - mu0) / sigma0

        # ── CUSUM 계산 ──
        k = params["k"]
        h_param = params["h"]
        reset = params["reset"]
        fir = params.get("fir", None)

        # ── Bootstrap 캘리브레이션 (h="auto" 또는 None) ──
        calibrated_h = None
        if h_param == "auto" or h_param is None:
            B = params.get("calibration_B", 500)
            q = params.get("calibration_q", 0.995)
            block = params.get("calibration_block", None)
            baseline_std = standardized[:baseline_end]
            # T는 baseline 길이로 제한 (전체 길이로 하면 느림)
            cal_T = min(len(baseline_std), 2000)
            # baseline이 너무 크면 서브샘플링
            if len(baseline_std) > 2000:
                indices = np.random.choice(len(baseline_std), 2000, replace=False)
                baseline_std = baseline_std[np.sort(indices)]
            h = self._calibrate_h(
                baseline_std, T=cal_T, B=B, k=k, q=q, block=block,
            )
            calibrated_h = float(h)
        else:
            h = float(h_param)

        s_pos_arr, s_neg_arr, alarm_mask = self._cusum_traces(
            standardized, k=k, h=h, reset=reset, fir=fir,
        )

        alarm_indices = list(np.where(alarm_mask == 1)[0])

        # ── Cache에 데이터 기록 (벡터화) ──
        # 전문가 차트가 cache.data에서 직접 series를 읽을 수 있도록
        # row마다 s_pos, s_neg, z, alarm을 함께 적재한다.
        if self.cache is not None:
            cache_rows = [
                {
                    "timestamp": timestamps.iloc[i],
                    "value": float(series[i]),
                    "s_pos": float(s_pos_arr[i]),
                    "s_neg": float(s_neg_arr[i]),
                    "z": float(standardized[i]),
                    "alarm": int(alarm_mask[i]),
                    "threshold_h": float(h),
                }
                for i in range(len(series))
            ]
            self.cache.append_data(cache_rows)

        # ── DriftEvent 생성 ──
        if not alarm_indices:
            return []

        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1] if data_ids else []

            peak_idx = group_start + int(np.argmax(
                np.maximum(s_pos_arr[group_start:group_end + 1],
                           s_neg_arr[group_start:group_end + 1])
            ))
            peak_s_pos = float(s_pos_arr[peak_idx])
            peak_s_neg = float(s_neg_arr[peak_idx])
            score = max(peak_s_pos, peak_s_neg) / h
            direction = "positive" if peak_s_pos >= peak_s_neg else "negative"

            ev = DriftEvent(
                stream=stream,
                plugin="cusum",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"CUSUM {direction}: S+={peak_s_pos:.2f}, S-={peak_s_neg:.2f}",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "cusum",
                    "s_pos": round(peak_s_pos, 4),
                    "s_neg": round(peak_s_neg, 4),
                    "threshold_h": float(h),
                    "k": float(k),
                    "alarm_direction": direction,
                    "mu0": round(mu0, 4),
                    "sigma0": round(sigma0, 4),
                    "baseline_end": int(baseline_end),
                    "robust": robust,
                    "calibrated_h": calibrated_h,
                    "h_source": "auto" if calibrated_h is not None else "manual",
                    "s_pos_series": [round(float(v), 4) for v in s_pos_arr],
                    "s_neg_series": [round(float(v), 4) for v in s_neg_arr],
                    "z_series": [round(float(v), 4) for v in standardized],
                    "alarm_mask": alarm_mask.tolist(),
                    # 하위 호환: 이전 코드에서 사용하던 키
                    "median": round(mu0, 4),
                    "sigma": round(sigma0, 4),
                },
            )
            events.append(ev)

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

    # ── Bootstrap Threshold Calibration ──────────────────────────

    @staticmethod
    def _max_cusum(y, k=0.25):
        """전체 경로의 최대 CUSUM값 계산 (캘리브레이션용)."""
        s_pos = s_neg = 0.0
        s_max = 0.0
        for v in y:
            s_pos = max(0.0, s_pos + v - k)
            s_neg = max(0.0, s_neg - v - k)
            s_max = max(s_max, s_pos, s_neg)
        return float(s_max)

    @staticmethod
    def _block_bootstrap(base, T, block, rng=None):
        """블록 부트스트랩 — 자기상관 데이터용."""
        if rng is None:
            rng = np.random.default_rng()
        n = len(base)
        blocks = []
        start_max = max(1, n - block + 1)
        while sum(len(b) for b in blocks) < T:
            start = int(rng.integers(0, start_max))
            b = base[start:start + block]
            blocks.append(b)
        return np.concatenate(blocks)[:T]

    @staticmethod
    def _calibrate_h(y0, T, B=500, k=0.25, q=0.995, block=None):
        """Bootstrap 캘리브레이션으로 임계값 h를 자동 결정한다.

        baseline 데이터(y0)로 B번 시뮬레이션하여 q-분위수를 h로 설정.
        """
        rng = np.random.default_rng()
        sims = []
        for _ in range(B):
            if block is None:
                y = rng.choice(y0, size=T, replace=True)
            else:
                y = CusumDetector._block_bootstrap(y0, T=T, block=block, rng=rng)
            sims.append(CusumDetector._max_cusum(y, k))
        return float(np.quantile(np.asarray(sims), q))

    # ── CUSUM Traces ──────────────────────────────────────────

    @staticmethod
    def _cusum_traces(y, k=0.25, h=5.0, reset=True, fir=None):
        """양방향 CUSUM 통계량 계산.

        Parameters
        ----------
        y : array-like
            표준화된 시계열
        k : float
            slack value
        h : float
            threshold
        reset : bool
            alarm 후 리셋 여부
        fir : float or None
            Fast Initial Response. 설정 시 S+, S-를 fir*h 로 초기화.
        """
        s_pos_vals = []
        s_neg_vals = []
        alarms = []

        if fir is not None:
            s_pos = float(fir * h)
            s_neg = float(fir * h)
        else:
            s_pos = 0.0
            s_neg = 0.0

        for v in y:
            s_pos = max(0.0, s_pos + v - k)
            s_neg = max(0.0, s_neg - v - k)
            alarm = int(s_pos > h or s_neg > h)
            s_pos_vals.append(s_pos)
            s_neg_vals.append(s_neg)
            alarms.append(alarm)
            if alarm and reset:
                if fir is not None:
                    s_pos = float(fir * h)
                    s_neg = float(fir * h)
                else:
                    s_pos = 0.0
                    s_neg = 0.0
        return np.array(s_pos_vals), np.array(s_neg_vals), np.array(alarms, dtype=int)

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
