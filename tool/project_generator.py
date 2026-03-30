"""플러그인 프로젝트 생성기 — 템플릿에서 전체 디렉토리 구조를 만든다."""

import os
from pathlib import Path


TEMPLATES_DIR = Path(__file__).parent / "templates"


def generate_plugin_project(
    output_dir: str,
    key: str,
    plugin_name: str,
    description: str,
    category: str = "statistical",
    version: str = "1.0.0",
    author: str = "",
):
    """플러그인 프로젝트를 생성한다.

    Args:
        output_dir: 프로젝트를 생성할 디렉토리 경로
        key: 플러그인 key (예: "mewma")
        plugin_name: 표시 이름 (예: "MEWMA")
        description: 한 줄 설명
        category: "statistical" 또는 "llm"
        version: 초기 버전
        author: 작성자 이름
    """
    key_underscore = key.replace("-", "_")
    class_name = "".join(w.capitalize() for w in key.split("_")) + "Detector"
    pkg_name = f"drift_{key_underscore}"

    # 치환 변수
    context = {
        "key": key,
        "key_underscore": key_underscore,
        "plugin_name": plugin_name,
        "class_name": class_name,
        "description": description,
        "category": category,
        "version": version,
        "author": author,
        "pkg_name": pkg_name,
        # Jinja2 템플릿 안의 Jinja2 표현식용 (card.html)
        "plugin_name_jinja": "{{ plugin.name }}",
        "version_jinja": "{{ plugin.version }}",
        "description_jinja": "{{ plugin.description }}",
    }

    root = Path(output_dir)

    # 디렉토리 구조 생성
    dirs = [
        root,
        root / pkg_name,
        root / pkg_name / "web",
        root / pkg_name / "web" / "templates" / key,
        root / pkg_name / "web" / "static",
        root / pkg_name / "examples",
        root / "tests",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # 템플릿 파일 매핑: (템플릿 파일명, 출력 경로)
    file_map = [
        ("pyproject.toml.tmpl", root / "pyproject.toml"),
        ("init.py.tmpl", root / pkg_name / "__init__.py"),
        ("detector.py.tmpl", root / pkg_name / "detector.py"),
        ("routes.py.tmpl", root / pkg_name / "web" / "routes.py"),
        ("page.html.tmpl", root / pkg_name / "web" / "templates" / key / "page.html"),
        ("card.html.tmpl", root / pkg_name / "web" / "templates" / key / "card.html"),
        ("chart.js.tmpl", root / pkg_name / "web" / "static" / "chart.js"),
        ("style.css.tmpl", root / pkg_name / "web" / "static" / "style.css"),
    ]

    for tmpl_name, out_path in file_map:
        tmpl_path = TEMPLATES_DIR / tmpl_name
        content = tmpl_path.read_text(encoding="utf-8")

        # 치환 — [[var]] 형식 (Jinja2의 {{ }}와 충돌 방지)
        for var_name, var_value in context.items():
            content = content.replace("[[" + var_name + "]]", str(var_value))

        out_path.write_text(content, encoding="utf-8")

    # 빈 __init__.py 파일들
    (root / pkg_name / "web" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")

    # .gitkeep
    (root / pkg_name / "examples" / ".gitkeep").write_text("", encoding="utf-8")

    return root
