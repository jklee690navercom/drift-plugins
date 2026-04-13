"""P Chart 플러그인 라우트."""

import json
import numpy as np
from flask import Blueprint, render_template, request, Response


class NumpyEncoder(json.JSONEncoder):
    """numpy 타입을 JSON으로 변환."""
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
    """numpy 타입을 지원하는 JSON 응답."""
    return Response(
        json.dumps(data, cls=NumpyEncoder, ensure_ascii=False),
        mimetype="application/json",
    )


def register_routes(bp: Blueprint):

    @bp.route("/api/example", methods=["GET", "POST"])
    def example():
        """예제 데이터로 P Chart 실행. POST 시 params를 받을 수 있다."""
        import pandas as pd

        # POST 요청에서 파라미터 추출
        params = {}
        if request.method == "POST" and request.is_json:
            body = request.get_json(silent=True) or {}
            params = body.get("params", {})

        # 합성 데이터: 비율 데이터
        np.random.seed(42)
        sample_size = 50
        normal_errors = np.random.binomial(sample_size, 0.05, 40) / sample_size  # ~5% error rate
        abnormal_errors = np.random.binomial(sample_size, 0.20, 20) / sample_size  # ~20% error rate
        proportions = np.concatenate([normal_errors, abnormal_errors])
        timestamps = pd.date_range("2026-01-01", periods=len(proportions), freq="1h")
        df = pd.DataFrame({"timestamp": timestamps, "value": proportions})

        from ..detector import PChartDetector
        from framework.plugin.cache import PluginCache

        detector = PChartDetector()
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
        })

    @bp.route("/api/run", methods=["POST"])
    def run():
        """사용자 파라미터로 P Chart 실행."""
        return example()
