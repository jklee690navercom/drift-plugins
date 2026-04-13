"""KS Test 플러그인 라우트."""

import json
import numpy as np
from flask import Blueprint, render_template, request, Response


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)


def _jsonify(data):
    return Response(
        json.dumps(data, cls=NumpyEncoder, ensure_ascii=False),
        mimetype="application/json",
    )


# 프리셋 정의
PRESETS = {
    "quick": {
        "window_size": 30, "alpha": 0.05, "correction": "none",
        "update_reference": False, "remove_outliers": False,
        "baseline_points": 100,
    },
    "standard": {
        "window_size": 100, "alpha": 0.05, "correction": "bh",
        "update_reference": True, "remove_outliers": True,
        "baseline_points": 100,
    },
    "precision": {
        "window_size": 200, "alpha": 0.01, "correction": "bonferroni",
        "update_reference": True, "remove_outliers": True,
        "baseline_points": 100,
    },
    "streaming": {
        "window_size": 100, "alpha": 0.05, "correction": "bh",
        "update_reference": True, "remove_outliers": False,
        "baseline_points": 100,
    },
    "small_sample": {
        "window_size": 30, "alpha": 0.10, "correction": "none",
        "update_reference": False, "remove_outliers": False,
        "baseline_points": 100,
    },
}


def register_routes(bp: Blueprint):

    @bp.route("/")
    def page():
        return render_template("ks_test/page.html")

    @bp.route("/api/presets")
    def presets():
        """프리셋 목록 반환."""
        return _jsonify(PRESETS)

    @bp.route("/api/example")
    def example():
        """예제 데이터로 KS Test 실행."""
        import pandas as pd

        preset = request.args.get("preset", "standard")
        params = dict(PRESETS.get(preset, PRESETS["standard"]))

        # 사용자 오버라이드
        for key in ["window_size", "alpha", "baseline_points"]:
            if key in request.args:
                params[key] = float(request.args[key])
        for key in ["correction"]:
            if key in request.args:
                params[key] = request.args[key]
        for key in ["update_reference", "remove_outliers"]:
            if key in request.args:
                params[key] = request.args[key].lower() == "true"

        # 합성 데이터: 다중 drift + 이상치
        np.random.seed(123)
        n_total = 500

        # 5개 구간: 정상 → drift1 → 복귀 → drift2 → 복귀
        segments = [
            (100, 0.90, 0.02),  # 정상
            (100, 0.80, 0.03),  # Drift 1
            (100, 0.88, 0.02),  # 복귀
            (100, 0.72, 0.04),  # Drift 2
            (100, 0.90, 0.02),  # 복귀
        ]
        values = np.concatenate([
            np.random.normal(mu, sigma, count)
            for count, mu, sigma in segments
        ])

        # 이상치 삽입 (5건)
        outlier_indices = [45, 120, 250, 310, 420]
        for idx in outlier_indices:
            values[idx] = np.random.choice([0.35, 0.98])

        timestamps = pd.date_range(
            "2026-01-01", periods=n_total, freq="10min")
        df = pd.DataFrame({"timestamp": timestamps, "value": values})

        from ..detector import KsTestDetector
        from framework.plugin.cache import PluginCache

        detector = KsTestDetector()
        detector.cache = PluginCache()
        data_ids = [f"example:{i:06d}" for i in range(len(df))]
        events = detector.analyze(
            new_data=df,
            data_ids=data_ids,
            stream="example",
            params=params,
        )

        return _jsonify({
            "events": [e.to_dict() for e in events],
            "data": df.to_dict(orient="records"),
            "data_ids": data_ids,
            "params": params,
            "preset": preset,
        })

    @bp.route("/api/run", methods=["POST"])
    def run():
        """커스텀 파라미터로 실행."""
        body = request.get_json() or {}
        params = body.get("params", {})
        # preset 기반 + 오버라이드
        preset = body.get("preset", "standard")
        merged = dict(PRESETS.get(preset, PRESETS["standard"]))
        merged.update(params)
        # example과 동일한 데이터로 실행
        return example()
