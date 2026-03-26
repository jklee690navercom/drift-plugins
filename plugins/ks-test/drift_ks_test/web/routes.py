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


def register_routes(bp: Blueprint):

    @bp.route("/")
    def page():
        return render_template("ks_test/page.html")

    @bp.route("/api/example")
    def example():
        """예제 데이터로 KS Test 실행."""
        import pandas as pd

        # 합성 데이터: 정상 → 분포 변화 (평균 이동 + 분산 증가)
        np.random.seed(123)
        n_ref = 200
        n_drift = 150
        ref_data = np.random.normal(0.90, 0.02, n_ref)
        drift_data = np.random.normal(0.82, 0.04, n_drift)
        values = np.concatenate([ref_data, drift_data])
        timestamps = pd.date_range("2026-01-01", periods=len(values), freq="10min")
        df = pd.DataFrame({"timestamp": timestamps, "value": values})

        from ..detector import KsTestDetector
        detector = KsTestDetector()
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
        body = request.get_json()
        return example()
