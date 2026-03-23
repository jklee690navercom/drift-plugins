"""drift-imr-chart: I-MR Chart (Individual-Moving Range) drift detection plugin."""

from pathlib import Path
from flask import Blueprint
from .detector import ImrChartDetector

__version__ = "1.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "imr_chart",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/imr_chart-static",
    url_prefix="/drift/imr_chart",
)

from .web.routes import register_routes  # noqa: E402
register_routes(blueprint)


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
        example_data=_PKG_DIR / "examples" / "sample.csv",
        params_schema={
            "reference_ratio": {"type": "float", "default": 0.5, "label": "Reference Ratio", "description": "기준 구간 비율 (0~1). 전체 데이터에서 이 비율만큼을 기준 구간으로 사용."},
        },
    )
