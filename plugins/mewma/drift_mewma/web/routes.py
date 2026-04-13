"""MEWMA 플러그인 라우트 — 다변량 예제 데이터 생성."""

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
        """예제 데이터로 MEWMA 실행 — 3-phase 다변량 합성 데이터.

        Phase 1 (정상): 200 samples, μ=[0,0,0,0,0], weak correlation (0.3)
        Phase 2 (평균 이동): 100 samples, μ=[1.5,-1.0,0,0,0]
        Phase 3 (공분산 변화): 100 samples, correlation → 0.8, x3 분산 증가
        """
        import pandas as pd

        # POST 요청에서 파라미터 추출
        params = {}
        if request.method == "POST" and request.is_json:
            body = request.get_json(silent=True) or {}
            params = body.get("params", {})

        np.random.seed(42)
        p = 5  # number of features

        # ── Phase 1: Normal (200 samples) ──
        mu1 = np.zeros(p)
        cov1 = np.eye(p) * 1.0
        # Add weak correlation (0.3)
        for i in range(p):
            for j in range(p):
                if i != j:
                    cov1[i, j] = 0.3
        phase1 = np.random.multivariate_normal(mu1, cov1, 200)

        # ── Phase 2: Mean shift (100 samples) ──
        mu2 = np.array([1.5, -1.0, 0.0, 0.0, 0.0])
        phase2 = np.random.multivariate_normal(mu2, cov1, 100)

        # ── Phase 3: Covariance change (100 samples) ──
        mu3 = np.zeros(p)
        cov3 = np.eye(p) * 1.0
        # Strong correlation (0.8) and increased x3 variance
        for i in range(p):
            for j in range(p):
                if i != j:
                    cov3[i, j] = 0.8
        cov3[2, 2] = 3.0  # x3 variance increases
        phase3 = np.random.multivariate_normal(mu3, cov3, 100)

        # ── Combine ──
        X = np.vstack([phase1, phase2, phase3])
        n_total = len(X)
        timestamps = pd.date_range("2026-01-01", periods=n_total, freq="10min")

        feature_names = [f"x{i}" for i in range(p)]
        df = pd.DataFrame(X, columns=feature_names)
        df["timestamp"] = timestamps

        from ..detector import MewmaDetector
        from framework.plugin.cache import PluginCache

        detector = MewmaDetector()
        detector.cache = PluginCache()
        data_ids = [f"example:{i:06d}" for i in range(n_total)]
        events = detector.analyze(
            new_data=df,
            data_ids=data_ids,
            stream="example_multivariate",
            params=params,
        )

        # Build response data
        data_records = []
        for i in range(n_total):
            row = {"timestamp": timestamps[i].isoformat()}
            for col in feature_names:
                row[col] = float(X[i, feature_names.index(col)])
            data_records.append(row)

        return _jsonify({
            "events": [e.to_dict() for e in events],
            "data": data_records,
            "data_ids": data_ids,
            "feature_names": feature_names,
        })

    @bp.route("/api/run", methods=["POST"])
    def run():
        """사용자 파라미터로 MEWMA 실행."""
        return example()
