"""drift-hotelling: Hotelling T2 drift detection plugin."""

from pathlib import Path
from flask import Blueprint
from .detector import HotellingDetector

__version__ = "1.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "hotelling",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/hotelling-static",
    url_prefix="/drift/hotelling",
)

from .web.routes import register_routes  # noqa: E402
register_routes(blueprint)


def register(app):
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="hotelling",
        name="Hotelling T2",
        version=__version__,
        description=" Hotelling T2 제어 차트 기반 다변량 drift 탐지",
        category="statistical",
        card_template="hotelling/card.html",
        page_url="/drift/hotelling/",
        icon="chart-bar",
        detector_class=HotellingDetector,
        params_schema=HotellingDetector.DEFAULT_PARAMS,
    )
