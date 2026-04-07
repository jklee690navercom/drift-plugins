"""MEWMA (Multivariate EWMA) drift detector — DriftPlugin 기반."""

from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.stats import chi2

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class MewmaDetector(DriftPlugin):
    """MEWMA 다변량 EWMA 기반 drift 탐지기.

    다변량 데이터의 분포 변화를 Mahalanobis 거리로 감지한다.
    - Filter:    Z_t = λ·X_t + (I-λ)·Z_{t-1}  (벡터 버전)
    - Covariance: Σ_Z ≈ (λ/(2-λ))·Σ0
    - Statistic:  D²_t = (Z_t - μ0)^T · Σ_Z^{-1} · (Z_t - μ0)
    - Alarm:      D² > UCL  (χ² 분포 기반)
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "lambda_": 0.1,
        "alpha": 0.001,
        "baseline_ratio": 0.3333,
    }

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        if data.empty:
            return []

        params = {**self.DEFAULT_PARAMS, **params}
        lam = float(params["lambda_"])
        alpha = float(params["alpha"])
        baseline_ratio = float(params["baseline_ratio"])

        timestamps = data["timestamp"]
        n = len(data)

        # ── Feature columns: all numeric except timestamp, count ──
        exclude_cols = {"timestamp", "count"}
        feature_cols = [c for c in data.columns
                        if c not in exclude_cols and pd.api.types.is_numeric_dtype(data[c])]
        if not feature_cols:
            return []

        X = data[feature_cols].to_numpy(dtype=float)
        p = X.shape[1]  # number of features

        # ── Baseline estimation ──
        baseline_end = int(n * baseline_ratio)
        if baseline_end < max(10, p + 1) or (n - baseline_end) < 5:
            return []

        baseline = X[:baseline_end]
        mu0 = np.mean(baseline, axis=0)             # (p,)
        sigma0 = np.cov(baseline, rowvar=False)      # (p, p)

        # Handle single-feature edge case
        if p == 1:
            sigma0 = np.array([[float(sigma0)]])

        # Regularize if near-singular
        det = np.linalg.det(sigma0)
        if abs(det) < 1e-12:
            sigma0 += np.eye(p) * 1e-6

        # ── EWMA filter (vector version) ──
        Z = np.zeros((n, p))
        Z[0] = mu0.copy()
        for t in range(1, n):
            Z[t] = lam * X[t] + (1 - lam) * Z[t - 1]

        # ── Σ_Z and its inverse ──
        sigma_z = (lam / (2 - lam)) * sigma0
        try:
            sigma_z_inv = np.linalg.inv(sigma_z)
        except np.linalg.LinAlgError:
            sigma_z_inv = np.linalg.pinv(sigma_z)

        # ── D² statistic (Mahalanobis distance) ──
        d2 = np.zeros(n)
        for t in range(n):
            diff = Z[t] - mu0
            d2[t] = float(diff @ sigma_z_inv @ diff)

        # ── UCL from χ² distribution ──
        ucl = float(chi2.ppf(1 - alpha, p))

        # ── Alarm detection (skip baseline warmup) ──
        alarm_mask = np.zeros(n, dtype=int)
        for t in range(baseline_end, n):
            if d2[t] > ucl:
                alarm_mask[t] = 1

        alarm_indices = list(np.where(alarm_mask == 1)[0])

        # ── Cache ──
        # 전문가 차트가 cache.data에서 직접 series를 읽도록 d2/alarm/ucl과
        # per-feature ewma 값을 row마다 적재한다.
        cache_rows = []
        for i in range(n):
            row = {
                "timestamp": timestamps.iloc[i],
                "value": float(d2[i]),  # D² as value for BaseChart compatibility
                "d2": float(d2[i]),
                "alarm": int(alarm_mask[i]),
                "ucl": float(ucl),
            }
            # per-feature EWMA Z 값을 컬럼으로 추가 (ewma_<feature>)
            for j, col in enumerate(feature_cols):
                row[f"ewma_{col}"] = float(Z[i, j])
            cache_rows.append(row)
        if self.cache is not None:
            self.cache.append_data(cache_rows)

        if not alarm_indices:
            return []

        # ── Build per-feature EWMA series for detail ──
        ewma_series = {}
        for j, col in enumerate(feature_cols):
            ewma_series[col] = [float(Z[t, j]) for t in range(n)]

        # ── DriftEvent generation ──
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1]

            # Peak = point with max D²
            peak_offset = int(np.argmax(d2[group_start:group_end + 1]))
            peak_idx = group_start + peak_offset
            peak_d2 = float(d2[peak_idx])
            score = float(peak_d2 / ucl) if ucl > 0 else 0.0

            events.append(DriftEvent(
                stream=stream,
                plugin="mewma",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=f"MEWMA D²={peak_d2:.4f} > UCL={ucl:.4f} (p={p})",
                data_ids=group_ids,
                data_count=int(len(group_ids)),
                detail={
                    "algorithm": "mewma",
                    "d2_value": round(float(peak_d2), 4),
                    "ucl": round(float(ucl), 4),
                    "mu0": [round(float(v), 6) for v in mu0],
                    "sigma0": [[round(float(v), 6) for v in row] for row in sigma0],
                    "lambda": float(lam),
                    "alpha": float(alpha),
                    "num_features": int(p),
                    "feature_names": list(feature_cols),
                    "baseline_end": int(baseline_end),
                    "alarm_count": int(group_end - group_start + 1),
                    "d2_series": [round(float(v), 6) for v in d2],
                    "ewma_series": {k: [round(float(x), 6) for x in vs]
                                    for k, vs in ewma_series.items()},
                    "alarm_mask": [int(v) for v in alarm_mask],
                },
            ))

        if self.cache is not None and events:
            self.cache.append_events(events)

        return events

    def get_chart_config(self):
        return {
            "mainLabel": "D² Statistic",
            "yLabel": "D²",
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
