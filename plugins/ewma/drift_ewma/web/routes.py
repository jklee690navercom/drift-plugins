"""MEWMA 플러그인 라우트."""

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
        """예제 데이터로 MEWMA 실행. POST 시 params를 받을 수 있다."""
        import pandas as pd

        # POST 요청에서 파라미터 추출
        params = {}
        if request.method == "POST" and request.is_json:
            body = request.get_json(silent=True) or {}
            params = body.get("params", {})

        # 합성 데이터: 정상 구간 + drift 구간
        np.random.seed(42)
        normal = np.random.normal(0.90, 0.02, 200)
        drift = np.random.normal(0.80, 0.03, 100)
        values = np.concatenate([normal, drift])
        timestamps = pd.date_range("2026-01-01", periods=len(values), freq="10min")
        df = pd.DataFrame({"timestamp": timestamps, "value": values})

        from ..detector import MewmaDetector
        detector = MewmaDetector()
        data_ids = [f"example:{i:06d}" for i in range(len(df))]
        events = detector.detect(
            data=df,
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
        """사용자 파라미터로 MEWMA 실행."""
        body = request.get_json()
        params = body.get("params", {})

        # 현재는 예제 데이터로 실행 (추후 Store 연동)
        return example()
