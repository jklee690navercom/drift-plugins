"""drift-ks-test: Kolmogorov-Smirnov test drift detection plugin."""

from pathlib import Path

from flask import Blueprint, render_template

from .detector import KsTestDetector

__version__ = "2.0.0"

_PKG_DIR = Path(__file__).resolve().parent

blueprint = Blueprint(
    "ks_test",
    __name__,
    template_folder=str(_PKG_DIR / "web" / "templates"),
    url_prefix="/drift/ks_test",
)


@blueprint.route("/")
def page():
    return render_template(
        "plugin_page.html",
        plugin_name="KS Test",
        plugin_key="ks_test",
    )


def register(app):
    """프레임워크가 호출하는 유일한 진입점."""
    from framework.plugin.types import PluginInfo

    app.register_blueprint(blueprint)

    return PluginInfo(
        key="ks_test",
        name="KS Test",
        version=__version__,
        description="Kolmogorov-Smirnov 검정 기반 분포 변화 탐지. 다중 검정 보정, 기준 갱신, 이상치 처리 지원.",
        category="statistical",
        card_template="ks_test/card.html",
        page_url="/drift/ks_test/",
        icon="chart-area",
        detector_class=KsTestDetector,
        params_schema={
            "window_size": {"type": "int", "default": 100, "label": "Window Size",
                            "description": "비교할 슬라이딩 윈도우 크기 (n>=100 권장)"},
            "alpha": {"type": "float", "default": 0.05, "label": "Alpha",
                      "description": "유의수준. 작을수록 보수적."},
            "reference_ratio": {"type": "float", "default": 0.5, "label": "Reference Ratio",
                                "description": "전체 데이터에서 기준 구간의 비율."},
            "correction": {"type": "str", "default": "bh", "label": "Correction",
                           "description": "다중 검정 보정: none, bonferroni, bh",
                           "options": ["none", "bonferroni", "bh"]},
            "update_reference": {"type": "bool", "default": True, "label": "Update Reference",
                                 "description": "drift 탐지 후 기준 윈도우 갱신"},
            "remove_outliers": {"type": "bool", "default": False, "label": "Remove Outliers",
                                "description": "IQR 기반 이상치 제거"},
            "method": {"type": "str", "default": "asymptotic", "label": "Method",
                       "description": "검정 방법: asymptotic, exact, bootstrap",
                       "options": ["asymptotic", "exact", "bootstrap"]},
        },
    )
