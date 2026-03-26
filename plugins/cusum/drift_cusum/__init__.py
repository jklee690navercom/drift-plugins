"""drift-cusum: CUSUM drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import CusumDetector

__version__ = "1.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "cusum",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    url_prefix="/drift/cusum",
)


@blueprint.route("/")
def page():
    return render_template(
        "plugin_page.html",
        plugin_name="CUSUM",
        plugin_key="cusum",
    )


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="cusum",
        name="CUSUM",
        version=__version__,
        description="누적합(CUSUM) 기반 변화점 탐지. 평균의 점진적 이동에 민감.",
        category="statistical",
        card_template="cusum/card.html",
        page_url="/drift/cusum/",
        icon="chart-line",
        detector_class=CusumDetector,
        params_schema={
            "k": {"type": "float", "default": 0.25, "label": "Slack (k)"},
            "h": {"type": "float", "default": 5.0, "label": "Threshold (h)"},
        },
    )
