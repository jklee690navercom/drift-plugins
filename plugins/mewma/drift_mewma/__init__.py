"""drift-mewma: MEWMA (Multivariate EWMA) drift detection plugin."""

from pathlib import Path
from flask import Blueprint
from .detector import MewmaDetector

__version__ = "1.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "mewma",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/mewma-static",
    url_prefix="/drift/mewma",
)

from .web.routes import register_routes  # noqa: E402
register_routes(blueprint)


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="mewma",
        name="MEWMA",
        version=__version__,
        description="MEWMA(Multivariate EWMA) 기반 drift 탐지. EWMA 평활화 후 이탈도를 측정.",
        category="statistical",
        card_template="mewma/card.html",
        page_url="/drift/mewma/",
        icon="chart-line",
        detector_class=MewmaDetector,
        example_data=_PKG_DIR / "examples" / "sample.csv",
        params_schema={
            "lambda_": {"type": "float", "default": 0.1, "label": "Lambda", "description": "EWMA 평활 계수. 작을수록 과거 가중치 높음."},
            "reference_ratio": {"type": "float", "default": 0.5, "label": "Reference Ratio", "description": "기준 구간 비율."},
            "alpha": {"type": "float", "default": 0.01, "label": "Alpha", "description": "유의수준. 작을수록 보수적."},
        },
    )
