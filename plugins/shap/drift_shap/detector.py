"""SHAP drift detector — DriftPlugin 기반 운영 환경용."""

from datetime import timedelta

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class ShapDetector(DriftPlugin):
    """Feature importance 변화 기반 drift 탐지기.

    단변량 데이터에서 rolling statistics(rolling_mean, rolling_std, rolling_diff)를
    feature로 추출한 뒤, 기준 구간과 테스트 윈도우 간 KS 검정으로
    feature 분포 변화를 감지한다.
    Score = 유의한 feature 비율 기반.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "window_size": 50,
        "reference_ratio": 0.5,
        "alpha": 0.05,
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
        ref_ratio = float(params["reference_ratio"])
        alpha = float(params["alpha"])

        # ── Rolling statistics를 feature로 추출 ──
        roll_win = min(10, window_size // 5)
        if roll_win < 2:
            roll_win = 2

        rolling_mean = pd.Series(series).rolling(roll_win, min_periods=1).mean().to_numpy()
        rolling_std = pd.Series(series).rolling(roll_win, min_periods=1).std().fillna(0).to_numpy()
        rolling_diff = np.concatenate([[0], np.diff(series)])

        features = {
            "rolling_mean": rolling_mean,
            "rolling_std": rolling_std,
            "rolling_diff": rolling_diff,
        }

        # ── 기준 구간 ──
        ref_end = int(n * ref_ratio)
        if ref_end < window_size or (n - ref_end) < window_size:
            return []

        # ── 슬라이딩 윈도우에서 각 feature의 KS 검정 ──
        drift_scores = np.zeros(n)
        feature_scores = {name: np.zeros(n) for name in features}
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        for i in range(ref_end, n - window_size + 1):
            mid = i + window_size // 2
            sig_count = 0
            max_score = 0.0

            for name, feat in features.items():
                ref_feat = feat[:ref_end]
                test_feat = feat[i:i + window_size]
                stat, pval = sp_stats.ks_2samp(ref_feat, test_feat)
                feat_score = stat  # KS statistic as drift score
                feature_scores[name][mid] = feat_score

                if pval < alpha:
                    sig_count += 1
                max_score = max(max_score, feat_score)

            # 모든 feature에서 유의한 변화가 있으면 drift
            drift_scores[mid] = max_score
            if sig_count == len(features):
                alarm_mask[mid] = 1
                alarm_indices.append(mid)

        # ── Cache에 데이터 기록 ──
        cache_rows = []
        for i in range(len(series)):
            cache_rows.append({
                "timestamp": timestamps.iloc[i],
                "value": float(series[i]),
            })

        if self.cache is not None:
            self.cache.append_data(cache_rows)

        if not alarm_indices:
            return []

        # ── DriftEvent 생성 ──
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            group_ids = data_ids[group_start:group_end + 1]

            peak_idx = group_start + int(np.argmax(drift_scores[group_start:group_end + 1]))
            peak_score = float(drift_scores[peak_idx])
            score = peak_score / 0.5  # normalize: KS stat of 0.5 = score 1.0

            feat_detail = {}
            for name in features:
                feat_detail[f"{name}_score"] = round(float(feature_scores[name][peak_idx]), 4)

            events.append(DriftEvent(
                stream=stream,
                plugin="shap",
                detected_at=timestamps.iloc[peak_idx],
                data_from=timestamps.iloc[group_start],
                data_to=timestamps.iloc[group_end],
                severity=self._score_to_severity(score),
                detected=True,
                score=round(score, 4),
                message=f"SHAP drift alarm: max_ks={peak_score:.4f}, all {len(features)} features significant (alpha={alpha})",
                data_ids=group_ids,
                data_count=len(group_ids),
                detail={
                    "algorithm": "shap",
                    "peak_ks_stat": round(peak_score, 4),
                    "alpha": alpha,
                    "window_size": window_size,
                    "reference_size": ref_end,
                    "alarm_count": group_end - group_start + 1,
                    "drift_score_series": drift_scores.tolist(),
                    "rolling_mean_score_series": feature_scores["rolling_mean"].tolist(),
                    "rolling_std_score_series": feature_scores["rolling_std"].tolist(),
                    "rolling_diff_score_series": feature_scores["rolling_diff"].tolist(),
                    "alarm_mask": alarm_mask.tolist(),
                    **feat_detail,
                },
            ))

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
