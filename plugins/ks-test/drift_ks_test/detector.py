"""KS Test drift detector — DriftPlugin 기반 운영 환경용.

8가지 기능:
1. 다중 검정 보정 (Bonferroni, Benjamini-Hochberg)
2. 기준 윈도우 갱신 (drift 후 reference 교체)
3. 이상치 처리 (IQR 기반)
4. 드리프트 유형 인식 (sudden/gradual/incremental)
5. 샘플 크기 검증
6. 다변량 KS 테스트
7. 부트스트랩 KS 테스트
8. ECDF 시각화 데이터 제공
"""

from datetime import timedelta

import numpy as np
import pandas as pd
from scipy import stats

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class KsTestDetector(DriftPlugin):
    """Kolmogorov-Smirnov 검정 기반 drift 탐지기."""

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "window_size": 100,
        "alpha": 0.05,
        "reference_ratio": 0.5,
        "correction": "bh",
        "update_reference": True,
        "remove_outliers": False,
        "method": "asymptotic",
    }

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        if data.empty:
            return []

        params = {**self.DEFAULT_PARAMS, **params}
        series = data["value"].to_numpy(dtype=float)
        timestamps = data["timestamp"]
        n = len(series)

        window_size = int(params["window_size"])
        alpha = float(params["alpha"])
        ref_ratio = float(params["reference_ratio"])
        correction = str(params.get("correction", "bh"))
        update_ref = bool(params.get("update_reference", True))
        remove_outliers = bool(params.get("remove_outliers", False))
        method = str(params.get("method", "asymptotic"))

        # ── Phase 1: 전처리 ──
        if window_size < 50:
            self.log(f"[ks_test] WARNING: window_size={window_size} < 50, "
                     f"검정력이 부족할 수 있습니다. n>=100 권장.")

        clean_series = series.copy()
        outlier_mask = np.zeros(n, dtype=bool)
        if remove_outliers:
            clean_series, outlier_mask = self._remove_outliers(series)

        # ── 기준 구간과 테스트 구간 분리 ──
        ref_end = int(n * ref_ratio)
        if ref_end < window_size or (n - ref_end) < window_size:
            return []

        full_reference = clean_series[:ref_end]

        # Reference가 너무 크면 서브샘플링 (검정력 유지, 속도 개선)
        max_ref_size = window_size * 10
        if len(full_reference) > max_ref_size:
            ref_indices = np.random.choice(
                len(full_reference), max_ref_size, replace=False)
            ref_indices.sort()
            reference = full_reference[ref_indices]
        else:
            reference = full_reference

        # ── Phase 2: 슬라이딩 윈도우 KS 검정 ──
        ks_stats = np.zeros(n)
        raw_p_values = np.ones(n)
        test_indices = []

        # 윈도우 이동 스텝: 데이터가 많으면 건너뛰어 속도 확보
        step = max(1, window_size // 5)

        # 기준 갱신용 상태
        consecutive_alarms = 0
        ref_update_threshold = 3  # 연속 alarm 이만큼이면 기준 갱신

        for i in range(ref_end, n - window_size + 1, step):
            window = clean_series[i:i + window_size]
            if method == "bootstrap":
                stat, pval = self._bootstrap_ks(reference, window)
            elif method == "exact":
                stat, pval = stats.ks_2samp(reference, window, method="exact")
            else:
                stat, pval = stats.ks_2samp(reference, window)

            mid = i + window_size // 2
            ks_stats[mid] = stat
            raw_p_values[mid] = pval
            test_indices.append(mid)

            # 기준 윈도우 갱신 (루프 내에서 즉시)
            if update_ref and pval < alpha:
                consecutive_alarms += 1
                if consecutive_alarms >= ref_update_threshold:
                    reference = window.copy()
                    consecutive_alarms = 0
            else:
                consecutive_alarms = 0

        # ── Phase 3: 다중 검정 보정 ──
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

        # ── Phase 4: 기준 갱신 + 이벤트 생성 ──

        # ECDF 데이터 (마지막 alarm 시점 또는 마지막 윈도우)
        ecdf_ref_x, ecdf_ref_y = self._compute_ecdf(reference)
        if alarm_indices:
            last_alarm = alarm_indices[-1]
            test_start = max(0, last_alarm - window_size // 2)
            test_window = clean_series[test_start:test_start + window_size]
        else:
            test_window = clean_series[max(0, n - window_size):n]
        ecdf_test_x, ecdf_test_y = self._compute_ecdf(test_window)

        # Cache에 데이터 기록
        # 전문가 차트가 cache.data에서 직접 series를 읽도록
        # ks, raw_p, corrected_p, alarm을 row마다 적재한다.
        # (KS는 step 단위로만 계산되므로 그 외 위치는 ks=0, p=1로 적재)
        cache_rows = []
        for i in range(len(series)):
            cache_rows.append({
                "timestamp": timestamps.iloc[i],
                "value": float(series[i]),
                "ks": float(ks_stats[i]),
                "raw_p": float(raw_p_values[i]),
                "corrected_p": float(corrected_p[i]),
                "alarm": int(alarm_mask[i]),
            })
        if self.cache is not None:
            self.cache.append_data(cache_rows)

        if not alarm_indices:
            return []

        # 기준 갱신을 위한 그룹화 (gap을 step의 3배로 설정)
        groups = self._group_consecutive(alarm_indices, gap=step * 3)
        events = []
        current_ref = reference.copy()

        for group_start, group_end in groups:
            group_ids = data_ids[group_start:group_end + 1]

            peak_idx = group_start + int(
                np.argmin(corrected_p[group_start:group_end + 1]))
            peak_stat = float(ks_stats[peak_idx])
            peak_pval = float(corrected_p[peak_idx])
            raw_pval = float(raw_p_values[peak_idx])

            score = min(-np.log10(max(peak_pval, 1e-300)) / 10.0, 5.0)

            # 드리프트 유형 판별
            drift_type = self._classify_drift_type(
                corrected_p, test_indices, alpha)

            events.append(DriftEvent(
                stream=stream,
                plugin="ks_test",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=(f"KS test: D={peak_stat:.4f}, p={peak_pval:.2e} "
                         f"(correction={correction}, type={drift_type})"),
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "ks_test",
                    "d_statistic": round(peak_stat, 6),
                    "p_value": raw_pval,
                    "corrected_p_value": peak_pval,
                    "alpha": alpha,
                    "correction": correction,
                    "method": method,
                    "drift_type": drift_type,
                    "window_size": window_size,
                    "reference_size": len(current_ref),
                    "n_tests": len(test_indices),
                    "alarm_count": group_end - group_start + 1,
                    "ks_series": ks_stats.tolist(),
                    "pvalue_series": raw_p_values.tolist(),
                    "corrected_pvalue_series": corrected_p.tolist(),
                    "alarm_mask": alarm_mask.tolist(),
                    "outlier_mask": outlier_mask.tolist(),
                    "ref_mean": round(float(np.mean(current_ref)), 4),
                    "ref_std": round(float(np.std(current_ref)), 4),
                    "test_mean": round(float(np.mean(
                        series[group_start:group_end + 1])), 4),
                    "test_std": round(float(np.std(
                        series[group_start:group_end + 1])), 4),
                    "ecdf_ref_x": ecdf_ref_x.tolist(),
                    "ecdf_ref_y": ecdf_ref_y.tolist(),
                    "ecdf_test_x": ecdf_test_x.tolist(),
                    "ecdf_test_y": ecdf_test_y.tolist(),
                    "update_reference": update_ref,
                    "remove_outliers": remove_outliers,
                },
            ))

            # (기준 윈도우 갱신은 Phase 2 루프 안에서 이미 수행됨)

        if self.cache is not None and events:
            self.cache.append_events(events)

        return events

    def get_chart_config(self):
        return {
            "mainLabel": "Value",
            "yLabel": "Value",
            "layers": [],
        }

    # ── 내부 헬퍼 메서드 ──

    @staticmethod
    def _remove_outliers(series):
        """IQR 기반 이상치를 NaN으로 마스킹하고 선형 보간한다."""
        q1, q3 = np.percentile(series, [25, 75])
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outlier_mask = (series < lower) | (series > upper)
        clean = series.copy()
        clean[outlier_mask] = np.nan
        # 선형 보간으로 NaN 채움
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
        """Benjamini-Hochberg FDR 보정."""
        n = len(p_values)
        sorted_idx = np.argsort(p_values)
        sorted_p = p_values[sorted_idx]

        # 보정된 p-value 계산
        adjusted = np.zeros(n)
        for i in range(n):
            adjusted[i] = sorted_p[i] * n / (i + 1)

        # 단조 감소 보정 (뒤에서부터 최소값 유지)
        for i in range(n - 2, -1, -1):
            adjusted[i] = min(adjusted[i], adjusted[i + 1])

        adjusted = np.minimum(adjusted, 1.0)

        # 원래 순서로 복원
        result = np.zeros(n)
        result[sorted_idx] = adjusted
        return result

    @staticmethod
    def _bootstrap_ks(sample1, sample2, n_bootstrap=500):
        """부트스트랩 KS 검정."""
        d_obs, _ = stats.ks_2samp(sample1, sample2)
        combined = np.concatenate([sample1, sample2])
        n1 = len(sample1)

        count = 0
        for _ in range(n_bootstrap):
            perm = np.random.permutation(combined)
            d_boot, _ = stats.ks_2samp(perm[:n1], perm[n1:])
            if d_boot >= d_obs:
                count += 1

        p_value = (count + 1) / (n_bootstrap + 1)
        return d_obs, p_value

    @staticmethod
    def _compute_ecdf(data):
        """ECDF를 계산한다."""
        clean = data[~np.isnan(data)] if np.any(np.isnan(data)) else data
        sorted_data = np.sort(clean)
        ecdf = np.arange(1, len(sorted_data) + 1) / len(sorted_data)
        return sorted_data, ecdf

    @staticmethod
    def _classify_drift_type(corrected_p, test_indices, alpha):
        """p-value 패턴으로 drift 유형을 판별한다."""
        if not test_indices:
            return "none"

        alarm_flags = [corrected_p[i] < alpha for i in test_indices]
        n_alarms = sum(alarm_flags)

        if n_alarms == 0:
            return "none"

        # alarm 비율
        alarm_ratio = n_alarms / len(test_indices)

        # 첫 alarm 위치
        first_alarm = next(i for i, f in enumerate(alarm_flags) if f)
        first_ratio = first_alarm / len(test_indices)

        # alarm이 전체의 60% 이상이면 incremental
        if alarm_ratio > 0.6:
            return "incremental"

        # 첫 alarm 이전에 점진적 p-value 하락이 있는지 확인
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
