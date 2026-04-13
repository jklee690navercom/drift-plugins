"""drift-ewma: EWMA control chart drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import EwmaDetector
from .web.routes import register_routes

__version__ = "2.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "ewma",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/static",
    url_prefix="/drift/ewma",
)

register_routes(blueprint)


@blueprint.route("/")
def page():
    return render_template(
        "ewma/page.html",
        plugin_name="EWMA",
        plugin_key="ewma",
    )


def register(app):
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="ewma",
        name="EWMA",
        version=__version__,
        description="EWMA 관리도 기반 drift 탐지. UCL/LCL 관리한계로 점진적 평균 변화 감지.",
        category="statistical",
        card_template="ewma/card.html",
        page_url="/drift/ewma/",
        icon="chart-line",
        detector_class=EwmaDetector,
        params_schema={
            "lambda_": {"type": "float", "default": 0.2, "label": "Lambda (λ)",
                        "description": "EWMA 평활 계수 (0.05~0.3). 작을수록 부드러움."},
            "L": {"type": "float", "default": 3.0, "label": "L (한계폭)",
                  "description": "관리한계 배수. 작을수록 민감, 클수록 안정적."},
            "baseline_points": {"type": "int", "default": 50, "label": "Baseline Points",
                                "description": "기준 구간 포인트 수 (μ0, σ0 추정용)."},
            "cooldown": {"type": "int", "default": 5, "label": "Cooldown",
                         "description": "알람 후 최소 간격 (연속 알람 억제)."},
            "two_sided": {"type": "bool", "default": True, "label": "Two-sided",
                          "description": "양측 검정 (상승+하락 모두 감지)."},
        },
    )
