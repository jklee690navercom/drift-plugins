"""drift-c-chart: C Chart (Count Chart) drift detection plugin."""

from pathlib import Path
from flask import Blueprint
from .detector import CChartDetector

__version__ = "1.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "c_chart",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/c_chart-static",
    url_prefix="/drift/c_chart",
)

from .web.routes import register_routes  # noqa: E402
register_routes(blueprint)


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
        example_data=_PKG_DIR / "examples" / "sample.csv",
        params_schema={
            "reference_ratio": {"type": "float", "default": 0.5, "label": "Reference Ratio", "description": "기준 구간 비율 (0~1)."},
        },
    )
