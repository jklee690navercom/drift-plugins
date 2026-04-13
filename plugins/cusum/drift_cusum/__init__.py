"""drift-cusum: CUSUM drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import CusumDetector
from .web.routes import register_routes

__version__ = "2.1.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "cusum",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/static",
    url_prefix="/drift/cusum",
)

# routes.py의 라우트 등록 (example API 등)
register_routes(blueprint)


@blueprint.route("/")
def page():
    return render_template(
        "cusum/page.html",
        plugin_name="CUSUM",
        plugin_key="cusum",
    )


def register(app):
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="cusum",
        name="CUSUM",
        version=__version__,
        description="누적합(CUSUM) 기반 변화점 탐지. 평균의 점진적 이동에 민감. Baseline 분리, FIR 지원.",
        category="statistical",
        card_template="cusum/card.html",
        page_url="/drift/cusum/",
        icon="chart-line",
        detector_class=CusumDetector,
        params_schema={
            "k": {"type": "float", "default": 0.25, "label": "Slack (k)",
                   "description": "허용 편차. 감지할 변화량 δ의 절반 (k=δ/2)"},
            "h": {"type": "string", "default": "auto", "label": "Threshold (h)",
                   "description": "알람 임계값. 'auto'이면 Bootstrap 캘리브레이션으로 자동 결정"},
            "baseline_points": {"type": "int", "default": 50, "label": "Baseline Points",
                                "description": "기준 구간 포인트 수. 이 구간에서 μ0, σ0를 계산"},
            "reset": {"type": "bool", "default": True, "label": "Reset after alarm",
                      "description": "알람 후 CUSUM 누적합을 0으로 리셋"},
            "robust": {"type": "bool", "default": True, "label": "Robust Standardization",
                       "description": "True: median/MAD, False: mean/std"},
            "calibration_B": {"type": "int", "default": 500, "label": "Bootstrap B",
                              "description": "Bootstrap 시뮬레이션 반복 횟수"},
            "calibration_q": {"type": "float", "default": 0.995, "label": "Quantile (q)",
                              "description": "Bootstrap 분위수. 높을수록 보수적 임계값"},
            "calibration_block": {"type": "int", "default": None, "label": "Block Size",
                                  "description": "블록 부트스트랩 블록 크기 (None=iid)"},
        },
    )
