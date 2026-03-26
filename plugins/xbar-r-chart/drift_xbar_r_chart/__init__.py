"""drift-xbar-r-chart: X-bar/R Chart drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import XbarRChartDetector

__version__ = "1.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "xbar_r_chart",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    url_prefix="/drift/xbar_r_chart",
)


@blueprint.route("/")
def page():
    return render_template(
        "plugin_page.html",
        plugin_name="X-bar/R Chart",
        plugin_key="xbar_r_chart",
    )


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="xbar_r_chart",
        name="X-bar/R Chart",
        version=__version__,
        description="X-bar/R 제어 차트 기반 이상 탐지. 서브그룹 평균과 범위를 동시에 모니터링하여 평균 이동과 산포 변화를 감지.",
        category="statistical",
        card_template="xbar_r_chart/card.html",
        page_url="/drift/xbar_r_chart/",
        icon="chart-bar",
        detector_class=XbarRChartDetector,
        params_schema={
            "subgroup_size": {"type": "int", "default": 5, "label": "Subgroup Size", "description": "서브그룹 크기. 데이터를 이 크기로 묶어서 분석."},
            "reference_ratio": {"type": "float", "default": 0.5, "label": "Reference Ratio", "description": "기준 구간 비율 (0~1)."},
        },
    )
