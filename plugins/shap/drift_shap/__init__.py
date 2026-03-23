"""drift-shap: Feature importance change drift detection plugin."""

from pathlib import Path
from flask import Blueprint
from .detector import ShapDetector

__version__ = "1.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "shap",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/shap-static",
    url_prefix="/drift/shap",
)

from .web.routes import register_routes  # noqa: E402
register_routes(blueprint)


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="shap",
        name="SHAP Drift",
        version=__version__,
        description="Feature importance 변화 기반 drift 탐지. Rolling statistics를 feature로 사용하여 분포 변화를 감지.",
        category="statistical",
        card_template="shap/card.html",
        page_url="/drift/shap/",
        icon="project-diagram",
        detector_class=ShapDetector,
        example_data=_PKG_DIR / "examples" / "sample.csv",
        params_schema={
            "window_size": {"type": "int", "default": 50, "label": "Window Size", "description": "슬라이딩 윈도우 크기"},
            "reference_ratio": {"type": "float", "default": 0.5, "label": "Reference Ratio", "description": "기준 구간 비율."},
            "alpha": {"type": "float", "default": 0.05, "label": "Alpha", "description": "유의수준."},
        },
    )
