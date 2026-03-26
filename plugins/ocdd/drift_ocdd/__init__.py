"""drift-ocdd: One-Class Drift Detector plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import OcddDetector

__version__ = "1.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "ocdd",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    url_prefix="/drift/ocdd",
)


@blueprint.route("/")
def page():
    return render_template(
        "plugin_page.html",
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
        description="One-Class Drift Detector. 기준 분포의 통계량(평균, 표준편차)과 슬라이딩 윈도우를 비교하여 drift 탐지.",
        category="statistical",
        card_template="ocdd/card.html",
        page_url="/drift/ocdd/",
        icon="shield-alt",
        detector_class=OcddDetector,
        params_schema={
            "window_size": {"type": "int", "default": 50, "label": "Window Size", "description": "슬라이딩 윈도우 크기"},
            "reference_ratio": {"type": "float", "default": 0.5, "label": "Reference Ratio", "description": "기준 구간 비율."},
            "z_threshold": {"type": "float", "default": 3.0, "label": "Z Threshold", "description": "Z-score 임계값."},
        },
    )
