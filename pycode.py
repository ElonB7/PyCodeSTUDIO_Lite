import sys
import os
import ast
import subprocess
from PyQt6.QtCore import Qt, QRect, QSize, QTimer, pyqtSignal, QRegularExpression, QThread
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QTextFormat, QSyntaxHighlighter, 
    QTextCharFormat, QKeySequence, QAction, QTextCursor
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QTextEdit, QListWidget,
    QStackedWidget, QMessageBox, QSplitter, QFileDialog, QGroupBox,
    QTabWidget, QPlainTextEdit, QMenuBar, QToolBar, QStatusBar, QToolTip,
    QListWidgetItem, QTableWidget, QTableWidgetItem
)

# --- VS CODE DARK+ THEME COLORS ---
THEME = {
    "bg_main": "#1e1e1e",
    "bg_sidebar": "#252526",
    "bg_editor": "#1e1e1e",
    "bg_terminal": "#181818",
    "fg_text": "#d4d4d4",
    "fg_gutter": "#858585",
    "bg_gutter": "#1e1e1e",
    "accent": "#007acc",
    "keyword": "#c586c0",
    "string": "#ce9178",
    "comment": "#6a9955",
    "number": "#b5cea8",
    "function": "#dcdcaa",
    "class": "#4ec9b0",
    "error_red": "#f14c4c",
    "warning_yellow": "#cca700",
    "border": "#333333"
}

VSCODE_STYLE = f"""
QMainWindow {{
    background-color: {THEME["bg_main"]};
    color: {THEME["fg_text"]};
    font-family: 'Segoe UI', 'Consolas', monospace;
    font-size: 13px;
}}
QMenuBar {{
    background-color: {THEME["bg_sidebar"]};
    color: {THEME["fg_text"]};
    border-bottom: 1px solid {THEME["border"]};
}}
QMenuBar::item:selected {{
    background-color: {THEME["accent"]};
}}
QMenu {{
    background-color: {THEME["bg_sidebar"]};
    color: {THEME["fg_text"]};
    border: 1px solid {THEME["border"]};
}}
QMenu::item:selected {{
    background-color: {THEME["accent"]};
}}
QToolBar {{
    background-color: {THEME["bg_sidebar"]};
    border-bottom: 1px solid {THEME["border"]};
    spacing: 6px;
    padding: 4px;
}}
QPushButton {{
    background-color: #333333;
    color: #cccccc;
    border: 1px solid #3f3f46;
    border-radius: 3px;
    padding: 5px 12px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: #3e3e42;
    color: #ffffff;
    border-color: #515155;
}}
QPushButton:pressed {{
    background-color: {THEME["accent"]};
    color: #ffffff;
}}
QTabWidget::pane {{
    border: 1px solid {THEME["border"]};
    background-color: {THEME["bg_editor"]};
}}
QTabBar::tab {{
    background-color: #2d2d2d;
    color: #969696;
    padding: 8px 16px;
    border-top: 2px solid transparent;
    border-right: 1px solid {THEME["border"]};
}}
QTabBar::tab:selected {{
    background-color: {THEME["bg_editor"]};
    color: {THEME["fg_text"]};
    border-top: 2px solid {THEME["accent"]};
}}
QTabBar::tab:hover {{
    color: {THEME["fg_text"]};
}}
QStatusBar {{
    background-color: #007acc;
    color: #ffffff;
    font-weight: bold;
}}
"""

# --- ROBUST PYTHON SYNTAX HIGHLIGHTER ---
class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        kw_format = QTextCharFormat()
        kw_format.setForeground(QColor(THEME["keyword"]))
        kw_format.setFontWeight(QFont.Weight.Bold)
        keywords = [
            'and', 'as', 'assert', 'break', 'class', 'continue', 'def',
            'del', 'elif', 'else', 'except', 'False', 'finally', 'for',
            'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'None',
            'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'True',
            'try', 'while', 'with', 'yield', 'async', 'await', 'print', 'len', 'range', 'int', 'str', 'float', 'list', 'dict'
        ]
        for word in keywords:
            self.rules.append((QRegularExpression(f"\\b{word}\\b"), kw_format))

        str_format = QTextCharFormat()
        str_format.setForeground(QColor(THEME["string"]))
        self.rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), str_format))
        self.rules.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), str_format))

        comm_format = QTextCharFormat()
        comm_format.setForeground(QColor(THEME["comment"]))
        comm_format.setFontItalic(True)
        self.rules.append((QRegularExpression(r"#[^\n]*"), comm_format))

        num_format = QTextCharFormat()
        num_format.setForeground(QColor(THEME["number"]))
        self.rules.append((QRegularExpression(r"\b\d+\b"), num_format))

        func_format = QTextCharFormat()
        func_format.setForeground(QColor(THEME["function"]))
        self.rules.append((QRegularExpression(r"\b[A-Za-z0-9_]+(?=\()"), func_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


# --- LINE NUMBER AREA ---
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)


# --- CODE EDITOR WITH INTELLISENSE & SQUIGGLY ERRORS ---
class CodeEditor(QPlainTextEdit):
    errors_updated = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.syntax_errors = {}
        self.line_number_area = LineNumberArea(self)

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self.update_line_number_area_width(0)
        self.highlight_current_line()
        self.setMouseTracking(True)

        font = QFont("Consolas", 11)
        self.setFont(font)
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {THEME["bg_editor"]};
                color: {THEME["fg_text"]};
                border: none;
                selection-background-color: #264f78;
            }}
        """)

        self.document().contentsChanged.connect(self.check_syntax)

        self.completer_list = QListWidget(self)
        self.completer_list.setWindowFlags(Qt.WindowType.ToolTip)
        self.completer_list.hide()
        self.completer_list.setStyleSheet("""
            QListWidget {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #007acc;
                font-family: 'Consolas', monospace;
                font-size: 12px;
            }
            QListWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
        """)
        self.completer_list.itemClicked.connect(self.insert_completion)

        self.keywords_suggestions = [
            'print', 'def', 'class', 'import', 'from', 'return', 'if', 'elif', 'else',
            'for', 'while', 'try', 'except', 'with', 'as', 'open', 'range', 'len',
            'int', 'str', 'float', 'list', 'dict', 'set', 'True', 'False', 'None',
            'async', 'await', 'lambda', 'global', 'nonlocal', 'pass', 'break', 'continue'
        ]

    def line_number_area_width(self):
        digits = 1
        max_value = max(1, self.blockCount())
        while max_value >= 10:
            max_value //= 10
            digits += 1
        space = 15 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(THEME["bg_gutter"]))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor(THEME["fg_gutter"]))
                painter.setFont(self.font())
                
                if block_number == self.textCursor().blockNumber():
                    painter.setPen(QColor("#ffffff"))

                painter.drawText(0, top, self.line_number_area_width() - 8, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, number)
                
                if (block_number + 1) in self.syntax_errors:
                    painter.setPen(QColor(THEME["error_red"]))
                    painter.drawText(2, top, "●")

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor("#2a2d2e")
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

            for lineno in self.syntax_errors:
                block = self.document().findBlockByNumber(lineno - 1)
                if block.isValid():
                    err_selection = QTextEdit.ExtraSelection()
                    err_selection.cursor = self.textCursor()
                    err_selection.cursor.setPosition(block.position())
                    err_selection.cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                    
                    fmt = QTextCharFormat()
                    fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                    fmt.setUnderlineColor(QColor(THEME["error_red"]))
                    err_selection.format = fmt
                    extra_selections.append(err_selection)

        self.setExtraSelections(extra_selections)
        self.line_number_area.update()

    def check_syntax(self):
        code = self.toPlainText()
        self.syntax_errors.clear()
        
        try:
            ast.parse(code)
        except SyntaxError as e:
            if e.lineno:
                self.syntax_errors[e.lineno] = e.msg
        except Exception:
            pass

        err_list = [{"lineno": ln, "msg": msg} for ln, msg in self.syntax_errors.items()]
        self.errors_updated.emit(err_list)
        self.highlight_current_line()
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        cursor = self.cursorForPosition(pos)
        line = cursor.blockNumber() + 1
        if line in self.syntax_errors:
            QToolTip.showText(self.mapToGlobal(pos), f"SyntaxError: {self.syntax_errors[line]}", self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if self.completer_list.isVisible():
            if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Tab:
                item = self.completer_list.currentItem()
                if item:
                    self.insert_completion(item)
                event.accept()
                return
            elif event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Escape):
                if event.key() == Qt.Key.Key_Escape:
                    self.completer_list.hide()
                else:
                    self.completer_list.keyPressEvent(event)
                event.accept()
                return

        super().keyPressEvent(event)

        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText().strip()
        if len(word) >= 1:
            matches = [w for w in self.keywords_suggestions if w.startswith(word) and w != word]
            if matches:
                self.completer_list.clear()
                self.completer_list.addItems(matches)
                self.completer_list.setCurrentRow(0)
                
                rect = self.cursorRect(cursor)
                global_pos = self.mapToGlobal(rect.bottomLeft())
                self.completer_list.move(global_pos)
                self.completer_list.resize(180, min(100, len(matches) * 22 + 10))
                self.completer_list.show()
                return
        self.completer_list.hide()

    def insert_completion(self, item):
        tc = self.textCursor()
        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        tc.removeSelectedText()
        tc.insertText(item.text())
        self.completer_list.hide()
        self.setFocus()


# --- INTERACTIVE CMD & LIVE SCRIPT RUNNER THREADS ---
class InteractiveTerminalThread(QThread):
    output_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.process = subprocess.Popen(
            ["cmd.exe"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        self.running = True

    def run(self):
        while self.running and self.process.poll() is None:
            line = self.process.stdout.readline()
            if line:
                self.output_signal.emit(line)

    def write_command(self, cmd):
        if self.process and self.process.stdin:
            self.process.stdin.write(cmd + "\n")
            self.process.stdin.flush()

    def stop(self):
        self.running = False
        try:
            self.process.terminate()
        except:
            pass


class ScriptRunnerThread(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, python_path, filepath):
        super().__init__()
        self.python_path = python_path
        self.filepath = filepath
        self.process = None

    def run(self):
        try:
            self.process = subprocess.Popen(
                [self.python_path, "-u", self.filepath],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            for line in iter(self.process.stdout.readline, ''):
                self.output_signal.emit(line)
            self.process.stdout.close()
            self.process.wait()
        except Exception as e:
            self.output_signal.emit(str(e))
        self.finished_signal.emit()

    def stop(self):
        if self.process:
            try:
                self.process.terminate()
            except:
                pass


# --- MAIN IDE WINDOW ---
class PyCodeStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyCode Studio - Python VS Code Clone")
        self.resize(1250, 850)
        self.setStyleSheet(VSCODE_STYLE)

        self.file_paths = {}
        self.runner_thread = None

        self.cmd_thread = InteractiveTerminalThread()
        self.cmd_thread.output_signal.connect(self.append_terminal_output)
        self.cmd_thread.start()

        self.init_ui()
        self.create_actions()
        self.create_menus()
        self.create_toolbar()
        self.new_file()

    def init_ui(self):
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.tab_changed)
        self.main_splitter.addWidget(self.tab_widget)

        self.bottom_tabs = QTabWidget()
        
        terminal_container = QWidget()
        term_layout = QVBoxLayout()
        term_layout.setContentsMargins(0, 0, 0, 0)
        
        self.terminal_output = QTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setStyleSheet(f"""
            QTextEdit {{
                background-color: {THEME["bg_terminal"]};
                color: #4ec9b0;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                border: none;
            }}
        """)
        term_layout.addWidget(self.terminal_output)

        self.term_input = QLineEdit()
        self.term_input.setPlaceholderText("Type commands here (e.g. pip install requests) and press Enter...")
        self.term_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #252526;
                color: #ffffff;
                border: 1px solid {THEME["border"]};
                padding: 5px;
                font-family: 'Consolas', monospace;
            }}
        """)
        self.term_input.returnPressed.connect(self.send_cmd_input)
        term_layout.addWidget(self.term_input)

        terminal_container.setLayout(term_layout)
        self.bottom_tabs.addTab(terminal_container, "Terminal (CMD / pip)")

        self.problems_table = QTableWidget()
        self.problems_table.setColumnCount(2)
        self.problems_table.setHorizontalHeaderLabels(["Line", "Description"])
        self.problems_table.horizontalHeader().setStretchLastSection(True)
        self.problems_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {THEME["bg_terminal"]};
                color: {THEME["error_red"]};
                gridline-color: {THEME["border"]};
                font-family: 'Consolas', monospace;
            }}
        """)
        self.problems_table.cellDoubleClicked.connect(self.jump_to_error_line)
        self.bottom_tabs.addTab(self.problems_table, "Problems (0)")

        self.main_splitter.addWidget(self.bottom_tabs)
        self.main_splitter.setSizes([600, 200])
        self.setCentralWidget(self.main_splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready | Global Python Environment active")

    def create_actions(self):
        self.action_new = QAction("New", self)
        self.action_new.setShortcut(QKeySequence.StandardKey.New)
        self.action_new.triggered.connect(self.new_file)

        self.action_open = QAction("Open...", self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self.open_file)

        self.action_save = QAction("Save", self)
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save.triggered.connect(self.save_file)

        self.action_save_as = QAction("Save As...", self)
        self.action_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.action_save_as.triggered.connect(self.save_file_as)

        self.action_run = QAction("Run Script", self)
        self.action_run.setShortcut("F5")
        self.action_run.triggered.connect(self.run_code)

    def create_menus(self):
        self.menubar = self.menuBar()
        file_menu = self.menubar.addMenu("File")
        file_menu.addAction(self.action_new)
        file_menu.addAction(self.action_open)
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_save_as)
        
        run_menu = self.menubar.addMenu("Run")
        run_menu.addAction(self.action_run)

        view_menu = self.menubar.addMenu("View")

    def create_toolbar(self):
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self.toolbar)

        btn_new = QPushButton("📄 New")
        btn_new.clicked.connect(self.new_file)
        self.toolbar.addWidget(btn_new)

        btn_open = QPushButton("📂 Open")
        btn_open.clicked.connect(self.open_file)
        self.toolbar.addWidget(btn_open)

        btn_save = QPushButton("💾 Save")
        btn_save.clicked.connect(self.save_file)
        self.toolbar.addWidget(btn_save)

        self.toolbar.addSeparator()

        btn_run = QPushButton("▶ Run (F5)")
        btn_run.setObjectName("runButton")
        btn_run.setStyleSheet("""
            QPushButton#runButton {
                background-color: #0e639c;
                color: white;
                font-weight: bold;
                border: none;
            }
            QPushButton#runButton:hover {
                background-color: #1177bb;
            }
        """)
        btn_run.clicked.connect(self.run_code)
        self.toolbar.addWidget(btn_run)

    def new_file(self):
        editor = CodeEditor()
        editor.highlighter = PythonHighlighter(editor.document())
        editor.errors_updated.connect(self.update_errors_for_editor)
        index = self.tab_widget.addTab(editor, "Untitled.py")
        self.tab_widget.setCurrentIndex(index)
        self.file_paths[editor] = None

    def open_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Python Files (*.py);;All Files (*.*)")
        if filepath:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            editor = CodeEditor()
            editor.setPlainText(content)
            editor.highlighter = PythonHighlighter(editor.document())
            editor.errors_updated.connect(self.update_errors_for_editor)
            filename = os.path.basename(filepath)
            index = self.tab_widget.addTab(editor, filename)
            self.tab_widget.setCurrentIndex(index)
            self.file_paths[editor] = filepath

    def save_file(self):
        current_editor = self.get_current_editor()
        if not current_editor:
            return
        filepath = self.file_paths.get(current_editor)
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(current_editor.toPlainText())
                self.status_bar.showMessage(f"Saved: {filepath}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")
        else:
            self.save_file_as()

    def save_file_as(self):
        current_editor = self.get_current_editor()
        if not current_editor:
            return
        filepath, _ = QFileDialog.getSaveFileName(self, "Save File As", "", "Python Files (*.py);;All Files (*.*)")
        if filepath:
            self.file_paths[current_editor] = filepath
            filename = os.path.basename(filepath)
            index = self.tab_widget.currentIndex()
            self.tab_widget.setTabText(index, filename)
            self.save_file()

    def close_tab(self, index):
        widget = self.tab_widget.widget(index)
        self.tab_widget.removeTab(index)
        if widget in self.file_paths:
            del self.file_paths[widget]

    def tab_changed(self, index):
        current_editor = self.get_current_editor()
        if current_editor and current_editor in self.file_paths:
            path = self.file_paths[current_editor]
            self.status_bar.showMessage(path if path else "Untitled.py")
            self.update_errors_for_editor(current_editor.syntax_errors.items() if hasattr(current_editor, 'syntax_errors') else [])

    def get_current_editor(self):
        widget = self.tab_widget.currentWidget()
        if isinstance(widget, CodeEditor):
            return widget
        return None

    def update_errors_for_editor(self, errors):
        current_editor = self.get_current_editor()
        if not current_editor:
            return
        
        err_list = []
        if isinstance(errors, dict):
            err_list = [{"lineno": k, "msg": v} for k, v in errors.items()]
        elif isinstance(errors, list):
            err_list = errors

        index = self.tab_widget.currentIndex()
        tab_text = self.tab_widget.tabText(index).replace(" ⚠️", "")

        if err_list:
            self.tab_widget.setTabText(index, tab_text + " ⚠️")
            self.tab_widget.tabBar().setStyleSheet(f"QTabBar::tab:selected {{ color: {THEME['error_red']}; font-weight: bold; }}")
        else:
            self.tab_widget.setTabText(index, tab_text)
            self.tab_widget.tabBar().setStyleSheet("")

        self.problems_table.setRowCount(len(err_list))
        self.bottom_tabs.setTabText(1, f"Problems ({len(err_list)})")
        
        for row, err in enumerate(err_list):
            ln = str(err.get("lineno", ""))
            msg = err.get("msg", "")
            self.problems_table.setItem(row, 0, QTableWidgetItem(f"Line {ln}"))
            self.problems_table.setItem(row, 1, QTableWidgetItem(msg))

    def jump_to_error_line(self, row, col):
        item = self.problems_table.item(row, 0)
        if item:
            text = item.text()
            try:
                lineno = int(text.replace("Line", "").strip())
                editor = self.get_current_editor()
                if editor:
                    block = editor.document().findBlockByNumber(lineno - 1)
                    cursor = editor.textCursor()
                    cursor.setPosition(block.position())
                    editor.setTextCursor(cursor)
                    editor.setFocus()
            except:
                pass

    def send_cmd_input(self):
        cmd = self.term_input.text().strip()
        if cmd:
            self.terminal_output.append(f"> {cmd}\n")
            self.cmd_thread.write_command(cmd)
            self.term_input.clear()

    def append_terminal_output(self, text):
        self.terminal_output.insertPlainText(text)
        self.terminal_output.ensureCursorVisible()

    def run_code(self):
        current_editor = self.get_current_editor()
        if not current_editor:
            return
        
        code = current_editor.toPlainText()
        self.bottom_tabs.setCurrentIndex(0)
        self.terminal_output.append(f"\n--- STARTING EXECUTION ({sys.executable}) ---\n")

        filepath = self.file_paths.get(current_editor)
        if not filepath:
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".py", mode="w", encoding="utf-8")
            tmp.write(code)
            tmp.close()
            filepath = tmp.name
        else:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(code)
            except:
                pass

        if self.runner_thread and self.runner_thread.isRunning():
            self.runner_thread.stop()

        self.runner_thread = ScriptRunnerThread(sys.executable, filepath)
        self.runner_thread.output_signal.connect(self.append_terminal_output)
        self.runner_thread.finished_signal.connect(lambda: self.terminal_output.append("\n[Execution finished]\n"))
        self.runner_thread.start()

    def closeEvent(self, event):
        if self.cmd_thread:
            self.cmd_thread.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PyCodeStudio()
    window.show()
    sys.exit(app.exec())