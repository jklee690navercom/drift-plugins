"""drift-p-chart: P Chart (Proportion Chart) drift detection plugin."""

from pathlib import Path
from flask import Blueprint
from .detector import PChartDetector

__version__ = "1.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "p_chart",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/p_chart-static",
    url_prefix="/drift/p_chart",
)

from .web.routes import register_routes  # noqa: E402
register_routes(blueprint)


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="p_chart",
        name="P Chart",
        version=__version__,
        description="P 차트(비율 차트) 기반 이상 탐지. 불량률/에러율 등 비율 지표의 이상 변동을 감지.",
        category="statistical",
        card_template="p_chart/card.html",
        page_url="/drift/p_chart/",
        icon="chart-bar",
        detector_class=PChartDetector,
        example_data=_PKG_DIR / "examples" / "sample.csv",
        params_schema={
            "sample_size": {"type": "int", "default": 50, "label": "Sample Size (n)", "description": "각 그룹의 검사 수."},
            "reference_ratio": {"type": "float", "default": 0.5, "label": "Reference Ratio", "description": "기준 구간 비율 (0~1)."},
        },
    )
