"""drift-shap: Statistical Profile Drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import ShapDetector
from .web.routes import register_routes

__version__ = "2.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "shap",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/static",
    url_prefix="/drift/shap",
)

register_routes(blueprint)


@blueprint.route("/")
def page():
    return render_template(
        "shap/page.html",
        plugin_name="SHAP Drift",
        plugin_key="shap",
    )


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="shap",
        name="SHAP Drift",
        version=__version__,
        description="Statistical Profile Drift 탐지. Rolling window의 통계 프로파일(mean, std, skewness, kurtosis) 변화를 정규화 거리로 측정.",
        category="statistical",
        card_template="shap/card.html",
        page_url="/drift/shap/",
        icon="project-diagram",
        detector_class=ShapDetector,
        params_schema={
            "window_size": {"type": "int", "default": 100, "label": "Window Size",
                            "description": "통계 프로파일 계산 윈도우 크기."},
            "baseline_windows": {"type": "int", "default": 50, "label": "Baseline Windows",
                                 "description": "기준 구간 윈도우 수 (프로파일 평균 계산용)."},
            "threshold": {"type": "float", "default": 3.0, "label": "Threshold",
                          "description": "정규화 유클리드 거리 임계값. 작을수록 민감."},
        },
    )
