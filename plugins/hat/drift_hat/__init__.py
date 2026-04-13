"""drift-hat: ADWIN 기반 적응형 윈도우 drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import HatDetector
from .web.routes import register_routes

__version__ = "2.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "hat",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/static",
    url_prefix="/drift/hat",
)

register_routes(blueprint)


@blueprint.route("/")
def page():
    return render_template(
        "hat/page.html",
        plugin_name="HAT",
        plugin_key="hat",
    )


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="hat",
        name="HAT",
        version=__version__,
        description="ADWIN 기반 적응형 윈도우 drift 탐지. 값 스트림의 분포 변화를 감지하여 윈도우를 자동 축소.",
        category="statistical",
        card_template="hat/card.html",
        page_url="/drift/hat/",
        icon="tree",
        detector_class=HatDetector,
        params_schema={
            "delta": {"type": "float", "default": 0.002, "label": "Delta (ADWIN)",
                      "description": "ADWIN confidence 파라미터. 작을수록 보수적 (오탐 감소)."},
            "baseline_points": {"type": "int", "default": 30, "label": "Baseline Points",
                                "description": "초기 윈도우 구축용 기준 구간 포인트 수."},
        },
    )
