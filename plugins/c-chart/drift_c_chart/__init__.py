"""drift-c-chart: C Chart (Count Chart) drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import CChartDetector
from .web.routes import register_routes

__version__ = "2.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "c_chart",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/static",
    url_prefix="/drift/c_chart",
)

register_routes(blueprint)


@blueprint.route("/")
def page():
    return render_template(
        "c_chart/page.html",
        plugin_name="C Chart",
        plugin_key="c_chart",
    )


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="c_chart",
        name="C Chart",
        version=__version__,
        description="C 차트(건수 차트) 기반 이상 탐지. 포아송분포 기반으로 에러 건수, timeout 건수 등 카운트 데이터의 이상 변동을 감지.",
        category="statistical",
        card_template="c_chart/card.html",
        page_url="/drift/c_chart/",
        icon="chart-bar",
        detector_class=CChartDetector,
        params_schema={
            "baseline_points": {"type": "int", "default": 30, "label": "Baseline Points",
                                "description": "기준 구간 포인트 수 (UCL/CL/LCL 계산용)."},
        },
    )
