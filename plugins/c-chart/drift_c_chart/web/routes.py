"""C Chart 플러그인 라우트."""

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

    @bp.route("/")
    def page():
        return render_template("c_chart/page.html")

    @bp.route("/api/example")
    def example():
        """예제 데이터로 C Chart 실행."""
        import pandas as pd
        import numpy as np

        # 합성 데이터: 카운트 데이터
        np.random.seed(42)
        normal_counts = np.random.poisson(3, 40)     # ~3 errors/hour
        abnormal_counts = np.random.poisson(12, 20)   # ~12 errors/hour
        counts = np.concatenate([normal_counts, abnormal_counts]).astype(float)
        timestamps = pd.date_range("2026-01-01", periods=len(counts), freq="1h")
        df = pd.DataFrame({"timestamp": timestamps, "value": counts})

        from ..detector import CChartDetector
        detector = CChartDetector()
        data_ids = [f"example:{i:06d}" for i in range(len(df))]
        events = detector.detect(
            data=df,
            data_ids=data_ids,
            stream="example",
            params={},
        )

        return _jsonify({
            "events": [e.to_dict() for e in events],
            "data": df.to_dict(orient="records"),
            "data_ids": data_ids,
        })

    @bp.route("/api/run", methods=["POST"])
    def run():
        """사용자 파라미터로 C Chart 실행."""
        body = request.get_json()
        params = body.get("params", {})
        return example()
