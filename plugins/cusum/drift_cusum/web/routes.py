"""CUSUM 플러그인 라우트."""

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
        """예제 데이터로 CUSUM 실행. POST 시 params를 받을 수 있다."""
        import pandas as pd
        import numpy as np
        from pathlib import Path

        # POST 요청에서 파라미터 추출
        params = {}
        if request.method == "POST" and request.is_json:
            body = request.get_json(silent=True) or {}
            params = body.get("params", {})

        # h 파라미터 처리: "auto" 문자열이면 그대로, 숫자 문자열이면 float 변환
        if "h" in params:
            h_val = params["h"]
            if isinstance(h_val, str) and h_val.lower() == "auto":
                params["h"] = "auto"
            elif h_val is not None:
                try:
                    params["h"] = float(h_val)
                except (ValueError, TypeError):
                    params["h"] = "auto"

        # cusum_example.csv 로드 (없으면 합성 데이터)
        example_dir = Path(__file__).resolve().parent.parent / "examples"
        cusum_csv = example_dir / "cusum_example.csv"

        if cusum_csv.exists():
            df = pd.read_csv(cusum_csv, parse_dates=["timestamp"])
        else:
            csv_files = list(example_dir.glob("*.csv"))
            if csv_files:
                df = pd.read_csv(csv_files[0], parse_dates=["timestamp"])
            else:
                # 합성 데이터: 정상 구간 + drift 구간
                np.random.seed(42)
                n = 200
                normal = np.random.normal(0.90, 0.02, n)
                drift = np.random.normal(0.80, 0.03, n // 2)
                values = np.concatenate([normal, drift])
                timestamps = pd.date_range("2026-01-01", periods=len(values), freq="10min")
                df = pd.DataFrame({"timestamp": timestamps, "value": values})

        from ..detector import CusumDetector
        from framework.plugin.cache import PluginCache

        detector = CusumDetector()
        detector.cache = PluginCache()
        data_ids = [f"example:{i:06d}" for i in range(len(df))]
        events = detector.analyze(
            new_data=df,
            data_ids=data_ids,
            stream="example",
            params=params,
        )

        # calibrated_h 추출 (첫 이벤트의 detail에서)
        calibrated_h = None
        if events and hasattr(events[0], 'detail'):
            calibrated_h = events[0].detail.get("calibrated_h")

        return _jsonify({
            "events": [e.to_dict() for e in events],
            "data": df.to_dict(orient="records"),
            "data_ids": data_ids,
            "calibrated_h": calibrated_h,
        })

    @bp.route("/api/run", methods=["POST"])
    def run():
        """사용자 파라미터로 CUSUM 실행."""
        body = request.get_json()
        params = body.get("params", {})

        # 현재는 예제 데이터로 실행 (추후 Store 연동)
        return example()
