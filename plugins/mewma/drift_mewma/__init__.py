"""drift-mewma: MEWMA (Multivariate EWMA) drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import MewmaDetector

__version__ = "2.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "mewma",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/static",
    url_prefix="/drift/mewma",
)


@blueprint.route("/")
def page():
    return render_template(
        "mewma/page.html",
        plugin_name="MEWMA",
        plugin_key="mewma",
    )


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo
    from .web.routes import register_routes

    register_routes(blueprint)
    app.register_blueprint(blueprint)

    return PluginInfo(
        key="mewma",
        name="MEWMA",
        version=__version__,
        description="MEWMA 다변량 EWMA 기반 drift 탐지. Mahalanobis 거리로 고차원 분포 변화 감지.",
        category="statistical",
        card_template="mewma/card.html",
        page_url="/drift/mewma/",
        icon="chart-line",
        detector_class=MewmaDetector,
        supported_stream_types=["numeric_multivariate"],
        params_schema={
            "lambda_": {"type": "float", "default": 0.1, "label": "Lambda (λ)",
                        "description": "EWMA 평활 계수 (0.05~0.5). 작을수록 부드러움."},
            "alpha": {"type": "float", "default": 0.001, "label": "Alpha (α)",
                      "description": "유의수준. 작을수록 보수적 (UCL 높음)."},
            "baseline_points": {"type": "int", "default": 100, "label": "Baseline Points",
                                "description": "기준 구간 포인트 수 (μ0, Σ0 추정용)."},
        },
    )
