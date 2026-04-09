"""drift-hotelling: Hotelling T2 drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import HotellingDetector
from .web.routes import register_routes

__version__ = "2.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "hotelling",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/static",
    url_prefix="/drift/hotelling",
)

register_routes(blueprint)


@blueprint.route("/")
def page():
    return render_template(
        "hotelling/page.html",
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
        description="Hotelling T2 다변량 제어 차트 기반 drift 탐지 (shrinkage 정규화, chi2 임계값)",
        category="statistical",
        card_template="hotelling/card.html",
        page_url="/drift/hotelling/",
        icon="chart-bar",
        detector_class=HotellingDetector,
        params_schema={
            "alpha": {"type": "float", "default": 0.05, "label": "Alpha (α)",
                      "description": "유의수준 (0.05 = 95% 신뢰구간)"},
            "window_size": {"type": "int", "default": 50, "label": "Window Size",
                           "description": "슬라이딩 윈도우 크기"},
            "baseline_ratio": {"type": "float", "default": 0.5, "label": "Baseline Ratio",
                               "description": "전체 데이터 중 기준 구간 비율 (μ, σ² 추정용)"},
            "shrinkage": {"type": "float", "default": 0.01, "label": "Shrinkage",
                          "description": "공분산 정규화 계수 (수치 안정성). 0=정규화 없음, 1=단위 분산"},
        },
    )
