"""MEWMA (Multivariate EWMA) drift detector v3.0.

1.D 책임 분리 (design_principles 6장):
- analyze() 3단계 패턴, 1.B placeholder 제거
- 누적 재실행 + replace_events=True 로 cache 통째 교체
- baseline 고정 포인트 수
"""

from datetime import timedelta

import numpy as np
from scipy.stats import chi2

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class MewmaDetector(DriftPlugin):
    """MEWMA 다변량 EWMA 기반 drift 탐지기.

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
        "baseline_points": 100,
    }

    def analyze(self, new_data, data_ids, stream, params,
                calculated_until=None, previous_events=None):
        if new_data.empty or self.cache is None:
            return []

        snapshot = self.cache.append_and_snapshot(
            new_data.to_dict("records")
        )
        n = len(snapshot)

        params = {**self.DEFAULT_PARAMS, **params}
        lam = float(params["lambda_"])
        alpha = float(params["alpha"])
        baseline_points = int(params["baseline_points"])

        # Feature columns: snapshot dict의 numeric 키 중 timestamp/count 제외
        feature_cols = self._extract_feature_cols(snapshot)
        if not feature_cols:
            return []
        p = len(feature_cols)

        baseline_end = min(baseline_points, n)
        if baseline_end < max(10, p + 1) or (n - baseline_end) < 5:
            return []

        all_events, layer_rows = self._run_mewma(
            snapshot, stream, lam, alpha, baseline_end, feature_cols,
        )
        new_events = self._dedupe_events(all_events, previous_events)

        self.cache.commit_analysis(
            layer_rows=layer_rows, events=all_events, replace_events=True,
        )
        return new_events

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        raise NotImplementedError("MewmaDetector는 analyze()를 사용한다.")

    @staticmethod
    def _extract_feature_cols(snapshot):
        if not snapshot:
            return []
        sample = snapshot[0]
        excluded = {"timestamp", "count"}
        cols = []
        for k, v in sample.items():
            if k in excluded:
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cols.append(k)
        return cols

    def _run_mewma(self, snapshot, stream, lam, alpha, baseline_end,
                   feature_cols):
        n = len(snapshot)
        p = len(feature_cols)
        timestamps = [row["timestamp"] for row in snapshot]

        X = np.zeros((n, p))
        for i, row in enumerate(snapshot):
            for j, c in enumerate(feature_cols):
                X[i, j] = float(row.get(c, 0.0))

        baseline = X[:baseline_end]
        mu0 = np.mean(baseline, axis=0)
        sigma0 = np.cov(baseline, rowvar=False)
        if p == 1:
            sigma0 = np.array([[float(sigma0)]])

        if abs(np.linalg.det(sigma0)) < 1e-12:
            sigma0 = sigma0 + np.eye(p) * 1e-6

        Z = np.zeros((n, p))
        Z[0] = mu0.copy()
        for t in range(1, n):
            Z[t] = lam * X[t] + (1 - lam) * Z[t - 1]

        sigma_z = (lam / (2 - lam)) * sigma0
        try:
            sigma_z_inv = np.linalg.inv(sigma_z)
        except np.linalg.LinAlgError:
            sigma_z_inv = np.linalg.pinv(sigma_z)

        d2 = np.zeros(n)
        for t in range(n):
            diff = Z[t] - mu0
            d2[t] = float(diff @ sigma_z_inv @ diff)

        ucl = float(chi2.ppf(1 - alpha, p))

        alarm_mask = np.zeros(n, dtype=int)
        for t in range(baseline_end, n):
            if d2[t] > ucl:
                alarm_mask[t] = 1
        alarm_indices = list(np.where(alarm_mask == 1)[0])

        layer_rows = []
        for i in range(n):
            row = {
                "timestamp": timestamps[i],
                "d2": float(d2[i]),
                "alarm": int(alarm_mask[i]),
                "ucl": float(ucl),
            }
            for j, c in enumerate(feature_cols):
                row[f"ewma_{c}"] = float(Z[i, j])
            layer_rows.append(row)

        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            peak_offset = int(np.argmax(d2[group_start:group_end + 1]))
            peak_idx = group_start + peak_offset
            peak_d2 = float(d2[peak_idx])
            score = float(peak_d2 / ucl) if ucl > 0 else 0.0

            events.append(DriftEvent(
                stream=stream,
                plugin="mewma",
                detected_at=timestamps[peak_idx],
                data_from=timestamps[group_start],
                data_to=timestamps[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(float(score), 4),
                message=f"MEWMA D²={peak_d2:.4f} > UCL={ucl:.4f} (p={p})",
                data_ids=[
                    f"{stream}:{idx}"
                    for idx in range(group_start, group_end + 1)
                ],
                data_count=int(group_end - group_start + 1),
                detail={
                    "algorithm": "mewma",
                    "d2_value": round(float(peak_d2), 4),
                    "ucl": round(float(ucl), 4),
                    "mu0": [round(float(v), 6) for v in mu0],
                    "lambda": float(lam),
                    "alpha": float(alpha),
                    "num_features": int(p),
                    "feature_names": list(feature_cols),
                    "baseline_points": int(baseline_end),
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
                    "field": "d2",
                    "label": "D²",
                    "color": "#1f77b4",
                    "yAxis": "right",
                },
                {
                    "type": "line",
                    "field": "ucl",
                    "label": "UCL",
                    "color": "#d62728",
                    "yAxis": "right",
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
