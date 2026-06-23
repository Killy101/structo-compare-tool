import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QPushButton, QFileDialog, QStatusBar,
    QLabel, QTextBrowser,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut

from ui.document_panel import DocumentPanel
from ui.xml_editor import XmlEditor
from logic.pdf_extractor import extract_pdf
from logic.xml_extractor import extract_xml
from logic.differ import build_diff_html
from models.document import Document


# ---------------------------------------------------------------------------
# Background worker — keeps UI responsive on large files
# ---------------------------------------------------------------------------
class _CompareWorker(QThread):
    done = Signal(str, str, str)  # old_html, new_html, sidebar_html
    error = Signal(str)

    def __init__(self, old_doc: Document, new_doc: Document):
        super().__init__()
        self._old = old_doc
        self._new = new_doc

    def run(self):
        try:
            old_html, new_html, sidebar_html = build_diff_html(self._old, self._new)
            self.done.emit(old_html, new_html, sidebar_html)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _btn(label: str, color: str, hover: str) -> QPushButton:
    b = QPushButton(label)
    b.setStyleSheet(
        f'QPushButton{{background:{color};color:#fff;border:none;'
        f'padding:6px 16px;border-radius:4px;font-weight:bold;}}'
        f'QPushButton:hover{{background:{hover};}}'
        f'QPushButton:disabled{{background:#555;color:#999;}}'
    )
    return b


def _panel_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        'background:#2b2d42;color:#edf2f4;padding:6px;'
        'font-weight:bold;font-size:12px;letter-spacing:0.5px;'
    )
    return lbl


def _legend_chip(color: str, text: str) -> QLabel:
    lbl = QLabel(f'  {text}  ')
    lbl.setStyleSheet(
        f'background:{color};padding:2px 10px;border-radius:3px;'
        'font-size:11px;border:1px solid rgba(0,0,0,0.15);'
    )
    return lbl


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Structo Compare — PDF vs PDF + XML Editor')
        self.resize(1600, 920)

        self._old_doc: Document | None = None
        self._new_doc: Document | None = None
        self._worker: _CompareWorker | None = None

        self._build_ui()
        self._wire_signals()

    # ------------------------------------------------------------------
    def _build_ui(self):

        # ── Toolbar ──────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet('background:#1a1a2e;')
        toolbar.setFixedHeight(52)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 0, 12, 0)
        tb.setSpacing(8)

        logo = QLabel('Structo Compare')
        logo.setStyleSheet(
            'color:#edf2f4;font-size:17px;font-weight:bold;letter-spacing:1px;'
        )

        self.btn_old  = _btn('Open Old PDF',  '#4361ee', '#3a56d4')
        self.btn_new  = _btn('Open New PDF',  '#4361ee', '#3a56d4')
        self.btn_xml  = _btn('Open XML',      '#7b5ea7', '#6a4d94')
        self.btn_cmp  = _btn('⟳  Compare',   '#2a9d8f', '#21867a')
        self.btn_save = _btn('Save XML As…',  '#e76f51', '#d4623d')

        tb.addWidget(logo)
        tb.addStretch()
        for w in [self.btn_old, self.btn_new, self.btn_xml,
                  QLabel(''), self.btn_cmp, self.btn_save]:
            tb.addWidget(w)

        # ── Old PDF panel ────────────────────────────────────────────
        old_wrap = QWidget()
        ow = QVBoxLayout(old_wrap)
        ow.setContentsMargins(0, 0, 0, 0)
        ow.setSpacing(0)
        ow.addWidget(_panel_header('Old  (PDF)'))
        self.old_panel = DocumentPanel()
        ow.addWidget(self.old_panel)

        # ── New PDF panel ────────────────────────────────────────────
        new_wrap = QWidget()
        nw = QVBoxLayout(new_wrap)
        nw.setContentsMargins(0, 0, 0, 0)
        nw.setSpacing(0)
        nw.addWidget(_panel_header('New  (PDF)'))
        self.new_panel = DocumentPanel()
        nw.addWidget(self.new_panel)

        # ── PDF row (top, horizontal split) ─────────────────────────
        pdf_splitter = QSplitter(Qt.Orientation.Horizontal)
        pdf_splitter.addWidget(old_wrap)
        pdf_splitter.addWidget(new_wrap)
        pdf_splitter.setSizes([800, 800])
        pdf_splitter.setHandleWidth(4)

        # ── XML Editor (bottom) ──────────────────────────────────────
        xml_wrap = QWidget()
        xw = QVBoxLayout(xml_wrap)
        xw.setContentsMargins(0, 0, 0, 0)
        xw.setSpacing(0)
        xw.addWidget(_panel_header('XML Editor'))
        self.xml_editor = XmlEditor()
        xw.addWidget(self.xml_editor)

        # ── Left column: PDF row on top, XML editor below ────────────
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(pdf_splitter)
        left_splitter.addWidget(xml_wrap)
        left_splitter.setSizes([560, 280])
        left_splitter.setHandleWidth(4)

        # ── Changes sidebar (right) ──────────────────────────────────
        sidebar_wrap = QWidget()
        sidebar_wrap.setMinimumWidth(240)
        sw = QVBoxLayout(sidebar_wrap)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(0)
        sw.addWidget(_panel_header('Changes'))
        self.sidebar = QTextBrowser()
        self.sidebar.setStyleSheet('background:#1e1e2e;border:none;')
        self.sidebar.setOpenLinks(False)
        self.sidebar.setHtml(
            '<body style="background:#1e1e2e;color:#585b70;font-family:Arial;'
            'font-size:12px;padding:12px;font-style:italic">'
            'Run Compare to see changes.</body>'
        )
        sw.addWidget(self.sidebar)

        # ── Main horizontal splitter: left content | sidebar ─────────
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(left_splitter)
        main_splitter.addWidget(sidebar_wrap)
        main_splitter.setSizes([1250, 320])
        main_splitter.setHandleWidth(4)

        # ── Legend bar ───────────────────────────────────────────────
        legend_bar = QWidget()
        legend_bar.setStyleSheet(
            'background:#f8f9fa;border-top:1px solid #dee2e6;'
        )
        leg = QHBoxLayout(legend_bar)
        leg.setContentsMargins(12, 4, 12, 4)
        leg.addWidget(QLabel('<b>Legend:</b>'))
        leg.addSpacing(6)
        leg.addWidget(_legend_chip('#ffb3b3', 'Deleted'))
        leg.addSpacing(4)
        leg.addWidget(_legend_chip('#b3ffb3', 'Added'))
        leg.addSpacing(4)
        leg.addWidget(_legend_chip('#ffffa0', 'Modified (new)'))
        leg.addSpacing(4)
        leg.addWidget(_legend_chip('#ffd6d6', 'Modified (old)'))
        leg.addStretch()
        leg.addWidget(QLabel(
            '<span style="color:#888;font-size:11px">'
            'Bold <b>B</b> · Italic <i>I</i> · Strike <s>S</s></span>'
        ))

        # ── Status bar ───────────────────────────────────────────────
        self._status = QStatusBar()
        self._status.setStyleSheet('font-size:12px;')
        self.setStatusBar(self._status)
        self._status.showMessage(
            'Open Old PDF, New PDF, and XML file — then click Compare.'
        )

        # ── Root layout ──────────────────────────────────────────────
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(toolbar)
        root.addWidget(main_splitter, 1)
        root.addWidget(legend_bar)
        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    def _wire_signals(self):
        self.btn_old.clicked.connect(self._open_old_pdf)
        self.btn_new.clicked.connect(self._open_new_pdf)
        self.btn_xml.clicked.connect(self._open_xml)
        self.btn_cmp.clicked.connect(self._compare)
        self.btn_save.clicked.connect(self._save_xml)
        QShortcut(QKeySequence('Ctrl+S'), self).activated.connect(self._save_xml)

    # ------------------------------------------------------------------
    def _open_old_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open Old PDF', '', 'PDF Files (*.pdf)'
        )
        if not path:
            return
        self._status.showMessage('Loading Old PDF…')
        try:
            self._old_doc = extract_pdf(path)
            self.old_panel.set_html(self._old_doc.to_html())
            self._status.showMessage(f'Old PDF: {os.path.basename(path)}')
        except Exception as e:
            self._status.showMessage(f'Error: {e}')

    def _open_new_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open New PDF', '', 'PDF Files (*.pdf)'
        )
        if not path:
            return
        self._status.showMessage('Loading New PDF…')
        try:
            self._new_doc = extract_pdf(path)
            self.new_panel.set_html(self._new_doc.to_html())
            self._status.showMessage(f'New PDF: {os.path.basename(path)}')
        except Exception as e:
            self._status.showMessage(f'Error: {e}')

    def _open_xml(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open XML', '',
            'XML / XHTML Files (*.xml *.xhtml *.html *.htm)'
        )
        if not path:
            return
        try:
            xml_doc = extract_xml(path)
            self.xml_editor.setPlainText(xml_doc.raw_xml)
            self._status.showMessage(f'XML: {os.path.basename(path)}')
        except Exception as e:
            self._status.showMessage(f'Error loading XML: {e}')

    def _compare(self):
        if not self._old_doc:
            self._status.showMessage('Open the Old PDF first.')
            return
        if not self._new_doc:
            self._status.showMessage('Open the New PDF first.')
            return

        self.btn_cmp.setEnabled(False)
        self._status.showMessage('Comparing…')

        self._worker = _CompareWorker(self._old_doc, self._new_doc)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, old_html: str, new_html: str, sidebar_html: str):
        self.old_panel.set_html(old_html)
        self.new_panel.set_html(new_html)
        self.sidebar.setHtml(sidebar_html)
        self.btn_cmp.setEnabled(True)
        self._status.showMessage(
            'Comparison complete. Edit XML below and Save XML As… when done.'
        )

    def _on_error(self, msg: str):
        self.btn_cmp.setEnabled(True)
        self._status.showMessage(f'Compare error: {msg}')

    def _save_xml(self):
        """Always opens a Save As dialog so user picks the path."""
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save XML As', '',
            'XML Files (*.xml);;All Files (*)'
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.xml_editor.toPlainText())
            self._status.showMessage(f'Saved: {path}')
        except Exception as e:
            self._status.showMessage(f'Save error: {e}')
