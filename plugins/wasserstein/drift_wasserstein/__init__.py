"""drift-wasserstein: Wasserstein distance drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import WassersteinDetector
from .web.routes import register_routes

__version__ = "2.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "wasserstein",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/static",
    url_prefix="/drift/wasserstein",
)

register_routes(blueprint)


@blueprint.route("/")
def page():
    return render_template(
        "wasserstein/page.html",
        plugin_name="Wasserstein",
        plugin_key="wasserstein",
    )


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="wasserstein",
        name="Wasserstein",
        version=__version__,
        description="Wasserstein 거리(Earth Mover's Distance) 기반 분포 변화 탐지. EWMA 평활화로 노이즈 감소.",
        category="statistical",
        card_template="wasserstein/card.html",
        page_url="/drift/wasserstein/",
        icon="chart-area",
        detector_class=WassersteinDetector,
        params_schema={
            "window_size": {"type": "int", "default": 50, "label": "Window Size",
                            "description": "슬라이딩 윈도우 크기"},
            "reference_ratio": {"type": "float", "default": 0.5, "label": "Reference Ratio",
                                "description": "기준 구간 비율."},
            "threshold": {"type": "float", "default": 0.1, "label": "Threshold",
                          "description": "Wasserstein 거리 임계값."},
            "lambda_smooth": {"type": "float", "default": 0.3, "label": "Lambda (EWMA)",
                              "description": "EWMA 평활 계수 (0~1). 클수록 최근값 반영."},
            "update_reference": {"type": "bool", "default": True, "label": "Update Reference",
                                 "description": "드리프트 후 기준 윈도우 갱신 여부."},
            "baseline_ratio": {"type": "float", "default": 0.5, "label": "Baseline Ratio",
                               "description": "기준 통계 추정 비율."},
        },
    )
