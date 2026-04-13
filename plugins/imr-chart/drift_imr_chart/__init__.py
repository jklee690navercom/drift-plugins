"""drift-imr-chart: I-MR Chart (Individual-Moving Range) drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import ImrChartDetector
from .web.routes import register_routes

__version__ = "2.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "imr_chart",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/static",
    url_prefix="/drift/imr_chart",
)

register_routes(blueprint)


@blueprint.route("/")
def page():
    return render_template(
        "imr_chart/page.html",
        plugin_name="I-MR Chart",
        plugin_key="imr_chart",
    )


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="imr_chart",
        name="I-MR Chart",
        version=__version__,
        description="개별값-이동범위(I-MR) 제어 차트 기반 이상 탐지. 개별 측정값의 이상치와 변동성 변화를 동시에 감지.",
        category="statistical",
        card_template="imr_chart/card.html",
        page_url="/drift/imr_chart/",
        icon="chart-line",
        detector_class=ImrChartDetector,
        params_schema={
            "baseline_points": {"type": "int", "default": 30, "label": "Baseline Points",
                                "description": "기준 구간 포인트 수 (UCL/CL/LCL 계산용)."},
        },
    )
