"""Hotelling T2 플러그인 라우트."""

import json
import numpy as np
from flask import Blueprint, render_template, request, Response


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if hasattr(obj, 'isoformat'): return obj.isoformat()
        return super().default(obj)


def _jsonify(data):
    return Response(json.dumps(data, cls=NumpyEncoder, ensure_ascii=False), mimetype="application/json")


def register_routes(bp: Blueprint):

    @bp.route("/")
    def page():
        return render_template("hotelling/page.html")

    @bp.route("/api/example")
    def example():
        import pandas as pd
        np.random.seed(42)
        n = 200
        normal = np.random.normal(0.90, 0.02, n)
        drift = np.random.normal(0.80, 0.03, n // 2)
        values = np.concatenate([normal, drift])
        timestamps = pd.date_range("2026-01-01", periods=len(values), freq="10min")
        df = pd.DataFrame({"timestamp": timestamps, "value": values})

        from ..detector import HotellingDetector
        detector = HotellingDetector()
        data_ids = [f"example:{i:06d}" for i in range(len(df))]
        events = detector.detect(data=df, data_ids=data_ids, stream="example", params={})

        return _jsonify({
            "events": [e.to_dict() for e in events],
            "data": df.to_dict(orient="records"),
        })

    @bp.route("/api/run", methods=["POST"])
    def run():
        return example()
