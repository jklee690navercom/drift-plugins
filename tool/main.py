"""Drift Plugin Developer Tool — PyQt6 메인 윈도우."""

import os
import sys
import subprocess
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QTabWidget, QToolBar,
    QDockWidget, QPlainTextEdit, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QPushButton, QTreeView, QListWidget, QListWidgetItem,
    QFormLayout, QLineEdit, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QMessageBox, QGroupBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QModelIndex
from PyQt6.QtGui import (
    QAction, QFont, QFileSystemModel, QSyntaxHighlighter,
    QTextCharFormat, QColor,
)


# ═══════════════════════════════════════
# 프로젝트 생성 다이얼로그
# ═══════════════════════════════════════

class NewPluginDialog(QDialog):
    """새 플러그인 프로젝트 생성 다이얼로그."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Plugin")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("mewma")
        form.addRow("Plugin Key:", self.key_edit)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("MEWMA")
        form.addRow("Display Name:", self.name_edit)

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("다변량 EWMA 기반 drift 탐지")
        form.addRow("Description:", self.desc_edit)

        self.category_combo = QComboBox()
        self.category_combo.addItems(["statistical", "llm"])
        form.addRow("Category:", self.category_combo)

        self.version_edit = QLineEdit("1.0.0")
        form.addRow("Version:", self.version_edit)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("C:\\dev\\drift-mewma")
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit)
        browse_btn = QPushButton("...")
        browse_btn.setMaximumWidth(40)
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)
        form.addRow("Output Path:", path_row)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            key = self.key_edit.text() or "new_plugin"
            self.path_edit.setText(str(Path(path) / f"drift-{key}"))

    def _validate_and_accept(self):
        if not self.key_edit.text():
            QMessageBox.warning(self, "Error", "Plugin Key를 입력하세요.")
            return
        if not self.name_edit.text():
            QMessageBox.warning(self, "Error", "Display Name을 입력하세요.")
            return
        if not self.path_edit.text():
            QMessageBox.warning(self, "Error", "Output Path를 선택하세요.")
            return
        self.accept()

    def get_values(self) -> dict:
        return {
            "key": self.key_edit.text(),
            "plugin_name": self.name_edit.text(),
            "description": self.desc_edit.text(),
            "category": self.category_combo.currentText(),
            "version": self.version_edit.text(),
            "output_dir": self.path_edit.text(),
        }


# ═══════════════════════════════════════
# STEP 편집 다이얼로그
# ═══════════════════════════════════════

class StepEditorDialog(QDialog):
    """STEP 예제 코드를 보여주고 수정 후 삽입하는 다이얼로그."""

    def __init__(self, title: str, description: str, example_code: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        # 설명
        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("QLabel { background: #f0f9ff; padding: 12px; border-radius: 6px; "
                                 "border: 1px solid #bae6fd; font-size: 13px; line-height: 1.6; }")
        layout.addWidget(desc_label)

        # 코드 편집기
        layout.addWidget(QLabel("예제 코드 (수정 후 '삽입' 클릭):"))
        self.code_edit = QPlainTextEdit()
        self.code_edit.setFont(QFont("Consolas", 11))
        self.code_edit.setTabStopDistance(40)
        self.code_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.code_edit.setPlainText(example_code)
        self.code_edit.setStyleSheet(
            "QPlainTextEdit { background: #1e293b; color: #e2e8f0; "
            "border-radius: 6px; padding: 8px; }")
        layout.addWidget(self.code_edit)

        # 버튼
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        insert_btn = QPushButton("삽입")
        insert_btn.setStyleSheet("QPushButton { background: #3b82f6; color: white; "
                                 "padding: 8px 24px; border-radius: 6px; border: none; font-weight: bold; }")
        insert_btn.clicked.connect(self.accept)
        btn_layout.addWidget(insert_btn)

        layout.addLayout(btn_layout)

    def get_code(self) -> str:
        return self.code_edit.toPlainText()


# ═══════════════════════════════════════
# 구문 강조
# ═══════════════════════════════════════

class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        from PyQt6.QtCore import QRegularExpression
        self._rules = []

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#0000FF"))
        kw_fmt.setFontWeight(QFont.Weight.Bold)
        for kw in ["class", "def", "return", "if", "elif", "else", "for", "while",
                    "import", "from", "as", "try", "except", "with", "True", "False",
                    "None", "and", "or", "not", "in", "is", "self", "lambda", "raise"]:
            self._rules.append((QRegularExpression(rf"\b{kw}\b"), kw_fmt))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#008000"))
        self._rules.append((QRegularExpression(r'"[^"]*"'), str_fmt))
        self._rules.append((QRegularExpression(r"'[^']*'"), str_fmt))

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#808080"))
        self._rules.append((QRegularExpression(r"#.*$"), comment_fmt))

        step_fmt = QTextCharFormat()
        step_fmt.setBackground(QColor("#FFFFCC"))
        step_fmt.setFontWeight(QFont.Weight.Bold)
        self._rules.append((QRegularExpression(r"# [▼▲╔║╚═].*$"), step_fmt))

    def highlightBlock(self, text):
        from PyQt6.QtCore import QRegularExpression
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


# ═══════════════════════════════════════
# 검증기
# ═══════════════════════════════════════

class PluginValidator:
    def validate(self, project_path: Path) -> list[tuple[bool, str, str]]:
        results = []
        if not project_path or not project_path.exists():
            return [(False, "프로젝트 경로가 존재하지 않습니다.", "error")]

        # pyproject.toml
        toml = project_path / "pyproject.toml"
        if toml.exists():
            content = toml.read_text(encoding="utf-8")
            if "drift_framework.plugins" in content:
                results.append((True, "✓ pyproject.toml entry_points 확인", "info"))
            else:
                results.append((False, "✗ pyproject.toml에 entry_points 누락", "error"))
            if "drift-framework" in content:
                results.append((True, "✓ drift-framework 의존성 확인", "info"))
            else:
                results.append((False, "✗ drift-framework 의존성 누락", "error"))
        else:
            results.append((False, "✗ pyproject.toml 없음", "error"))

        # 패키지 디렉토리 찾기
        pkg_dirs = [d for d in project_path.iterdir()
                    if d.is_dir() and d.name.startswith("drift_") and (d / "__init__.py").exists()]
        if pkg_dirs:
            pkg = pkg_dirs[0]
            results.append((True, f"✓ 패키지 디렉토리: {pkg.name}/", "info"))

            # __init__.py
            init = (pkg / "__init__.py").read_text(encoding="utf-8")
            if "def register(" in init:
                results.append((True, "✓ register() 함수 확인", "info"))
            else:
                results.append((False, "✗ __init__.py에 register() 없음", "error"))

            # detector.py
            det = pkg / "detector.py"
            if det.exists():
                det_content = det.read_text(encoding="utf-8")
                if "DriftDetector" in det_content:
                    results.append((True, "✓ DriftDetector 상속 확인", "info"))
                else:
                    results.append((False, "✗ DriftDetector 상속 없음", "error"))
                if "def detect(" in det_content:
                    results.append((True, "✓ detect() 메서드 확인", "info"))
                else:
                    results.append((False, "✗ detect() 메서드 없음", "error"))
                if "▼▼▼" in det_content:
                    results.append((True, "⚠ STEP 2 구현 영역에 TODO가 남아있음", "warning"))
            else:
                results.append((False, "✗ detector.py 없음", "error"))

            # routes.py
            routes = pkg / "web" / "routes.py"
            if routes.exists():
                results.append((True, "✓ web/routes.py 확인", "info"))
            else:
                results.append((False, "✗ web/routes.py 없음", "error"))

            # templates
            tmpl_dir = pkg / "web" / "templates"
            if tmpl_dir.exists() and any(tmpl_dir.rglob("page.html")):
                results.append((True, "✓ page.html 확인", "info"))
            else:
                results.append((False, "✗ page.html 없음", "error"))
        else:
            results.append((False, "✗ drift_* 패키지 디렉토리 없음", "error"))

        return results


# ═══════════════════════════════════════
# 메인 윈도우
# ═══════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drift Plugin Developer Tool")
        self.resize(1400, 900)
        self.project_path: Path | None = None
        self.validator = PluginValidator()

        self._create_toolbar()
        self._create_panels()
        self._create_log_dock()
        self.statusBar().showMessage("Ready — File → New Plugin으로 시작하세요.")

    def _create_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction(self._action("New Plugin", self.on_new_plugin))
        toolbar.addAction(self._action("Open Project", self.on_open_project))
        toolbar.addAction(self._action("Save", self.on_save))
        toolbar.addSeparator()
        toolbar.addAction(self._action("Validate", self.on_validate))
        toolbar.addAction(self._action("Test", self.on_test))
        toolbar.addAction(self._action("Preview", self.on_preview))
        toolbar.addSeparator()
        toolbar.addAction(self._action("Register to GitHub", self.on_register))

    def _action(self, text, slot):
        a = QAction(text, self)
        a.triggered.connect(slot)
        return a

    def _create_panels(self):
        # 좌측: 파일 탐색기
        self.file_model = QFileSystemModel()
        self.file_model.setNameFilters(["*.py", "*.html", "*.js", "*.css", "*.toml", "*.yaml", "*.md"])
        self.file_model.setNameFilterDisables(False)
        self.tree = QTreeView()
        self.tree.setModel(self.file_model)
        self.tree.hideColumn(1)
        self.tree.hideColumn(2)
        self.tree.hideColumn(3)
        self.tree.setHeaderHidden(True)
        self.tree.clicked.connect(self._on_file_clicked)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.project_label = QLabel("No project open")
        left_layout.addWidget(self.project_label)
        left_layout.addWidget(self.tree)

        # 중앙: 코드 편집기
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.tabCloseRequested.connect(lambda i: self.editor_tabs.removeTab(i))
        self._open_files: dict[str, QPlainTextEdit] = {}

        # 우측: 속성 + 검증 + 액션
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(5, 5, 5, 5)

        # 속성
        info_group = QGroupBox("Plugin Info")
        info_layout = QFormLayout()
        self.info_key = QLabel("-")
        self.info_version = QLabel("-")
        self.info_category = QLabel("-")
        info_layout.addRow("Key:", self.info_key)
        info_layout.addRow("Version:", self.info_version)
        info_layout.addRow("Category:", self.info_category)
        info_group.setLayout(info_layout)
        right_layout.addWidget(info_group)

        # 검증
        valid_group = QGroupBox("Validation")
        valid_layout = QVBoxLayout()
        self.valid_list = QListWidget()
        valid_layout.addWidget(self.valid_list)
        valid_group.setLayout(valid_layout)
        right_layout.addWidget(valid_group)

        # 구현 가이드
        guide_group = QGroupBox("Implementation Guide")
        guide_layout = QVBoxLayout()
        self.guide_text = QLabel()
        self.guide_text.setWordWrap(True)
        self.guide_text.setStyleSheet("QLabel { font-size: 12px; line-height: 1.5; color: #334155; }")
        self.guide_text.setTextFormat(Qt.TextFormat.RichText)
        self.guide_text.setOpenExternalLinks(False)
        self.guide_text.linkActivated.connect(self._on_guide_link)
        guide_layout.addWidget(self.guide_text)
        guide_group.setLayout(guide_layout)
        right_layout.addWidget(guide_group)

        # 액션
        action_group = QGroupBox("Actions")
        action_layout = QVBoxLayout()
        for text, slot in [("Run Tests", self.on_test), ("Preview in Browser", self.on_preview),
                           ("Register to GitHub", self.on_register)]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            action_layout.addWidget(btn)
        action_group.setLayout(action_layout)
        right_layout.addWidget(action_group)
        right_layout.addStretch()

        # 스플리터
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.editor_tabs)
        splitter.addWidget(right)
        splitter.setSizes([250, 850, 300])
        self.setCentralWidget(splitter)

    def _create_log_dock(self):
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setMaximumHeight(150)
        dock = QDockWidget("Log", self)
        dock.setWidget(self.log_text)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

    # ── 파일 탐색기 ──

    def _on_file_clicked(self, index: QModelIndex):
        path = self.file_model.filePath(index)
        if Path(path).is_file():
            self._open_file(path)

    def _open_file(self, file_path: str):
        if file_path in self._open_files:
            self.editor_tabs.setCurrentWidget(self._open_files[file_path])
            return

        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        editor = QPlainTextEdit()
        editor.setFont(QFont("Consolas", 11))
        editor.setTabStopDistance(40)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        editor.setPlainText(content)
        editor.setProperty("file_path", file_path)

        # Python 구문 강조
        if file_path.endswith(".py"):
            PythonHighlighter(editor.document())

        tab_name = Path(file_path).name
        self.editor_tabs.addTab(editor, tab_name)
        self.editor_tabs.setCurrentWidget(editor)
        self._open_files[file_path] = editor

    # ── 프로젝트 열기 ──

    def _set_project(self, path: Path):
        self.project_path = path
        self.project_label.setText(f"Project: {path.name}")
        self.file_model.setRootPath(str(path))
        self.tree.setRootIndex(self.file_model.index(str(path)))
        self._update_info()
        self.on_validate()

    def _update_info(self):
        if not self.project_path:
            return
        toml_path = self.project_path / "pyproject.toml"
        if toml_path.exists():
            import tomllib
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
            project = data.get("project", {})
            self.info_version.setText(project.get("version", "-"))
            eps = project.get("entry-points", {}).get("drift_framework.plugins", {})
            if eps:
                self.info_key.setText(list(eps.keys())[0])
            self.info_category.setText("statistical")

    # ── 슬롯 ──

    def on_new_plugin(self):
        dialog = NewPluginDialog(self)
        if dialog.exec():
            values = dialog.get_values()
            from .project_generator import generate_plugin_project
            try:
                path = generate_plugin_project(
                    output_dir=values["output_dir"],
                    key=values["key"],
                    plugin_name=values["plugin_name"],
                    description=values["description"],
                    category=values["category"],
                    version=values["version"],
                )
                self._set_project(path)
                self.log(f"✓ 프로젝트 생성 완료: {path}")

                # detector.py 자동 열기
                pkg_name = f"drift_{values['key'].replace('-', '_')}"
                detector_path = path / pkg_name / "detector.py"
                if detector_path.exists():
                    self._open_file(str(detector_path))

            except Exception as e:
                QMessageBox.critical(self, "Error", f"프로젝트 생성 실패:\n{e}")

    def on_open_project(self):
        path = QFileDialog.getExistingDirectory(self, "Open Plugin Project")
        if path:
            self._set_project(Path(path))
            self.log(f"✓ 프로젝트 열기: {path}")

    def on_save(self):
        editor = self.editor_tabs.currentWidget()
        if not editor:
            return
        file_path = editor.property("file_path")
        if not file_path:
            return
        Path(file_path).write_text(editor.toPlainText(), encoding="utf-8")
        self.log(f"✓ 저장: {Path(file_path).name}")
        self.on_validate()

    def on_validate(self):
        if not self.project_path:
            return
        results = self.validator.validate(self.project_path)
        self.valid_list.clear()
        for passed, msg, severity in results:
            item = QListWidgetItem(msg)
            if severity == "error":
                item.setForeground(QColor("#CC0000"))
            elif severity == "warning":
                item.setForeground(QColor("#CC8800"))
            else:
                item.setForeground(QColor("#008800"))
            self.valid_list.addItem(item)
        self._update_guide(results)

    def _update_guide(self, validation_results):
        """검증 결과를 분석하여 다음에 할 일을 안내한다."""
        if not self.project_path:
            self.guide_text.setText("New Plugin으로 프로젝트를 생성하세요.")
            return

        errors = [r for r in validation_results if r[2] == "error"]
        warnings = [r for r in validation_results if r[2] == "warning"]
        has_todo = any("TODO" in r[1] or "STEP" in r[1] for r in warnings)

        if errors:
            guide = "<b style='color:#dc2626;'>구조 오류가 있습니다:</b><br><br>"
            for _, msg, _ in errors:
                guide += f"• {msg}<br>"
            guide += "<br>위 오류를 먼저 해결하세요."
            self.guide_text.setText(guide)
            return

        if has_todo:
            guide = (
                "<b>다음 단계: 알고리즘 구현</b><br><br>"
                "아래 버튼을 클릭하면 <b>예제 코드</b>가 열립니다.<br>"
                "예제를 수정하여 <b>삽입</b>하세요.<br><br>"
                "<a href='action:step1' style='display:inline-block;padding:8px 16px;"
                "background:#3b82f6;color:white;border-radius:6px;"
                "text-decoration:none;margin-bottom:8px;'>STEP 1: 파라미터 정의</a><br><br>"
                "<a href='action:step2' style='display:inline-block;padding:8px 16px;"
                "background:#8b5cf6;color:white;border-radius:6px;"
                "text-decoration:none;margin-bottom:8px;'>STEP 2: 알고리즘 구현</a><br><br>"
                "<hr>"
                "<b>삽입 후:</b><br>"
                "1. <b>Save</b> → 자동 검증<br>"
                "2. <a href='action:test'>Test</a> → 설치 확인<br>"
                "3. <a href='action:preview'>Preview</a> → 브라우저 확인<br>"
                "4. <a href='action:register'>Register</a> → GitHub 등록<br>"
            )
            self.guide_text.setText(guide)
            return

        guide = (
            "<b style='color:#16a34a;'>구조 검증 통과!</b><br><br>"
            "<b>다음 단계:</b><br>"
            "1. <a href='action:test'>Test</a> — 설치 확인<br>"
            "2. <a href='action:preview'>Preview</a> — 브라우저 확인<br>"
            "3. <a href='action:register'>Register</a> — GitHub 등록<br><br>"
            "<b>선택:</b><br>"
            "• <a href='open:page.html'>page.html</a> — 차트 커스터마이징<br>"
            "• <a href='open:chart.js'>chart.js</a> — 차트 JS 구현<br>"
        )
        self.guide_text.setText(guide)

    def _on_guide_link(self, link: str):
        """가이드 패널의 링크 클릭 핸들러."""
        if link.startswith("open:"):
            self._open_file_by_name(link.replace("open:", ""))
        elif link == "action:step1":
            self._show_step_dialog("step1")
        elif link == "action:step2":
            self._show_step_dialog("step2")
        elif link == "action:test":
            self.on_test()
        elif link == "action:preview":
            self.on_preview()
        elif link == "action:register":
            self.on_register()

    def _show_step_dialog(self, step: str):
        """STEP 예제 코드를 보여주고 수정 후 삽입하는 다이얼로그."""
        if not self.project_path:
            return

        plugin_name = self.info_key.text()

        if step == "step1":
            title = "STEP 1: 파라미터 정의"
            description = (
                "이 알고리즘이 사용자로부터 받을 파라미터를 정의합니다.\n"
                "여기서 정의한 파라미터는 웹 UI에서 사용자가 값을 변경할 수 있습니다.\n\n"
                "[작성 규칙]\n"
                "• dict 형태로 '파라미터명': 기본값 을 나열합니다.\n"
                "• # 주석으로 파라미터의 의미를 설명합니다.\n"
                "• 이 파라미터들은 STEP 2에서 params['파라미터명']으로 사용합니다.\n\n"
                "[예시]\n"
                "• CUSUM: k(허용편차), h(임계값)\n"
                "• KS Test: alpha(유의수준), window_size(윈도우크기)\n"
                "• 아래 예제를 이 알고리즘에 맞게 수정하세요."
            )
            example = (
                '    DEFAULT_PARAMS = {\n'
                '        "alpha": 0.01,           # 유의수준 (0.01 = 99% 신뢰구간)\n'
                '        "window_size": 50,        # 슬라이딩 윈도우 크기\n'
                '        "reference_ratio": 0.5,   # 전체 데이터 중 기준 구간 비율\n'
                '    }'
            )
            marker_start = "DEFAULT_PARAMS = {"
            marker_end = "    }"
        else:
            title = "STEP 2: 알고리즘 구현"
            description = (
                "[이 코드의 역할]\n"
                "시계열 숫자 데이터에서 '이상(drift)'을 찾는 알고리즘을 구현합니다.\n\n"
                "[중요: 데이터 특성을 몰라도 됩니다]\n"
                "이 알고리즘은 범용 숫자 시계열을 받습니다.\n"
                "value가 confidence score인지, 온도인지, 에러율인지 모릅니다.\n"
                "순수하게 '숫자 패턴의 이상'만 찾으면 됩니다.\n"
                "데이터의 의미 해석은 프레임워크의 다른 계층이 담당합니다.\n\n"
                "[사용 가능한 입력 — 이미 준비되어 있음]\n"
                "• series     — numpy 배열 (예: [0.91, 0.88, 0.73, ...])\n"
                "• params     — STEP 1에서 정의한 파라미터 dict\n"
                "• timestamps — pandas 시간 인덱스\n"
                "• np         — numpy 라이브러리 (import 됨)\n\n"
                "[채워야 할 출력 — 4개 변수]\n"
                "• alarm_indices — 이상 포인트의 인덱스 리스트\n"
                "                  예: [150, 151, 152, 180, 181]\n"
                "                  빈 리스트면 '이상 없음'으로 처리됨\n"
                "• score         — 이상의 강도 (실수)\n"
                "                  1.0 이상이면 warning, 2.0 이상이면 critical\n"
                "• message       — 사람이 읽을 한 줄 요약 문자열\n"
                "                  예: 'T2=15.2, threshold=9.21'\n"
                "• detail        — 알고리즘 고유 결과 dict\n"
                "                  UI 차트에서 사용할 데이터를 넣으세요\n"
                "                  예: {'t2_series': [...], 'threshold': 9.21}\n\n"
                "[일반적인 구현 패턴]\n"
                "1. 데이터를 기준 구간(reference)과 테스트 구간으로 나눔\n"
                "2. 기준 구간에서 통계량(평균, 분산 등)을 계산\n"
                "3. 테스트 구간의 각 포인트/윈도우에서 이상 여부를 판정\n"
                "4. 임계값을 넘는 포인트를 alarm_indices에 추가\n\n"
                "아래 예제(Hotelling T²)를 참고하여 수정하세요."
            )
            example = (
                '        alarm_indices = []\n'
                '        score = 0.0\n'
                '        message = ""\n'
                '        detail = {}\n'
                '\n'
                '        alpha = params["alpha"]\n'
                '        window_size = int(params["window_size"])\n'
                '        ref_ratio = params["reference_ratio"]\n'
                '\n'
                '        # 기준 구간 분리\n'
                '        ref_end = int(len(series) * ref_ratio)\n'
                '        reference = series[:ref_end]\n'
                '        ref_mean = np.mean(reference)\n'
                '        ref_std = np.std(reference, ddof=1)\n'
                '        if ref_std <= 0:\n'
                '            ref_std = 1e-8\n'
                '\n'
                '        # T2 통계량 계산\n'
                '        from scipy.stats import chi2\n'
                '        threshold = chi2.ppf(1 - alpha, df=1)\n'
                '\n'
                '        t2_values = np.zeros(len(series))\n'
                '        for i in range(ref_end, len(series)):\n'
                '            z = (series[i] - ref_mean) / ref_std\n'
                '            t2 = z ** 2\n'
                '            t2_values[i] = t2\n'
                '            if t2 > threshold:\n'
                '                alarm_indices.append(i)\n'
                '\n'
                '        if alarm_indices:\n'
                '            peak_idx = alarm_indices[np.argmax(t2_values[alarm_indices])]\n'
                '            score = float(t2_values[peak_idx] / threshold)\n'
                '            message = f"Hotelling T2={t2_values[peak_idx]:.2f}, threshold={threshold:.2f}"\n'
                '            detail = {\n'
                '                "algorithm": "hotelling_t2",\n'
                '                "threshold": round(threshold, 4),\n'
                '                "alpha": alpha,\n'
                '                "ref_mean": round(float(ref_mean), 4),\n'
                '                "ref_std": round(float(ref_std), 4),\n'
                '                "t2_series": t2_values.tolist(),\n'
                '                "alarm_mask": [1 if i in alarm_indices else 0 for i in range(len(series))],\n'
                '            }'
            )
            marker_start = "# ▼▼▼"
            marker_end = "# ▲▲▲"

        dialog = StepEditorDialog(title, description, example, self)
        if dialog.exec():
            edited_code = dialog.get_code()
            self._insert_code_into_detector(step, edited_code, marker_start, marker_end)

    def _insert_code_into_detector(self, step, code, marker_start, marker_end):
        """편집된 코드를 detector.py의 해당 영역에 삽입한다."""
        detector_path = None
        for f in self.project_path.rglob("detector.py"):
            detector_path = f
            break
        if not detector_path:
            self.log("✗ detector.py를 찾을 수 없음")
            return

        content = detector_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        if step == "step1":
            # DEFAULT_PARAMS 영역 교체
            new_lines = []
            skip = False
            for line in lines:
                if "DEFAULT_PARAMS = {" in line:
                    # 새 코드 삽입
                    for code_line in code.split("\n"):
                        new_lines.append(code_line)
                    skip = True
                    continue
                if skip:
                    if line.strip() == "}" or (line.strip().endswith("}") and "DEFAULT_PARAMS" not in line):
                        skip = False
                        continue
                    continue
                new_lines.append(line)
            content = "\n".join(new_lines)

        elif step == "step2":
            # ▼▼▼ ~ ▲▲▲ 영역 교체
            new_lines = []
            skip = False
            for line in lines:
                if "# ▼▼▼" in line:
                    new_lines.append(line)
                    new_lines.append("")
                    for code_line in code.split("\n"):
                        new_lines.append(code_line)
                    new_lines.append("")
                    skip = True
                    continue
                if skip:
                    if "# ▲▲▲" in line:
                        new_lines.append(line)
                        skip = False
                    continue
                new_lines.append(line)
            content = "\n".join(new_lines)

        detector_path.write_text(content, encoding="utf-8")
        self.log(f"✓ {step} 코드 삽입 완료 → detector.py")

        # 편집기에 열려있으면 갱신
        str_path = str(detector_path)
        if str_path in self._open_files:
            self._open_files[str_path].setPlainText(content)

        self.on_validate()

    def _open_file_by_name(self, filename: str):
        """프로젝트 내에서 파일명으로 검색하여 열기."""
        if not self.project_path:
            return
        matches = list(self.project_path.rglob(filename))
        if matches:
            self._open_file(str(matches[0]))
        else:
            self.log(f"파일을 찾을 수 없음: {filename}")

    def on_test(self):
        if not self.project_path:
            QMessageBox.warning(self, "Error", "프로젝트를 먼저 여세요.")
            return
        self.log("테스트 실행 중...")
        # pip install -e 로 설치 후 import 테스트
        result = subprocess.run(
            ["pip", "install", "-e", str(self.project_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            self.log(f"✗ pip install -e 실패:\n{result.stderr}")
            return
        self.log("✓ pip install -e 성공")

        # entry_points 확인
        result = subprocess.run(
            [sys.executable, "-c",
             "from importlib.metadata import entry_points;"
             "eps = entry_points(group='drift_framework.plugins');"
             f"print([ep.name for ep in eps])"],
            capture_output=True, text=True,
        )
        self.log(f"✓ entry_points: {result.stdout.strip()}")

    def on_preview(self):
        if not self.project_path:
            QMessageBox.warning(self, "Error", "프로젝트를 먼저 여세요.")
            return
        self.log("미리보기 서버 시작 중...")
        # pip install -e
        subprocess.run(
            ["pip", "install", "-e", str(self.project_path)],
            capture_output=True, text=True,
        )
        # Flask 서버 시작
        framework_dir = Path(__file__).resolve().parent.parent.parent
        subprocess.Popen(
            [sys.executable, "-c",
             "from framework.app import create_app; "
             "app = create_app(); "
             "app.run(debug=False, port=5099)"],
            cwd=str(framework_dir),
        )
        import webbrowser
        import threading
        key = self.info_key.text()
        url = f"http://localhost:5099/drift/{key}/" if key != "-" else "http://localhost:5099/"
        threading.Timer(2.0, lambda: webbrowser.open(url)).start()
        self.log(f"✓ 미리보기: {url}")

    def on_register(self):
        if not self.project_path:
            QMessageBox.warning(self, "Error", "프로젝트를 먼저 여세요.")
            return

        key = self.info_key.text()
        version = self.info_version.text()
        if key == "-":
            QMessageBox.warning(self, "Error", "유효한 프로젝트가 아닙니다.")
            return

        # Registry Server 주소
        registry_url = "http://localhost:8080"

        # GitHub 토큰 획득 (gh CLI에서 자동)
        gh_path = os.environ.get("PATH", "") + ";C:\\Program Files\\GitHub CLI"
        env = {**os.environ, "PATH": gh_path}
        token_result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, env=env,
        )
        if token_result.returncode != 0 or not token_result.stdout.strip():
            QMessageBox.warning(
                self, "인증 필요",
                "GitHub 인증이 필요합니다.\n"
                "터미널에서 'gh auth login'을 먼저 실행하세요."
            )
            return
        token = token_result.stdout.strip()

        # Registry Server를 통해 사용자 인증 확인
        import requests
        try:
            auth_resp = requests.get(
                f"{registry_url}/api/auth/verify",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if auth_resp.status_code != 200:
                error_detail = ""
                try:
                    error_detail = auth_resp.json().get("detail", "")
                except Exception:
                    pass
                QMessageBox.warning(
                    self, "인증 실패",
                    f"Registry Server 인증에 실패했습니다.\n{error_detail}"
                )
                return
            username = auth_resp.json()["user"]
        except requests.ConnectionError:
            QMessageBox.warning(
                self, "Registry Server 연결 실패",
                f"Registry Server({registry_url})에 연결할 수 없습니다.\n\n"
                f"서버가 실행 중인지 확인하세요:\n"
                f"  python -m registry_server.app"
            )
            return
        except Exception as e:
            QMessageBox.warning(self, "네트워크 오류", f"Registry Server 연결 실패: {e}")
            return

        # 확인 다이얼로그
        # 기존 플러그인인지 확인
        existing = requests.get(f"{registry_url}/api/plugins/{key}", timeout=5)
        if existing.status_code == 200:
            action = "버전 업데이트"
            msg = f"Registry에 '{key}'이 이미 있습니다.\n새 버전 v{version}을 배포합니다.\n\n사용자: {username}\n계속하시겠습니까?"
        else:
            action = "새 플러그인 등록"
            msg = f"Registry에 '{key}' v{version}을 등록합니다.\n\n사용자: {username}\n계속하시겠습니까?"

        reply = QMessageBox.question(
            self, action, msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.log(f"Registry Server를 통해 등록 중... ({username})")

        # 프로젝트를 zip으로 압축
        import tempfile
        import zipfile
        import shutil

        tmp_zip = tempfile.mktemp(suffix=".zip")
        self.log("  프로젝트 압축 중...")
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in self.project_path.rglob("*"):
                if file.is_file() and "__pycache__" not in str(file) and ".egg-info" not in str(file):
                    zf.write(file, file.relative_to(self.project_path.parent))
        self.log(f"  압축 완료: {Path(tmp_zip).stat().st_size // 1024}KB")

        # Registry Server API 호출
        try:
            if existing.status_code == 200:
                # 기존 플러그인 → 새 버전 배포
                self.log("  새 버전 배포 중...")
                with open(tmp_zip, "rb") as f:
                    resp = requests.post(
                        f"{registry_url}/api/plugins/{key}/versions",
                        headers={"Authorization": f"Bearer {token}"},
                        data={"version": version, "message": f"Update {key} v{version}"},
                        files={"files": ("plugin.zip", f, "application/zip")},
                        timeout=60,
                    )
            else:
                # 새 플러그인 등록
                self.log("  새 플러그인 등록 중...")

                # pyproject.toml에서 description과 category 읽기
                description = ""
                category = "statistical"
                toml_path = self.project_path / "pyproject.toml"
                if toml_path.exists():
                    import tomllib
                    with open(toml_path, "rb") as tf:
                        toml_data = tomllib.load(tf)
                    description = toml_data.get("project", {}).get("description", "")

                with open(tmp_zip, "rb") as f:
                    resp = requests.post(
                        f"{registry_url}/api/plugins",
                        headers={"Authorization": f"Bearer {token}"},
                        data={
                            "key": key,
                            "description": description,
                            "category": category,
                            "version": version,
                        },
                        files={"files": ("plugin.zip", f, "application/zip")},
                        timeout=60,
                    )

            # 결과 처리
            result = resp.json()

            if resp.status_code in (200, 201):
                self.log(f"  ✓ {result.get('message', 'Success')}")
                self.log(f"\n✓ Registry 등록 완료: {key} v{version}")
                self.log(f"  Registry: http://localhost:8080/plugin/{key}")
                QMessageBox.information(
                    self, "등록 완료",
                    f"'{key}' v{version} 등록 완료!\n\n"
                    f"Registry: http://localhost:8080/plugin/{key}\n"
                    f"Owner: {username}"
                )
            else:
                error_msg = result.get("error", "Unknown error")
                detail = result.get("detail", "")
                self.log(f"  ✗ 등록 실패: {error_msg}")
                if detail:
                    self.log(f"    {detail}")
                QMessageBox.warning(
                    self, "등록 실패",
                    f"{error_msg}\n{detail}" if detail else error_msg
                )

        except Exception as e:
            self.log(f"  ✗ 오류: {e}")
            QMessageBox.critical(self, "오류", f"등록 중 오류 발생:\n{e}")

        finally:
            # 임시 파일 정리
            try:
                os.unlink(tmp_zip)
            except Exception:
                pass

    def log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"[{ts}] {msg}")
        self.statusBar().showMessage(msg, 5000)


# ═══════════════════════════════════════
# 메인
# ═══════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Drift Plugin Developer Tool")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
