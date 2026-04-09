"""KS Test drift detector v3.0.

1.D 책임 분리 (design_principles 6장):
- analyze() 3단계 패턴, 1.B placeholder 제거
- 누적 재실행 + replace_events=True
- baseline 고정 포인트 수
- reference mutation은 순차 결정적 (baseline_points 고정이 전제)
- np.random 서브샘플링 제거 (결정성 보장)
"""

from datetime import timedelta

import numpy as np
from scipy import stats

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class KsTestDetector(DriftPlugin):
    """Kolmogorov-Smirnov 검정 기반 drift 탐지기.

    기준 구간(reference)과 슬라이딩 윈도우(test)의 분포 차이를
    KS 통계량으로 측정한다. 다중 검정 보정(BH/Bonferroni) 지원.
    drift 감지 시 reference를 새 데이터로 교체할 수 있다.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "window_size": 100,
        "alpha": 0.05,
        "baseline_points": 100,
        "correction": "bh",
        "update_reference": True,
        "remove_outliers": False,
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
        alpha = float(params["alpha"])
        baseline_points = int(params["baseline_points"])
        correction = str(params.get("correction", "bh"))
        update_ref = bool(params.get("update_reference", True))
        remove_outliers = bool(params.get("remove_outliers", False))

        ref_end = min(baseline_points, n)
        if ref_end < window_size or (n - ref_end) < window_size:
            return []

        # ── 2단계: 계산 (락 밖) ──
        all_events, layer_rows = self._run_ks_test(
            snapshot, stream, window_size, alpha, ref_end,
            correction, update_ref, remove_outliers,
        )
        new_events = self._dedupe_events(all_events, previous_events)

        # ── 3단계: 커밋 (락 안, 짧음) ──
        self.cache.commit_analysis(
            layer_rows=layer_rows, events=all_events, replace_events=True,
        )
        return new_events

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        raise NotImplementedError("KsTestDetector는 analyze()를 사용한다.")

    # ── 알고리즘 (락 밖에서 실행) ──

    def _run_ks_test(self, snapshot, stream, window_size, alpha, ref_end,
                     correction, update_ref, remove_outliers):
        timestamps = [row["timestamp"] for row in snapshot]
        series = np.array(
            [float(row["value"]) for row in snapshot], dtype=float,
        )
        n = len(series)

        # 전처리
        clean_series = series.copy()
        if remove_outliers:
            clean_series, _ = self._remove_outliers(series)

        # Reference (고정 baseline)
        reference = clean_series[:ref_end]

        # 슬라이딩 윈도우 KS 검정
        ks_stats = np.zeros(n)
        raw_p_values = np.ones(n)
        test_indices = []

        step = max(1, window_size // 5)

        consecutive_alarms = 0
        ref_update_threshold = 3

        for i in range(ref_end, n - window_size + 1, step):
            window = clean_series[i:i + window_size]
            stat, pval = stats.ks_2samp(reference, window)

            mid = i + window_size // 2
            ks_stats[mid] = stat
            raw_p_values[mid] = pval
            test_indices.append(mid)

            # Reference 갱신 (순차 결정적 — baseline_points 고정이 전제)
            if update_ref and pval < alpha:
                consecutive_alarms += 1
                if consecutive_alarms >= ref_update_threshold:
                    reference = window.copy()
                    consecutive_alarms = 0
            else:
                consecutive_alarms = 0

        # 다중 검정 보정
        corrected_p = np.ones(n)
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        if test_indices:
            test_p = np.array([raw_p_values[i] for i in test_indices])

            if correction == "bonferroni":
                adj_p = np.minimum(test_p * len(test_indices), 1.0)
            elif correction == "bh":
                adj_p = self._bh_correction(test_p)
            else:
                adj_p = test_p

            for idx, mid in enumerate(test_indices):
                corrected_p[mid] = adj_p[idx]
                if adj_p[idx] < alpha:
                    alarm_mask[mid] = 1
                    alarm_indices.append(mid)

        # layer_rows
        layer_rows = [
            {
                "timestamp": timestamps[i],
                "ks": float(ks_stats[i]),
                "raw_p": float(raw_p_values[i]),
                "corrected_p": float(corrected_p[i]),
                "alarm": int(alarm_mask[i]),
            }
            for i in range(n)
        ]

        # events
        events = []
        groups = self._group_consecutive(alarm_indices, gap=step * 3)
        for group_start, group_end in groups:
            peak_idx = group_start + int(
                np.argmin(corrected_p[group_start:group_end + 1]))
            peak_stat = float(ks_stats[peak_idx])
            peak_pval = float(corrected_p[peak_idx])
            raw_pval = float(raw_p_values[peak_idx])

            score = min(-np.log10(max(peak_pval, 1e-300)) / 10.0, 5.0)

            drift_type = self._classify_drift_type(
                corrected_p, test_indices, alpha)

            events.append(DriftEvent(
                stream=stream,
                plugin="ks_test",
                detected_at=timestamps[peak_idx],
                data_from=timestamps[group_start],
                data_to=timestamps[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=(
                    f"KS test: D={peak_stat:.4f}, p={peak_pval:.2e} "
                    f"(correction={correction}, type={drift_type})"
                ),
                data_ids=[
                    f"{stream}:{idx}"
                    for idx in range(group_start, group_end + 1)
                ],
                data_count=int(group_end - group_start + 1),
                detail={
                    "algorithm": "ks_test",
                    "d_statistic": round(float(peak_stat), 6),
                    "p_value": float(raw_pval),
                    "corrected_p_value": float(peak_pval),
                    "alpha": float(alpha),
                    "correction": correction,
                    "drift_type": drift_type,
                    "window_size": int(window_size),
                    "baseline_points": int(ref_end),
                    "n_tests": len(test_indices),
                    "alarm_count": int(group_end - group_start + 1),
                    "update_reference": update_ref,
                    "remove_outliers": remove_outliers,
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
                    "field": "ks",
                    "label": "KS statistic",
                    "color": "#1f77b4",
                    "yAxis": "right",
                },
                {
                    "type": "line",
                    "field": "corrected_p",
                    "label": "p-value",
                    "color": "#ff7f0e",
                    "yAxis": "right",
                },
            ],
        }

    # ── 내부 헬퍼 ──

    @staticmethod
    def _remove_outliers(series):
        q1, q3 = np.percentile(series, [25, 75])
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outlier_mask = (series < lower) | (series > upper)
        clean = series.copy()
        clean[outlier_mask] = np.nan
        nans = np.isnan(clean)
        if nans.any() and not nans.all():
            clean[nans] = np.interp(
                np.flatnonzero(nans),
                np.flatnonzero(~nans),
                clean[~nans],
            )
        return clean, outlier_mask

    @staticmethod
    def _bh_correction(p_values):
        n = len(p_values)
        sorted_idx = np.argsort(p_values)
        sorted_p = p_values[sorted_idx]

        adjusted = np.zeros(n)
        for i in range(n):
            adjusted[i] = sorted_p[i] * n / (i + 1)

        for i in range(n - 2, -1, -1):
            adjusted[i] = min(adjusted[i], adjusted[i + 1])

        adjusted = np.minimum(adjusted, 1.0)

        result = np.zeros(n)
        result[sorted_idx] = adjusted
        return result

    @staticmethod
    def _classify_drift_type(corrected_p, test_indices, alpha):
        if not test_indices:
            return "none"

        alarm_flags = [corrected_p[i] < alpha for i in test_indices]
        n_alarms = sum(alarm_flags)

        if n_alarms == 0:
            return "none"

        alarm_ratio = n_alarms / len(test_indices)

        first_alarm = next(i for i, f in enumerate(alarm_flags) if f)

        if alarm_ratio > 0.6:
            return "incremental"

        if first_alarm > 5:
            pre_p = [corrected_p[test_indices[i]]
                     for i in range(max(0, first_alarm - 10), first_alarm)]
            if len(pre_p) >= 3 and pre_p[-1] < pre_p[0] * 0.5:
                return "gradual"

        return "sudden"

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
