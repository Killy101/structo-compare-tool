import os
import traceback

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QSplitter, QPushButton, QFileDialog, QStatusBar,
    QLabel, QTextBrowser, QProgressBar, QCheckBox, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QKeySequence, QShortcut

from ui.document_panel import DocumentPanel
from ui.xml_editor import XmlEditor
from logic.pdf_extractor import extract_pdf
from logic.xml_extractor import extract_xml
from logic.differ import build_diff_html
from models.document import Document


# ---------------------------------------------------------------------------
# Background worker — extracts PDFs and runs diff in one go
# ---------------------------------------------------------------------------
class _CompareWorker(QThread):
    progress = Signal(str, int)   # status message, percent (0–100)
    done     = Signal()
    error    = Signal(str)

    def __init__(self, old_path: str, new_path: str):
        super().__init__()
        self.old_path = old_path
        self.new_path = new_path
        # Results populated by run()
        self.old_doc:      Document | None = None
        self.new_doc:      Document | None = None
        self.old_html:     str = ''
        self.new_html:     str = ''
        self.sidebar_html: str = ''

    def run(self):
        try:
            self.progress.emit('Extracting Old PDF…', 10)
            self.old_doc = extract_pdf(self.old_path)

            self.progress.emit('Extracting New PDF…', 40)
            self.new_doc = extract_pdf(self.new_path)

            self.progress.emit('Comparing documents…', 75)
            self.old_html, self.new_html, self.sidebar_html = build_diff_html(
                self.old_doc, self.new_doc
            )

            self.progress.emit('Done', 100)
            self.done.emit()
        except Exception as exc:
            self.error.emit(str(exc) + '\n\n' + traceback.format_exc())


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _btn(label: str, color: str, hover: str, min_w: int = 0) -> QPushButton:
    b = QPushButton(label)
    style = (
        f'QPushButton{{background:{color};color:#fff;border:none;'
        f'padding:6px 16px;border-radius:4px;font-weight:bold;}}'
        f'QPushButton:hover{{background:{hover};}}'
        f'QPushButton:disabled{{background:#555;color:#999;}}'
    )
    b.setStyleSheet(style)
    if min_w:
        b.setMinimumWidth(min_w)
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


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setStyleSheet('color:#3a3a4a;')
    return f


# ---------------------------------------------------------------------------
# Upload screen (page 0)
# ---------------------------------------------------------------------------
class _UploadPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background:#12122a;')

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QWidget()
        card.setFixedWidth(560)
        card.setStyleSheet(
            'background:#1e1e38;border-radius:12px;'
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 36, 40, 36)
        card_layout.setSpacing(20)

        # Title
        title = QLabel('Structo Compare')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            'color:#edf2f4;font-size:26px;font-weight:bold;'
            'letter-spacing:1px;background:transparent;'
        )
        subtitle = QLabel('Document Comparison Tool')
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet('color:#8890aa;font-size:13px;background:transparent;')
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet('color:#2e2e50;')
        card_layout.addWidget(div)

        # Drop-zone style row helper
        def file_row(icon: str, label: str, optional: bool = False):
            row = QFrame()
            row.setStyleSheet(
                'QFrame{background:#16162e;border:1px dashed #3a3a5a;'
                'border-radius:8px;}'
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(14, 10, 14, 10)
            rl.setSpacing(10)

            lbl = QLabel(f'{icon}  {label}')
            lbl.setStyleSheet(
                'color:#cdd6f4;font-size:13px;font-weight:bold;'
                'background:transparent;border:none;'
            )
            lbl.setFixedWidth(120)

            info_wrap = QVBoxLayout()
            info_wrap.setSpacing(1)
            fname = QLabel('Drop file here  ·  or browse')
            fname.setStyleSheet(
                'color:#6272a4;font-size:12px;background:transparent;border:none;'
            )
            status = QLabel('optional' if optional else '')
            status.setStyleSheet(
                'color:#6272a4;font-size:10px;background:transparent;border:none;'
            )
            info_wrap.addWidget(fname)
            info_wrap.addWidget(status)

            browse = _btn('Browse…', '#3a3a6a', '#4a4a8a')
            browse.setFixedWidth(90)

            rl.addWidget(lbl)
            rl.addLayout(info_wrap, 1)
            rl.addWidget(browse)
            return row, fname, status, browse

        self._old_row, self._old_lbl, self._old_status, self._btn_old = file_row('📄', 'Old PDF')
        self._new_row, self._new_lbl, self._new_status, self._btn_new = file_row('📄', 'New PDF')
        self._xml_row, self._xml_lbl, self._xml_status, self._btn_xml = file_row('📋', 'XML File', optional=True)

        card_layout.addWidget(self._old_row)
        card_layout.addWidget(self._new_row)
        card_layout.addWidget(self._xml_row)

        self.setAcceptDrops(True)

        # Compare button
        self.btn_compare = _btn('⟳  Compare', '#2a9d8f', '#21867a', min_w=160)
        self.btn_compare.setFixedHeight(40)
        self.btn_compare.setEnabled(False)
        cmp_wrap = QHBoxLayout()
        cmp_wrap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cmp_wrap.addWidget(self.btn_compare)
        card_layout.addLayout(cmp_wrap)

        self._hint = QLabel('Select Old PDF and New PDF to enable comparison.')
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setStyleSheet('color:#585b70;font-size:11px;background:transparent;')
        card_layout.addWidget(self._hint)

        outer.addWidget(card)

        # State
        self.old_path: str = ''
        self.new_path: str = ''
        self.xml_path: str = ''

        # Signals
        self._btn_old.clicked.connect(lambda: self._browse('old'))
        self._btn_new.clicked.connect(lambda: self._browse('new'))
        self._btn_xml.clicked.connect(lambda: self._browse('xml'))

    # ── File handling (shared by Browse and drag-drop) ─────────────────────────
    _FILTERS = {
        'old': ('Open Old PDF', 'PDF Files (*.pdf)'),
        'new': ('Open New PDF', 'PDF Files (*.pdf)'),
        'xml': ('Open XML File', 'XML / XHTML Files (*.xml *.xhtml *.html *.htm)'),
    }

    def _browse(self, kind: str):
        title, ffilter = self._FILTERS[kind]
        path, _ = QFileDialog.getOpenFileName(self, title, '', ffilter)
        if path:
            self._set_file(kind, path)

    @staticmethod
    def _human_size(path: str) -> str:
        try:
            n = os.path.getsize(path)
        except OSError:
            return ''
        for unit in ('B', 'KB', 'MB', 'GB'):
            if n < 1024:
                return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
            n /= 1024
        return f'{n:.1f} TB'

    @staticmethod
    def _validate(kind: str, path: str) -> tuple:
        """Return (ok, message)."""
        ext = os.path.splitext(path)[1].lower()
        if kind in ('old', 'new'):
            if ext != '.pdf':
                return False, '✕ Not a PDF file'
            try:
                with open(path, 'rb') as f:
                    if f.read(5) != b'%PDF-':
                        return False, '✕ Invalid PDF header'
            except OSError as e:
                return False, f'✕ {e}'
            return True, '✓ Valid PDF'
        else:
            if ext not in ('.xml', '.xhtml', '.html', '.htm'):
                return False, '✕ Not an XML/HTML file'
            return True, '✓ Valid XML'

    def _set_file(self, kind: str, path: str):
        ok, msg = self._validate(kind, path)
        lbl    = {'old': self._old_lbl,    'new': self._new_lbl,    'xml': self._xml_lbl}[kind]
        status = {'old': self._old_status, 'new': self._new_status, 'xml': self._xml_status}[kind]

        if ok:
            setattr(self, f'{kind}_path', path)
            lbl.setText(f'{os.path.basename(path)}  ·  {self._human_size(path)}')
            lbl.setStyleSheet('color:#cdd6f4;font-size:12px;background:transparent;border:none;')
            status.setText(msg)
            status.setStyleSheet('color:#a6e3a1;font-size:10px;background:transparent;border:none;')
        else:
            setattr(self, f'{kind}_path', '')
            lbl.setText(os.path.basename(path))
            lbl.setStyleSheet('color:#cdd6f4;font-size:12px;background:transparent;border:none;')
            status.setText(msg)
            status.setStyleSheet('color:#f38ba8;font-size:10px;background:transparent;border:none;')

        self._update_compare()

    # ── Drag and drop ──────────────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        # Route by extension; first PDF → old (if empty) else new.
        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            if ext == '.pdf':
                self._set_file('old' if not self.old_path else 'new', p)
            elif ext in ('.xml', '.xhtml', '.html', '.htm'):
                self._set_file('xml', p)
        event.acceptProposedAction()

    def _update_compare(self):
        ready = bool(self.old_path and self.new_path)
        self.btn_compare.setEnabled(ready)
        if ready:
            self._hint.setText('Click Compare to start analysis.')
        else:
            self._hint.setText('Select Old PDF and New PDF to enable comparison.')


# ---------------------------------------------------------------------------
# Processing screen (page 1)
# ---------------------------------------------------------------------------
class _ProcessingPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background:#12122a;')

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QWidget()
        card.setFixedWidth(480)
        card.setStyleSheet('background:#1e1e38;border-radius:12px;')
        cl = QVBoxLayout(card)
        cl.setContentsMargins(40, 40, 40, 40)
        cl.setSpacing(18)

        title = QLabel('Processing Comparison…')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            'color:#edf2f4;font-size:20px;font-weight:bold;background:transparent;'
        )
        cl.addWidget(title)

        self._status = QLabel('Initialising…')
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet('color:#a6adc8;font-size:13px;background:transparent;')
        cl.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)   # indeterminate / pulsing
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        self._bar.setStyleSheet(
            'QProgressBar{background:#2b2d42;border-radius:4px;border:none;}'
            'QProgressBar::chunk{background:#2a9d8f;border-radius:4px;}'
        )
        cl.addWidget(self._bar)

        outer.addWidget(card)

    def set_status(self, msg: str, _pct: int = 0):
        self._status.setText(msg)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Structo Compare — PDF vs PDF + XML Editor')
        self.resize(1600, 920)

        self._old_doc:      Document | None = None
        self._new_doc:      Document | None = None
        self._old_diff_html: str = ''
        self._new_diff_html: str = ''
        self._worker:        _CompareWorker | None = None
        self._view_raw:      bool = False
        self._scroll_syncing: bool = False

        self._build_ui()
        self._wire_signals()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._upload_page = _UploadPage()
        self._proc_page   = _ProcessingPage()
        self._work_page   = self._build_workspace()

        self._stack.addWidget(self._upload_page)   # index 0
        self._stack.addWidget(self._proc_page)     # index 1
        self._stack.addWidget(self._work_page)     # index 2

        self._stack.setCurrentIndex(0)

        self._status = QStatusBar()
        self._status.setStyleSheet('font-size:12px;')
        self.setStatusBar(self._status)
        self._status.showMessage('Select files on the upload screen to begin.')

    def _build_workspace(self) -> QWidget:
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet('background:#1a1a2e;')
        toolbar.setFixedHeight(52)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 0, 12, 0)
        tb.setSpacing(6)

        logo = QLabel('Structo Compare')
        logo.setStyleSheet(
            'color:#edf2f4;font-size:17px;font-weight:bold;letter-spacing:1px;'
        )

        self.btn_back    = _btn('← New Files',   '#3a3a6a', '#4a4a8a')
        self.btn_view    = _btn('PDF Raw View',   '#6c757d', '#5a6268')
        self.btn_save    = _btn('Save XML As…',   '#e76f51', '#d4623d')

        self._sync_cb = QCheckBox('Sync Scroll')
        self._sync_cb.setStyleSheet(
            'QCheckBox{color:#cdd6f4;font-size:12px;spacing:5px;}'
            'QCheckBox::indicator{width:14px;height:14px;}'
            'QCheckBox::indicator:unchecked{background:#3a3a5a;border:1px solid #556;border-radius:3px;}'
            'QCheckBox::indicator:checked{background:#2a9d8f;border:1px solid #2a9d8f;border-radius:3px;}'
        )

        self._save_status = QLabel('')
        self._save_status.setStyleSheet(
            'color:#6c7086;font-size:11px;background:transparent;'
        )

        tb.addWidget(logo)
        tb.addStretch()
        tb.addWidget(self.btn_back)
        tb.addWidget(_sep())
        tb.addWidget(self._sync_cb)
        tb.addWidget(self.btn_view)
        tb.addWidget(_sep())
        tb.addWidget(self._save_status)
        tb.addWidget(self.btn_save)
        root.addWidget(toolbar)

        # ── Old PDF panel ─────────────────────────────────────────────────────
        old_wrap = QWidget()
        ow = QVBoxLayout(old_wrap)
        ow.setContentsMargins(0, 0, 0, 0)
        ow.setSpacing(0)
        ow.addWidget(_panel_header('Old  (PDF)'))
        self.old_panel = DocumentPanel()
        ow.addWidget(self.old_panel)

        # ── New PDF panel ─────────────────────────────────────────────────────
        new_wrap = QWidget()
        nw = QVBoxLayout(new_wrap)
        nw.setContentsMargins(0, 0, 0, 0)
        nw.setSpacing(0)
        nw.addWidget(_panel_header('New  (PDF)'))
        self.new_panel = DocumentPanel()
        nw.addWidget(self.new_panel)

        # ── PDF row ───────────────────────────────────────────────────────────
        pdf_splitter = QSplitter(Qt.Orientation.Horizontal)
        pdf_splitter.addWidget(old_wrap)
        pdf_splitter.addWidget(new_wrap)
        pdf_splitter.setSizes([800, 800])
        pdf_splitter.setHandleWidth(4)

        # ── XML Editor ────────────────────────────────────────────────────────
        xml_wrap = QWidget()
        xw = QVBoxLayout(xml_wrap)
        xw.setContentsMargins(0, 0, 0, 0)
        xw.setSpacing(0)
        xw.addWidget(_panel_header('XML Editor'))
        self.xml_editor = XmlEditor()
        xw.addWidget(self.xml_editor)

        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(pdf_splitter)
        left_splitter.addWidget(xml_wrap)
        left_splitter.setSizes([560, 280])
        left_splitter.setHandleWidth(4)

        # ── Changes sidebar ───────────────────────────────────────────────────
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

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(left_splitter)
        main_splitter.addWidget(sidebar_wrap)
        main_splitter.setSizes([1260, 310])
        main_splitter.setHandleWidth(4)
        root.addWidget(main_splitter, 1)

        # ── Legend bar ────────────────────────────────────────────────────────
        legend_bar = QWidget()
        legend_bar.setStyleSheet('background:#f8f9fa;border-top:1px solid #dee2e6;')
        leg = QHBoxLayout(legend_bar)
        leg.setContentsMargins(12, 4, 12, 4)
        leg.addWidget(QLabel('<b>Legend:</b>'))
        leg.addSpacing(6)
        for color, label in [
            ('#ffb3b3', 'Deleted'),
            ('#b3ffb3', 'Added'),
            ('#ffffa0', 'Modified (new)'),
            ('#ffd6d6', 'Modified (old)'),
            ('#ddd0ff', 'Emphasis change'),
        ]:
            leg.addWidget(_legend_chip(color, label))
            leg.addSpacing(4)
        leg.addStretch()
        leg.addWidget(QLabel(
            '<span style="color:#888;font-size:11px">'
            'Bold <b>B</b> · Italic <i>I</i> · Strike <s>S</s></span>'
        ))
        root.addWidget(legend_bar)

        return container

    # ── Wire signals ──────────────────────────────────────────────────────────
    def _wire_signals(self):
        # Upload page
        self._upload_page.btn_compare.clicked.connect(self._start_compare)

        # Workspace toolbar
        self.btn_back.clicked.connect(self._go_to_upload)
        self.btn_view.clicked.connect(self._toggle_view)
        self.btn_save.clicked.connect(self._save_xml)
        QShortcut(QKeySequence('Ctrl+S'), self).activated.connect(self._save_xml)

        # Sync scroll
        self._sync_cb.toggled.connect(self._on_sync_toggled)

        # Sidebar navigation
        self.sidebar.anchorClicked.connect(self._on_sidebar_click)

        # Save-status tracking
        self.xml_editor.document().contentsChanged.connect(self._mark_unsaved)
        self._xml_loaded = False

    # ── Upload / compare flow ─────────────────────────────────────────────────
    def _go_to_upload(self):
        self._stack.setCurrentIndex(0)
        self._status.showMessage('Select files to begin a new comparison.')

    def _start_compare(self):
        up = self._upload_page
        if not up.old_path or not up.new_path:
            return

        # Load XML immediately (lightweight)
        if up.xml_path:
            try:
                xml_doc = extract_xml(up.xml_path)
                self.xml_editor.setPlainText(xml_doc.raw_xml)
                self._xml_loaded = True
                self._set_saved_state('XML loaded — not yet saved')
            except Exception as e:
                self._status.showMessage(f'XML load error: {e}')

        # Switch to processing screen
        self._stack.setCurrentIndex(1)
        self._proc_page.set_status('Initialising…')
        self._status.showMessage('Processing…')

        self._worker = _CompareWorker(up.old_path, up.new_path)
        self._worker.progress.connect(self._proc_page.set_status)
        self._worker.progress.connect(
            lambda msg, _pct: self._status.showMessage(msg)
        )
        self._worker.done.connect(self._on_compare_done)
        self._worker.error.connect(self._on_compare_error)
        self._worker.start()

    def _on_compare_done(self):
        w = self._worker
        self._old_doc       = w.old_doc
        self._new_doc       = w.new_doc
        self._old_diff_html = w.old_html
        self._new_diff_html = w.new_html
        self._view_raw      = False
        self.btn_view.setText('PDF Raw View')

        self.old_panel.set_html(self._old_diff_html)
        self.new_panel.set_html(self._new_diff_html)
        self.sidebar.setHtml(w.sidebar_html)

        self._stack.setCurrentIndex(2)
        self._status.showMessage(
            'Comparison complete. Edit XML below and Save XML As… when done.'
        )

    def _on_compare_error(self, msg: str):
        self._stack.setCurrentIndex(0)
        self._status.showMessage(f'Compare error: {msg[:120]}')

    # ── View mode toggle ──────────────────────────────────────────────────────
    def _toggle_view(self):
        if self._old_doc is None:
            return
        self._view_raw = not self._view_raw
        if self._view_raw:
            self.old_panel.set_html(self._old_doc.to_html())
            self.new_panel.set_html(self._new_doc.to_html())
            self.btn_view.setText('Compare View')
            self._status.showMessage('PDF Raw View — showing extracted text without diff highlights.')
        else:
            self.old_panel.set_html(self._old_diff_html)
            self.new_panel.set_html(self._new_diff_html)
            self.btn_view.setText('PDF Raw View')
            self._status.showMessage('Compare View — diff highlights restored.')

    # ── Sync scroll ───────────────────────────────────────────────────────────
    def _on_sync_toggled(self, checked: bool):
        old_sb = self.old_panel.browser.verticalScrollBar()
        new_sb = self.new_panel.browser.verticalScrollBar()

        if checked:
            old_sb.valueChanged.connect(self._sync_old_to_new)
            new_sb.valueChanged.connect(self._sync_new_to_old)
        else:
            try:
                old_sb.valueChanged.disconnect(self._sync_old_to_new)
                new_sb.valueChanged.disconnect(self._sync_new_to_old)
            except RuntimeError:
                pass

    def _sync_old_to_new(self, value: int):
        if self._scroll_syncing:
            return
        self._scroll_syncing = True
        sb = self.new_panel.browser.verticalScrollBar()
        # Scale proportionally in case documents have different lengths
        old_sb = self.old_panel.browser.verticalScrollBar()
        if old_sb.maximum() > 0:
            frac = value / old_sb.maximum()
            sb.setValue(int(frac * sb.maximum()))
        self._scroll_syncing = False

    def _sync_new_to_old(self, value: int):
        if self._scroll_syncing:
            return
        self._scroll_syncing = True
        sb = self.old_panel.browser.verticalScrollBar()
        new_sb = self.new_panel.browser.verticalScrollBar()
        if new_sb.maximum() > 0:
            frac = value / new_sb.maximum()
            sb.setValue(int(frac * sb.maximum()))
        self._scroll_syncing = False

    # ── Sidebar click-to-navigate ─────────────────────────────────────────────
    def _on_sidebar_click(self, url: QUrl):
        # href is "#kind:cN" (e.g. "#del:c5", "#mod:c12").
        # Fall back to plain "#cN" for any legacy items.
        raw = url.fragment() or url.toString().lstrip('#')
        if '/' in raw:
            raw = raw.rsplit('/', 1)[-1]
        if not raw:
            return

        if ':' in raw:
            kind, anchor = raw.split(':', 1)
        else:
            kind, anchor = 'mod', raw   # treat as two-panel nav

        # Route to the correct panel(s):
        #   del  → only old panel has the anchor
        #   add  → only new panel has the anchor
        #   mod / emph → both panels
        if kind == 'del':
            self.old_panel.scroll_to_anchor(anchor)
        elif kind == 'add':
            self.new_panel.scroll_to_anchor(anchor)
        else:
            self.old_panel.scroll_to_anchor(anchor)
            self.new_panel.scroll_to_anchor(anchor)

    # ── Save-status indicator ──────────────────────────────────────────────────
    def _set_saved_state(self, text: str, color: str = '#6c7086'):
        self._save_status.setText(text)
        self._save_status.setStyleSheet(
            f'color:{color};font-size:11px;background:transparent;'
        )

    def _mark_unsaved(self):
        if self._xml_loaded:
            self._set_saved_state('● Unsaved changes', '#f9e2af')

    # ── Save XML ──────────────────────────────────────────────────────────────
    def _save_xml(self):
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
            self._set_saved_state(f'✓ Saved · {os.path.basename(path)}', '#a6e3a1')
        except Exception as e:
            self._status.showMessage(f'Save error: {e}')
            self._set_saved_state('✕ Save failed', '#f38ba8')
