"""drift-hotelling: Hotelling T2 drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import HotellingDetector

__version__ = "1.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "hotelling",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    url_prefix="/drift/hotelling",
)


@blueprint.route("/")
def page():
    return render_template(
        "plugin_page.html",
        plugin_name="Hotelling T2",
        plugin_key="hotelling",
    )


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="hotelling",
        name="Hotelling T2",
        version=__version__,
        description="Hotelling T2 다변량 제어 차트 기반 drift 탐지",
        category="statistical",
        card_template="hotelling/card.html",
        page_url="/drift/hotelling/",
        icon="chart-bar",
        detector_class=HotellingDetector,
        params_schema={
            "alpha": {"type": "float", "default": 0.01, "label": "Alpha", "description": "유의수준 (0.01 = 99% 신뢰구간)"},
            "window_size": {"type": "int", "default": 50, "label": "Window Size", "description": "슬라이딩 윈도우 크기"},
            "reference_ratio": {"type": "float", "default": 0.5, "label": "Reference Ratio", "description": "전체 데이터 중 기준 구간 비율"},
        },
    )
