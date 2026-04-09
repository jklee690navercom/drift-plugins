"""drift-ocdd: One-Class Drift Detector plugin (IQR-based) v2.0."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import OcddDetector
from .web.routes import register_routes

__version__ = "2.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "ocdd",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/static",
    url_prefix="/drift/ocdd",
)

register_routes(blueprint)


@blueprint.route("/")
def page():
    return render_template(
        "ocdd/page.html",
        plugin_name="OCDD",
        plugin_key="ocdd",
    )


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="ocdd",
        name="OCDD",
        version=__version__,
        description="One-Class Drift Detector (IQR 기반). Baseline의 IQR로 outlier를 판별하고, 슬라이딩 윈도우 내 outlier 비율이 임계값을 초과하면 drift 탐지.",
        category="statistical",
        card_template="ocdd/card.html",
        page_url="/drift/ocdd/",
        icon="shield-alt",
        detector_class=OcddDetector,
        params_schema={
            "window_size": {"type": "int", "default": 100, "label": "Window Size",
                            "description": "슬라이딩 윈도우 크기 (outlier ratio 계산용)"},
            "rho": {"type": "float", "default": 0.3, "label": "Rho (rho)",
                    "description": "outlier 비율 임계값. 이 비율 이상이면 drift 감지."},
            "baseline_ratio": {"type": "float", "default": 0.3333, "label": "Baseline Ratio",
                               "description": "IQR 계산을 위한 기준 구간 비율."},
        },
    )
