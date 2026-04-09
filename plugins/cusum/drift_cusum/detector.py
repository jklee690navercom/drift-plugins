"""CUSUM drift detector v3.0.

1.D 책임 분리 (design_principles 6장):
- analyze() 3단계 패턴
- 누적 재실행 + replace_events=True
- baseline 고정 포인트 수
- bootstrap seed 고정 (결정성 보장)
"""

from datetime import timedelta

import numpy as np

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
        "k": 0.25,
        "h": "auto",
        "reset": True,
        "baseline_points": 50,
        "robust": True,
        "calibration_B": 500,
        "calibration_q": 0.995,
        "calibration_block": None,
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
        k = float(params["k"])
        h_param = params["h"]
        reset = bool(params["reset"])
        baseline_points = int(params["baseline_points"])
        robust = bool(params.get("robust", True))
        fir = params.get("fir", None)

        baseline_end = min(baseline_points, n)
        if baseline_end < 5 or (n - baseline_end) < 5:
            return []

        # ── 2단계: 계산 (락 밖) ──
        all_events, layer_rows = self._run_cusum(
            snapshot, stream, k, h_param, reset, baseline_end, robust, fir,
            params,
        )
        new_events = self._dedupe_events(all_events, previous_events)

        # ── 3단계: 커밋 (락 안, 짧음) ──
        self.cache.commit_analysis(
            layer_rows=layer_rows, events=all_events, replace_events=True,
        )
        return new_events

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        raise NotImplementedError("CusumDetector는 analyze()를 사용한다.")

    # ── 알고리즘 (락 밖에서 실행) ──

    def _run_cusum(self, snapshot, stream, k, h_param, reset, baseline_end,
                   robust, fir, params):
        timestamps = [row["timestamp"] for row in snapshot]
        series = np.array(
            [float(row["value"]) for row in snapshot], dtype=float,
        )
        n = len(series)

        # Baseline 통계량
        baseline = series[:baseline_end]
        if robust:
            mu0 = float(np.median(baseline))
            mad = float(np.median(np.abs(baseline - mu0)))
            sigma0 = 1.4826 * mad
        else:
            mu0 = float(np.mean(baseline))
            sigma0 = float(np.std(baseline, ddof=1))
        if sigma0 <= 0:
            sigma0 = 1e-8

        # 전체 표준화
        standardized = (series - mu0) / sigma0

        # Bootstrap 캘리브레이션 (seed 고정으로 결정성 보장)
        calibrated_h = None
        if h_param == "auto" or h_param is None:
            B = int(params.get("calibration_B", 500))
            q = float(params.get("calibration_q", 0.995))
            block = params.get("calibration_block", None)
            baseline_std = standardized[:baseline_end]
            cal_T = min(len(baseline_std), 2000)
            if len(baseline_std) > 2000:
                rng = np.random.RandomState(42)
                indices = rng.choice(len(baseline_std), 2000, replace=False)
                baseline_std = baseline_std[np.sort(indices)]
            h = self._calibrate_h(
                baseline_std, T=cal_T, B=B, k=k, q=q, block=block,
            )
            calibrated_h = float(h)
        else:
            h = float(h_param)

        # CUSUM traces
        s_pos_arr, s_neg_arr, alarm_mask = self._cusum_traces(
            standardized, k=k, h=h, reset=reset, fir=fir,
        )
        alarm_indices = list(np.where(alarm_mask == 1)[0])

        # layer_rows
        layer_rows = [
            {
                "timestamp": timestamps[i],
                "s_pos": float(s_pos_arr[i]),
                "s_neg": float(s_neg_arr[i]),
                "z": float(standardized[i]),
                "alarm": int(alarm_mask[i]),
                "threshold_h": float(h),
            }
            for i in range(n)
        ]

        # events
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            peak_idx = group_start + int(np.argmax(
                np.maximum(s_pos_arr[group_start:group_end + 1],
                           s_neg_arr[group_start:group_end + 1])
            ))
            peak_s_pos = float(s_pos_arr[peak_idx])
            peak_s_neg = float(s_neg_arr[peak_idx])
            score = max(peak_s_pos, peak_s_neg) / h if h > 0 else 0.0
            direction = "positive" if peak_s_pos >= peak_s_neg else "negative"

            events.append(DriftEvent(
                stream=stream,
                plugin="cusum",
                detected_at=timestamps[peak_idx],
                data_from=timestamps[group_start],
                data_to=timestamps[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=f"CUSUM {direction}: S+={peak_s_pos:.2f}, S-={peak_s_neg:.2f}",
                data_ids=[
                    f"{stream}:{idx}"
                    for idx in range(group_start, group_end + 1)
                ],
                data_count=int(group_end - group_start + 1),
                detail={
                    "algorithm": "cusum",
                    "s_pos": round(float(peak_s_pos), 4),
                    "s_neg": round(float(peak_s_neg), 4),
                    "threshold_h": float(h),
                    "k": float(k),
                    "alarm_direction": direction,
                    "mu0": round(float(mu0), 4),
                    "sigma0": round(float(sigma0), 4),
                    "baseline_points": int(baseline_end),
                    "robust": robust,
                    "calibrated_h": calibrated_h,
                    "h_source": "auto" if calibrated_h is not None else "manual",
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
                    "field": "s_pos",
                    "label": "S+",
                    "color": "#1f77b4",
                    "yAxis": "right",
                },
                {
                    "type": "line",
                    "field": "s_neg",
                    "label": "S-",
                    "color": "#ff7f0e",
                    "yAxis": "right",
                },
                {
                    "type": "line",
                    "field": "threshold_h",
                    "label": "h",
                    "color": "#d62728",
                    "yAxis": "right",
                    "dash": [5, 5],
                },
            ],
        }

    # ── Bootstrap / CUSUM 내부 함수 ──

    @staticmethod
    def _max_cusum(y, k=0.25):
        s_pos = s_neg = 0.0
        s_max = 0.0
        for v in y:
            s_pos = max(0.0, s_pos + v - k)
            s_neg = max(0.0, s_neg - v - k)
            s_max = max(s_max, s_pos, s_neg)
        return float(s_max)

    @staticmethod
    def _block_bootstrap(base, T, block, rng=None):
        if rng is None:
            rng = np.random.default_rng(42)
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
        # seed 고정: 같은 baseline → 같은 h (결정성 보장)
        rng = np.random.default_rng(42)
        sims = []
        for _ in range(B):
            if block is None:
                y = rng.choice(y0, size=T, replace=True)
            else:
                y = CusumDetector._block_bootstrap(
                    y0, T=T, block=block, rng=rng,
                )
            sims.append(CusumDetector._max_cusum(y, k))
        return float(np.quantile(np.asarray(sims), q))

    @staticmethod
    def _cusum_traces(y, k=0.25, h=5.0, reset=True, fir=None):
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

        return (np.array(s_pos_vals), np.array(s_neg_vals),
                np.array(alarms, dtype=int))

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
