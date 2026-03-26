"""drift-hat: Hoeffding Adaptive Tree inspired drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import HatDetector

__version__ = "1.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "hat",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    url_prefix="/drift/hat",
)


@blueprint.route("/")
def page():
    return render_template(
        "plugin_page.html",
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
        description="Hoeffding Adaptive Tree 기반 ADWIN-like drift 탐지. 두 윈도우의 평균 차이를 Hoeffding bound로 판단.",
        category="statistical",
        card_template="hat/card.html",
        page_url="/drift/hat/",
        icon="tree",
        detector_class=HatDetector,
        params_schema={
            "min_window": {"type": "int", "default": 30, "label": "Min Window", "description": "최소 윈도우 크기"},
            "delta": {"type": "float", "default": 0.01, "label": "Delta", "description": "Hoeffding bound confidence."},
            "reference_ratio": {"type": "float", "default": 0.5, "label": "Reference Ratio", "description": "기준 구간 비율."},
        },
    )
