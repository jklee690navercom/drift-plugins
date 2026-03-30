"""drift-cusum: CUSUM drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import CusumDetector

__version__ = "2.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "cusum",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    static_folder=str(_PKG_DIR / "web" / "static"),
    static_url_path="/static",
    url_prefix="/drift/cusum",
)


@blueprint.route("/")
def page():
    return render_template(
        "cusum/page.html",
        plugin_name="CUSUM",
        plugin_key="cusum",
    )


def register(app):
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="cusum",
        name="CUSUM",
        version=__version__,
        description="누적합(CUSUM) 기반 변화점 탐지. 평균의 점진적 이동에 민감. Baseline 분리, FIR 지원.",
        category="statistical",
        card_template="cusum/card.html",
        page_url="/drift/cusum/",
        icon="chart-line",
        detector_class=CusumDetector,
        params_schema={
            "k": {"type": "float", "default": 0.25, "label": "Slack (k)",
                   "description": "허용 편차. 감지할 변화량 δ의 절반 (k=δ/2)"},
            "h": {"type": "float", "default": 5.0, "label": "Threshold (h)",
                   "description": "알람 임계값. 작을수록 빠른 감지, 클수록 안정적"},
            "baseline_ratio": {"type": "float", "default": 0.5, "label": "Baseline Ratio",
                               "description": "기준 구간 비율. 이 구간에서 μ0, σ0를 계산"},
            "robust": {"type": "bool", "default": True, "label": "Robust Standardization",
                       "description": "True: median/MAD, False: mean/std"},
        },
    )
