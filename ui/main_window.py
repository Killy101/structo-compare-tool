import os
import traceback

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QSplitter, QPushButton, QFileDialog, QStatusBar,
    QLabel, QTextBrowser, QProgressBar, QCheckBox, QFrame, QLineEdit,
)
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QKeySequence, QShortcut, QTextDocument

from ui.document_panel import DocumentPanel
from ui.xml_editor import XmlEditor
from logic.pdf_extractor import extract_pdf, render_pdf_preview
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
        self.changes:      list = []

    def run(self):
        try:
            self.progress.emit('Extracting Old PDF…', 10)
            self.old_doc = extract_pdf(self.old_path)

            self.progress.emit('Extracting New PDF…', 40)
            self.new_doc = extract_pdf(self.new_path)

            self.progress.emit('Comparing documents…', 75)
            self.old_html, self.new_html, self.sidebar_html, self.changes = \
                build_diff_html(self.old_doc, self.new_doc)

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
        f'padding:6px 16px;border-radius:4px;font-weight:600;}}'
        f'QPushButton:hover{{background:{hover};}}'
        f'QPushButton:disabled{{background:#e2e8f0;color:#94a3b8;}}'
    )
    b.setStyleSheet(style)
    if min_w:
        b.setMinimumWidth(min_w)
    return b


def _panel_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        'background:#f1f5f9;color:#334155;padding:7px;'
        'font-weight:bold;font-size:12px;letter-spacing:0.5px;'
        'border-bottom:1px solid #e2e8f0;'
    )
    return lbl


def _legend_chip(color: str, text: str) -> QLabel:
    lbl = QLabel(f'  {text}  ')
    lbl.setStyleSheet(
        f'background:{color};padding:2px 10px;border-radius:3px;'
        'font-size:11px;border:1px solid rgba(0,0,0,0.15);'
        'color:#1e293b;font-weight:500;'
    )
    return lbl


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setStyleSheet('color:#e2e8f0;')
    return f


# ---------------------------------------------------------------------------
# Upload screen (page 0)
# ---------------------------------------------------------------------------
_ROW_BASE = ('QFrame{background:#f8fafc;border:1px dashed #cbd5e1;'
             'border-radius:8px;}')
_ROW_HOVER = ('QFrame{background:#eef2ff;border:2px dashed #6366f1;'
              'border-radius:8px;}')
_ROW_OK = ('QFrame{background:#f0fdf4;border:1px solid #86efac;'
           'border-radius:8px;}')


class _UploadPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background:#f0f4f8;')

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QWidget()
        card.setFixedWidth(560)
        card.setStyleSheet(
            'background:#ffffff;border-radius:12px;border:1px solid #e2e8f0;'
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 36, 40, 36)
        card_layout.setSpacing(20)

        # Title
        title = QLabel('Structo Compare')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            'color:#1e293b;font-size:26px;font-weight:bold;'
            'letter-spacing:1px;background:transparent;'
        )
        subtitle = QLabel('Document Comparison Tool')
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet('color:#64748b;font-size:13px;background:transparent;')
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet('color:#e2e8f0;')
        card_layout.addWidget(div)

        # Drop-zone style row helper
        def file_row(icon: str, label: str, optional: bool = False):
            row = QFrame()
            row.setStyleSheet(_ROW_BASE)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(14, 10, 14, 10)
            rl.setSpacing(10)

            lbl = QLabel(f'{icon}  {label}')
            lbl.setStyleSheet(
                'color:#334155;font-size:13px;font-weight:bold;'
                'background:transparent;border:none;'
            )
            lbl.setFixedWidth(120)

            info_wrap = QVBoxLayout()
            info_wrap.setSpacing(1)
            fname = QLabel('Drop file here  ·  or browse')
            fname.setStyleSheet(
                'color:#94a3b8;font-size:12px;background:transparent;border:none;'
            )
            status = QLabel('optional' if optional else '')
            status.setStyleSheet(
                'color:#94a3b8;font-size:10px;background:transparent;border:none;'
            )
            info_wrap.addWidget(fname)
            info_wrap.addWidget(status)

            browse = _btn('Browse…', '#6366f1', '#4f46e5')
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

        self._rows = {'old': self._old_row, 'new': self._new_row, 'xml': self._xml_row}
        self._default_lbl = 'Drop file here  ·  or browse'
        self.setAcceptDrops(True)

        # Compare button
        self.btn_compare = _btn('⟳  Compare', '#0ea5e9', '#0284c7', min_w=160)
        self.btn_compare.setFixedHeight(40)
        self.btn_compare.setEnabled(False)
        cmp_wrap = QHBoxLayout()
        cmp_wrap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cmp_wrap.addWidget(self.btn_compare)
        card_layout.addLayout(cmp_wrap)

        self._hint = QLabel('Select Old PDF and New PDF to enable comparison.')
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setStyleSheet('color:#94a3b8;font-size:11px;background:transparent;')
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
        row    = self._rows[kind]

        if ok:
            setattr(self, f'{kind}_path', path)
            lbl.setText(f'{os.path.basename(path)}  ·  {self._human_size(path)}')
            lbl.setStyleSheet('color:#334155;font-size:12px;background:transparent;border:none;')
            status.setText(msg)
            status.setStyleSheet('color:#059669;font-size:10px;background:transparent;border:none;')
            row.setStyleSheet(_ROW_OK)
        else:
            setattr(self, f'{kind}_path', '')
            lbl.setText(os.path.basename(path))
            lbl.setStyleSheet('color:#334155;font-size:12px;background:transparent;border:none;')
            status.setText(msg)
            status.setStyleSheet('color:#dc2626;font-size:10px;background:transparent;border:none;')
            row.setStyleSheet(_ROW_BASE)

        self._update_compare()

    # ── Reset ──────────────────────────────────────────────────────────────────
    def reset(self):
        """Return the upload card to its pristine, empty state."""
        self.old_path = self.new_path = self.xml_path = ''
        for kind, (lbl, status, optional) in {
            'old': (self._old_lbl, self._old_status, False),
            'new': (self._new_lbl, self._new_status, False),
            'xml': (self._xml_lbl, self._xml_status, True),
        }.items():
            lbl.setText(self._default_lbl)
            lbl.setStyleSheet('color:#94a3b8;font-size:12px;background:transparent;border:none;')
            status.setText('optional' if optional else '')
            status.setStyleSheet('color:#94a3b8;font-size:10px;background:transparent;border:none;')
            self._rows[kind].setStyleSheet(_ROW_BASE)
        self._update_compare()

    # ── Drag and drop ──────────────────────────────────────────────────────────
    def _row_kind_at(self, pos) -> str:
        """Return the file-row kind under *pos*, or '' if none."""
        widget = self.childAt(pos)
        while widget is not None:
            for kind, row in self._rows.items():
                if widget is row:
                    return kind
            widget = widget.parentWidget()
        return ''

    def _clear_row_highlights(self):
        for kind, row in self._rows.items():
            path = getattr(self, f'{kind}_path')
            row.setStyleSheet(_ROW_OK if path else _ROW_BASE)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasUrls():
            return
        kind = self._row_kind_at(event.position().toPoint())
        self._clear_row_highlights()
        if kind:
            self._rows[kind].setStyleSheet(_ROW_HOVER)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._clear_row_highlights()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        target = self._row_kind_at(event.position().toPoint())
        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            if target:                       # dropped onto a specific zone
                self._set_file(target, p)
                target = ''                  # only the first file goes to that zone
            elif ext == '.pdf':
                self._set_file('old' if not self.old_path else 'new', p)
            elif ext in ('.xml', '.xhtml', '.html', '.htm'):
                self._set_file('xml', p)
        self._clear_row_highlights()
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
        self.setStyleSheet('background:#f0f4f8;')

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QWidget()
        card.setFixedWidth(480)
        card.setStyleSheet('background:#ffffff;border-radius:12px;border:1px solid #e2e8f0;')
        cl = QVBoxLayout(card)
        cl.setContentsMargins(40, 40, 40, 40)
        cl.setSpacing(18)

        title = QLabel('Processing Comparison…')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            'color:#1e293b;font-size:20px;font-weight:bold;background:transparent;'
        )
        cl.addWidget(title)

        self._status = QLabel('Initialising…')
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet('color:#64748b;font-size:13px;background:transparent;')
        cl.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)   # indeterminate / pulsing
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        self._bar.setStyleSheet(
            'QProgressBar{background:#e2e8f0;border-radius:4px;border:none;}'
            'QProgressBar::chunk{background:#0ea5e9;border-radius:4px;}'
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

        self._old_doc:       Document | None = None
        self._new_doc:       Document | None = None
        self._old_diff_html: str = ''
        self._new_diff_html: str = ''
        self._old_path:      str = ''
        self._new_path:      str = ''
        self._worker:        _CompareWorker | None = None
        self._view_raw:      bool = False
        self._scroll_syncing: bool = False
        self._changes:       list = []
        self._change_index:  int = -1
        self._pdf_zoom:      float = 2.0

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
        toolbar.setStyleSheet('background:#ffffff;border-bottom:2px solid #e2e8f0;')
        toolbar.setFixedHeight(52)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 0, 12, 0)
        tb.setSpacing(6)

        logo = QLabel('Structo Compare')
        logo.setStyleSheet(
            'color:#1e293b;font-size:17px;font-weight:bold;letter-spacing:1px;'
        )

        self.btn_back     = _btn('＋ New',         '#64748b', '#475569')
        self.btn_recompare = _btn('⟳ Re-Compare', '#059669', '#047857')
        self.btn_view     = _btn('PDF Page View',  '#64748b', '#475569')
        self.btn_export   = _btn('Export ▾',       '#2563eb', '#1d4ed8')
        self.btn_save     = _btn('Save XML As…',   '#dc2626', '#b91c1c')

        self.btn_recompare.setToolTip(
            'Re-run the comparison from the (edited) panel text  ·  Ctrl+R')

        # ── Change navigation (Beyond Compare-style prev/next) ───────────────
        _nav_ss = (
            'QPushButton{background:#f1f5f9;color:#334155;border:1px solid #e2e8f0;'
            'border-radius:4px;padding:4px 9px;font-size:12px;font-weight:bold;}'
            'QPushButton:hover{background:#e2e8f0;}'
            'QPushButton:disabled{background:#f8fafc;color:#cbd5e1;}'
        )
        self.btn_prev_change = QPushButton('▲')
        self.btn_prev_change.setStyleSheet(_nav_ss)
        self.btn_prev_change.setToolTip('Previous change  ·  Shift+F3 / Alt+Up')
        self.btn_next_change = QPushButton('▼')
        self.btn_next_change.setStyleSheet(_nav_ss)
        self.btn_next_change.setToolTip('Next change  ·  F3 / Alt+Down')
        self._change_counter = QLabel('0 / 0')
        self._change_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._change_counter.setFixedWidth(64)
        self._change_counter.setStyleSheet(
            'color:#475569;font-size:12px;font-weight:bold;background:transparent;')

        # ── Zoom controls (only meaningful in PDF Page View) ─────────────────
        self.btn_zoom_out = QPushButton('－')
        self.btn_zoom_out.setStyleSheet(_nav_ss)
        self.btn_zoom_out.setToolTip('Zoom out  ·  Ctrl+-')
        self.btn_zoom_in = QPushButton('＋')
        self.btn_zoom_in.setStyleSheet(_nav_ss)
        self.btn_zoom_in.setToolTip('Zoom in  ·  Ctrl++')
        self._zoom_lbl = QLabel('100%')
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_lbl.setFixedWidth(46)
        self._zoom_lbl.setStyleSheet(
            'color:#475569;font-size:11px;background:transparent;')
        self._zoom_widgets = [self.btn_zoom_out, self._zoom_lbl, self.btn_zoom_in]
        for w in self._zoom_widgets:
            w.setVisible(False)

        # Panel-visibility toggles (always in toolbar for quick access)
        _tgl_ss = (
            'QPushButton{background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;'
            'border-radius:4px;padding:4px 10px;font-size:11px;}'
            'QPushButton:hover{background:#e2e8f0;color:#334155;}'
            'QPushButton:checked{background:#ede9fe;color:#5b21b6;border-color:#c4b5fd;}'
        )
        self._btn_sidebar_tb = QPushButton('Changes ◀')
        self._btn_sidebar_tb.setStyleSheet(_tgl_ss)
        self._btn_sidebar_tb.setCheckable(True)
        self._btn_sidebar_tb.setChecked(False)

        self._btn_xml_tb = QPushButton('XML ▼')
        self._btn_xml_tb.setStyleSheet(_tgl_ss)
        self._btn_xml_tb.setCheckable(True)
        self._btn_xml_tb.setChecked(False)

        self._sync_cb = QCheckBox('Sync Scroll')
        self._sync_cb.setChecked(True)
        self._sync_cb.setStyleSheet(
            'QCheckBox{color:#475569;font-size:12px;spacing:5px;}'
            'QCheckBox::indicator{width:14px;height:14px;}'
            'QCheckBox::indicator:unchecked{background:#f1f5f9;border:1px solid #cbd5e1;border-radius:3px;}'
            'QCheckBox::indicator:checked{background:#0ea5e9;border:1px solid #0ea5e9;border-radius:3px;}'
        )

        self._save_status = QLabel('')
        self._save_status.setStyleSheet(
            'color:#94a3b8;font-size:11px;background:transparent;'
        )

        tb.addWidget(logo)
        tb.addStretch()
        tb.addWidget(self.btn_prev_change)
        tb.addWidget(self._change_counter)
        tb.addWidget(self.btn_next_change)
        tb.addWidget(_sep())
        tb.addWidget(self.btn_recompare)
        tb.addWidget(_sep())
        tb.addWidget(self._btn_sidebar_tb)
        tb.addWidget(self._btn_xml_tb)
        tb.addWidget(_sep())
        tb.addWidget(self._sync_cb)
        tb.addWidget(self.btn_view)
        tb.addWidget(self.btn_zoom_out)
        tb.addWidget(self._zoom_lbl)
        tb.addWidget(self.btn_zoom_in)
        tb.addWidget(_sep())
        tb.addWidget(self.btn_export)
        tb.addWidget(_sep())
        tb.addWidget(self._save_status)
        tb.addWidget(self.btn_save)
        tb.addWidget(_sep())
        tb.addWidget(self.btn_back)
        root.addWidget(toolbar)

        # ── Search bar (Ctrl+F, hidden by default) ────────────────────────────
        search_bar = QWidget()
        search_bar.setVisible(False)
        search_bar.setStyleSheet('background:#f8fafc;border-bottom:1px solid #e2e8f0;')
        search_bar.setFixedHeight(42)
        self._search_bar = search_bar
        sb_lay = QHBoxLayout(search_bar)
        sb_lay.setContentsMargins(12, 6, 12, 6)
        sb_lay.setSpacing(6)

        sb_lbl = QLabel('Find:')
        sb_lbl.setStyleSheet('color:#475569;font-size:12px;background:transparent;')

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText('Search in both panels…')
        self._search_input.setFixedWidth(280)
        self._search_input.setStyleSheet(
            'QLineEdit{background:#ffffff;color:#1e293b;border:1px solid #cbd5e1;'
            'border-radius:3px;padding:3px 8px;font-size:12px;}'
            'QLineEdit:focus{border:1px solid #6366f1;}'
        )

        self._search_count_lbl = QLabel('')
        self._search_count_lbl.setFixedWidth(120)
        self._search_count_lbl.setStyleSheet('color:#64748b;font-size:11px;background:transparent;')

        _sbtn_ss = (
            'QPushButton{background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;'
            'border-radius:3px;padding:3px 10px;font-size:11px;}'
            'QPushButton:hover{background:#e2e8f0;color:#334155;}'
        )
        btn_prev = QPushButton('▲ Prev')
        btn_prev.setStyleSheet(_sbtn_ss)
        btn_next = QPushButton('Next ▼')
        btn_next.setStyleSheet(_sbtn_ss)
        btn_close_search = QPushButton('✕')
        btn_close_search.setFixedWidth(28)
        btn_close_search.setStyleSheet(
            'QPushButton{background:#fee2e2;color:#dc2626;border:none;border-radius:3px;font-size:11px;}'
            'QPushButton:hover{background:#fecaca;}'
        )

        sb_lay.addWidget(sb_lbl)
        sb_lay.addWidget(self._search_input)
        sb_lay.addWidget(self._search_count_lbl)
        sb_lay.addStretch()
        sb_lay.addWidget(btn_prev)
        sb_lay.addWidget(btn_next)
        sb_lay.addWidget(btn_close_search)
        root.addWidget(search_bar)

        # ── Old PDF panel ─────────────────────────────────────────────────────
        old_wrap = QWidget()
        ow = QVBoxLayout(old_wrap)
        ow.setContentsMargins(0, 0, 0, 0)
        ow.setSpacing(0)
        ow.addWidget(_panel_header('Old PDF  ·  editable — fix alignment then ⟳ Re-Compare'))
        self.old_panel = DocumentPanel()
        ow.addWidget(self.old_panel)

        # ── New PDF panel ─────────────────────────────────────────────────────
        new_wrap = QWidget()
        nw = QVBoxLayout(new_wrap)
        nw.setContentsMargins(0, 0, 0, 0)
        nw.setSpacing(0)
        nw.addWidget(_panel_header('New PDF  ·  editable — fix alignment then ⟳ Re-Compare'))
        self.new_panel = DocumentPanel()
        nw.addWidget(self.new_panel)

        # ── PDF row ───────────────────────────────────────────────────────────
        pdf_splitter = QSplitter(Qt.Orientation.Horizontal)
        pdf_splitter.addWidget(old_wrap)
        pdf_splitter.addWidget(new_wrap)
        pdf_splitter.setSizes([800, 800])
        pdf_splitter.setHandleWidth(4)

        # ── XML Editor (collapsible) ──────────────────────────────────────────
        xml_wrap = QWidget()
        self._xml_wrap = xml_wrap
        xw = QVBoxLayout(xml_wrap)
        xw.setContentsMargins(0, 0, 0, 0)
        xw.setSpacing(0)

        xml_hdr = QWidget()
        xml_hdr.setStyleSheet(
            'background:#f1f5f9;border-top:1px solid #e2e8f0;'
            'border-bottom:1px solid #e2e8f0;'
        )
        xml_hdr.setFixedHeight(28)
        xml_hdr_lay = QHBoxLayout(xml_hdr)
        xml_hdr_lay.setContentsMargins(10, 0, 6, 0)
        xml_hdr_lbl = QLabel('XML Editor')
        xml_hdr_lbl.setStyleSheet(
            'color:#334155;font-size:12px;font-weight:bold;'
            'letter-spacing:0.5px;background:transparent;'
        )
        self._btn_toggle_xml = QPushButton('▼ Hide')
        self._btn_toggle_xml.setFixedSize(58, 20)
        self._btn_toggle_xml.setStyleSheet(
            'QPushButton{background:#e2e8f0;color:#64748b;border:none;'
            'border-radius:3px;font-size:10px;}'
            'QPushButton:hover{background:#cbd5e1;color:#334155;}'
        )
        xml_hdr_lay.addWidget(xml_hdr_lbl, 1)
        xml_hdr_lay.addWidget(self._btn_toggle_xml)
        xw.addWidget(xml_hdr)

        self.xml_editor = XmlEditor()
        xw.addWidget(self.xml_editor)

        self._left_splitter = QSplitter(Qt.Orientation.Vertical)
        self._left_splitter.addWidget(pdf_splitter)
        self._left_splitter.addWidget(xml_wrap)
        self._left_splitter.setSizes([560, 280])
        self._left_splitter.setHandleWidth(4)

        # ── Changes sidebar (collapsible) ─────────────────────────────────────
        sidebar_wrap = QWidget()
        sidebar_wrap.setMinimumWidth(28)
        self._sidebar_wrap = sidebar_wrap
        sw = QVBoxLayout(sidebar_wrap)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(0)

        sidebar_hdr = QWidget()
        sidebar_hdr.setStyleSheet(
            'background:#f1f5f9;border-bottom:1px solid #e2e8f0;'
        )
        sidebar_hdr.setFixedHeight(28)
        sidebar_hdr_lay = QHBoxLayout(sidebar_hdr)
        sidebar_hdr_lay.setContentsMargins(10, 0, 6, 0)
        sidebar_hdr_lbl = QLabel('Changes')
        sidebar_hdr_lbl.setStyleSheet(
            'color:#334155;font-size:12px;font-weight:bold;'
            'letter-spacing:0.5px;background:transparent;'
        )
        self._btn_toggle_sidebar = QPushButton('◀ Hide')
        self._btn_toggle_sidebar.setFixedSize(58, 20)
        self._btn_toggle_sidebar.setStyleSheet(
            'QPushButton{background:#e2e8f0;color:#64748b;border:none;'
            'border-radius:3px;font-size:10px;}'
            'QPushButton:hover{background:#cbd5e1;color:#334155;}'
        )
        sidebar_hdr_lay.addWidget(sidebar_hdr_lbl, 1)
        sidebar_hdr_lay.addWidget(self._btn_toggle_sidebar)
        sw.addWidget(sidebar_hdr)

        self.sidebar = QTextBrowser()
        self.sidebar.setStyleSheet('background:#ffffff;border:none;border-left:1px solid #e2e8f0;')
        self.sidebar.setOpenLinks(False)
        self.sidebar.setHtml(
            '<body style="background:#ffffff;color:#94a3b8;font-family:Arial;'
            'font-size:12px;padding:12px;font-style:italic">'
            'Run Compare to see changes.</body>'
        )
        sw.addWidget(self.sidebar)

        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.addWidget(self._left_splitter)
        self._main_splitter.addWidget(sidebar_wrap)
        self._main_splitter.setSizes([1260, 310])
        self._main_splitter.setHandleWidth(4)
        root.addWidget(self._main_splitter, 1)

        # ── Legend bar ────────────────────────────────────────────────────────
        legend_bar = QWidget()
        legend_bar.setStyleSheet('background:#ffffff;border-top:1px solid #e2e8f0;')
        leg = QHBoxLayout(legend_bar)
        leg.setContentsMargins(12, 4, 12, 4)
        leg.addWidget(QLabel('<b>Legend:</b>'))
        leg.addSpacing(6)
        for color, label in [
            ('#ffb3b3', 'Removed'),
            ('#b3ffb3', 'Added'),
        ]:
            leg.addWidget(_legend_chip(color, label))
            leg.addSpacing(4)
        leg.addStretch()
        leg.addWidget(QLabel(
            '<span style="color:#888;font-size:11px">'
            'Red = deleted / modified old words  ·  '
            'Green = added / modified new words</span>'
        ))
        root.addWidget(legend_bar)

        # Wire up search bar buttons
        self._search_input.textChanged.connect(self._on_search_changed)
        self._search_input.returnPressed.connect(self._search_next)
        btn_next.clicked.connect(self._search_next)
        btn_prev.clicked.connect(self._search_prev)
        btn_close_search.clicked.connect(self._close_search)

        # Wire up collapse buttons (panel header AND toolbar)
        self._btn_toggle_sidebar.clicked.connect(self._toggle_sidebar)
        self._btn_toggle_xml.clicked.connect(self._toggle_xml)
        self._btn_sidebar_tb.clicked.connect(self._toggle_sidebar)
        self._btn_xml_tb.clicked.connect(self._toggle_xml)

        return container

    # ── Wire signals ──────────────────────────────────────────────────────────
    def _wire_signals(self):
        # Upload page
        self._upload_page.btn_compare.clicked.connect(self._start_compare)

        # Workspace toolbar
        self.btn_back.clicked.connect(self._go_to_upload)
        self.btn_view.clicked.connect(self._toggle_view)
        self.btn_recompare.clicked.connect(self._recompare)
        self.btn_save.clicked.connect(self._save_xml)
        self._build_export_menu()

        # Change navigation
        self.btn_prev_change.clicked.connect(self._prev_change)
        self.btn_next_change.clicked.connect(self._next_change)

        # Zoom controls
        self.btn_zoom_in.clicked.connect(lambda: self._adjust_zoom(1.25))
        self.btn_zoom_out.clicked.connect(lambda: self._adjust_zoom(0.8))

        # Keyboard shortcuts
        QShortcut(QKeySequence('Ctrl+S'), self).activated.connect(self._save_xml)
        QShortcut(QKeySequence('Ctrl+R'), self).activated.connect(self._recompare)
        QShortcut(QKeySequence('F3'), self).activated.connect(self._next_change)
        QShortcut(QKeySequence('Shift+F3'), self).activated.connect(self._prev_change)
        QShortcut(QKeySequence('Alt+Down'), self).activated.connect(self._next_change)
        QShortcut(QKeySequence('Alt+Up'), self).activated.connect(self._prev_change)
        QShortcut(QKeySequence('Ctrl+F'), self).activated.connect(self._open_search)
        QShortcut(QKeySequence.StandardKey.ZoomIn, self).activated.connect(lambda: self._adjust_zoom(1.25))
        QShortcut(QKeySequence.StandardKey.ZoomOut, self).activated.connect(lambda: self._adjust_zoom(0.8))
        QShortcut(QKeySequence('Escape'), self._search_bar).activated.connect(self._close_search)

        # Sync scroll
        self._sync_cb.toggled.connect(self._on_sync_toggled)
        self._on_sync_toggled(self._sync_cb.isChecked())

        # Sidebar navigation
        self.sidebar.anchorClicked.connect(self._on_sidebar_click)

        # Save-status tracking
        self.xml_editor.document().contentsChanged.connect(self._mark_unsaved)
        self._xml_loaded = False

    # ── Upload / compare flow ─────────────────────────────────────────────────
    def _go_to_upload(self):
        """New session — completely reset the workspace and return to upload."""
        self._reset_session()
        self._stack.setCurrentIndex(0)
        self._status.showMessage('Select files to begin a new comparison.')

    def _reset_session(self):
        """Clear every piece of session state so the next compare starts clean."""
        # Stop any running worker so its callbacks can't touch fresh state.
        if self._worker is not None:
            try:
                self._worker.done.disconnect()
                self._worker.error.disconnect()
                self._worker.progress.disconnect()
            except (RuntimeError, TypeError):
                pass
            if self._worker.isRunning():
                self._worker.requestInterruption()
                self._worker.quit()
                self._worker.wait(2000)
            self._worker = None

        # In-memory results
        self._old_doc = None
        self._new_doc = None
        self._old_diff_html = ''
        self._new_diff_html = ''
        self._old_path = ''
        self._new_path = ''
        self._changes = []
        self._change_index = -1
        self._view_raw = False
        self._pdf_zoom = 2.0

        # Panels / sidebar / xml
        self.old_panel.clear()
        self.new_panel.clear()
        self.sidebar.setHtml(
            '<body style="background:#ffffff;color:#94a3b8;font-family:Arial;'
            'font-size:12px;padding:12px;font-style:italic">'
            'Run Compare to see changes.</body>'
        )
        self.xml_editor.setPlainText('')
        self._xml_loaded = False
        self._set_saved_state('')

        # Toolbar / search / counters
        self.btn_view.setText('PDF Page View')
        for w in self._zoom_widgets:
            w.setVisible(False)
        self._update_change_counter()
        self._close_search()
        self._search_input.clear()

        # Upload page fields
        self._upload_page.reset()

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

        # Remember paths for PDF Page View
        self._old_path = up.old_path
        self._new_path = up.new_path

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
        if w is None:
            self._status.showMessage('Comparison worker failed to initialize.')
            return
        if w.old_doc is None or w.new_doc is None:
            self._status.showMessage('Comparison completed without document data.')
            return

        self._old_doc = w.old_doc
        self._new_doc = w.new_doc
        self._old_diff_html = w.old_html
        self._new_diff_html = w.new_html
        self._changes = w.changes
        self._change_index = -1
        self._view_raw = False
        self.btn_view.setText('PDF Page View')
        for wdg in self._zoom_widgets:
            wdg.setVisible(False)

        self.old_panel.set_html(self._old_diff_html)
        self.new_panel.set_html(self._new_diff_html)
        self.sidebar.setHtml(w.sidebar_html)
        self._update_change_counter()

        self._stack.setCurrentIndex(2)
        n = len(self._changes)
        self._status.showMessage(
            f'Comparison complete — {n} change{"s" if n != 1 else ""} found. '
            'Edit either panel and click ⟳ Re-Compare to refresh, or F3 to step through changes.'
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
            self._render_pdf_pages()
            self.btn_view.setText('Compare View')
            for w in self._zoom_widgets:
                w.setVisible(True)
        else:
            self.old_panel.set_html(self._old_diff_html)
            self.new_panel.set_html(self._new_diff_html)
            self.btn_view.setText('PDF Page View')
            for w in self._zoom_widgets:
                w.setVisible(False)
            self._status.showMessage('Compare View — diff highlights restored.')

    def _render_pdf_pages(self):
        if not (self._old_path and self._new_path):
            self._status.showMessage('PDF Page View needs the original PDF files.')
            self._view_raw = False
            return
        self._status.showMessage('Rendering PDF pages…')
        self._zoom_lbl.setText(f'{int(self._pdf_zoom / 2.0 * 100)}%')
        try:
            old_frac = self.old_panel.scroll_fraction()
            new_frac = self.new_panel.scroll_fraction()
            self.old_panel.set_html(render_pdf_preview(self._old_path, self._pdf_zoom))
            self.new_panel.set_html(render_pdf_preview(self._new_path, self._pdf_zoom))
            self.old_panel.set_scroll_fraction(old_frac)
            self.new_panel.set_scroll_fraction(new_frac)
            self._status.showMessage(
                'PDF Page View — true page layout.  Use ＋ / － to zoom, '
                'Compare View to return.')
        except Exception as e:
            self._view_raw = False
            self._status.showMessage(f'PDF Page View error: {e}')

    def _adjust_zoom(self, factor: float):
        if not self._view_raw:
            return
        self._pdf_zoom = max(0.5, min(self._pdf_zoom * factor, 4.0))
        self._render_pdf_pages()

    # ── Change navigation ─────────────────────────────────────────────────────
    def _update_change_counter(self):
        n = len(self._changes)
        cur = self._change_index + 1 if 0 <= self._change_index < n else 0
        self._change_counter.setText(f'{cur} / {n}')
        self.btn_prev_change.setEnabled(n > 0)
        self.btn_next_change.setEnabled(n > 0)

    def _goto_change(self, index: int):
        n = len(self._changes)
        if n == 0:
            self._status.showMessage('No changes to navigate.')
            return
        if self._view_raw:          # navigation only makes sense in compare view
            self._toggle_view()
        self._change_index = index % n
        ch = self._changes[self._change_index]
        anchor, kind = ch['id'], ch['kind']
        if kind == 'del':
            self.old_panel.scroll_to_anchor(anchor)
        elif kind == 'add':
            self.new_panel.scroll_to_anchor(anchor)
        else:
            self.old_panel.scroll_to_anchor(anchor)
            self.new_panel.scroll_to_anchor(anchor)
        self._update_change_counter()
        label = {'del': 'Deleted', 'add': 'Added', 'mod': 'Modified'}.get(kind, 'Change')
        self._status.showMessage(
            f'Change {self._change_index + 1} of {n}  ·  {label}')

    def _next_change(self):
        self._goto_change(self._change_index + 1)

    def _prev_change(self):
        start = self._change_index if self._change_index >= 0 else 0
        self._goto_change(start - 1)

    # ── Re-Compare from edited panel text ─────────────────────────────────────
    def _recompare(self):
        if self._old_doc is None or self._new_doc is None:
            self._status.showMessage('Run a comparison first.')
            return
        if self._view_raw:
            self._toggle_view()     # back to compare view before reading text

        # Read the edited panels back into documents, preserving per‑word
        # emphasis (bold / italic / underline / strikethrough) and indentation.
        self._old_doc = self.old_panel.edited_document()
        self._new_doc = self.new_panel.edited_document()

        self._status.showMessage('Re-comparing…')
        try:
            self._old_diff_html, self._new_diff_html, sidebar_html, self._changes = \
                build_diff_html(self._old_doc, self._new_doc)
        except Exception as e:
            self._status.showMessage(f'Re-compare error: {e}')
            return

        self.old_panel.set_html(self._old_diff_html)
        self.new_panel.set_html(self._new_diff_html)
        self.sidebar.setHtml(sidebar_html)
        self._change_index = -1
        self._update_change_counter()
        n = len(self._changes)
        self._status.showMessage(
            f'Re-compare complete — {n} change{"s" if n != 1 else ""} found.')

    # ── Export ────────────────────────────────────────────────────────────────
    def _build_export_menu(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction('Side-by-side HTML…', self._export_html)
        menu.addAction('Change list (XML)…', self._export_xml)
        menu.addAction('PDF report…', self._export_pdf_report)
        self.btn_export.setMenu(menu)

    def _export_html(self):
        if not self._old_diff_html:
            self._status.showMessage('Run a comparison first before exporting.')
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Comparison as HTML', '',
            'HTML Files (*.html);;All Files (*)'
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self._build_export_html())
            self._status.showMessage(f'Exported: {path}')
        except Exception as e:
            self._status.showMessage(f'Export error: {e}')

    def _export_xml(self):
        if not self._changes:
            self._status.showMessage('No changes to export — run a comparison first.')
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Change List as XML', '',
            'XML Files (*.xml);;All Files (*)'
        )
        if not path:
            return
        import xml.sax.saxutils as _sx
        old_name = os.path.basename(self._old_path) if self._old_path else 'old'
        new_name = os.path.basename(self._new_path) if self._new_path else 'new'
        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 f'<comparison old="{_sx.quoteattr(old_name)[1:-1]}" '
                 f'new="{_sx.quoteattr(new_name)[1:-1]}" '
                 f'changes="{len(self._changes)}">']
        for ch in self._changes:
            lines.append(f'  <change id="{ch["id"]}" type="{ch["kind"]}">')
            if ch['old']:
                lines.append(f'    <old>{_sx.escape(ch["old"])}</old>')
            if ch['new']:
                lines.append(f'    <new>{_sx.escape(ch["new"])}</new>')
            lines.append('  </change>')
        lines.append('</comparison>')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            self._status.showMessage(f'Exported {len(self._changes)} changes: {path}')
        except Exception as e:
            self._status.showMessage(f'Export error: {e}')

    def _export_pdf_report(self):
        if not self._changes and not self._old_diff_html:
            self._status.showMessage('Run a comparison first before exporting.')
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export PDF Report', '',
            'PDF Files (*.pdf);;All Files (*)'
        )
        if not path:
            return
        try:
            from PySide6.QtGui import QPdfWriter, QPageSize
            writer = QPdfWriter(path)
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            doc = QTextDocument()
            doc.setHtml(self._build_report_html())
            doc.print_(writer)
            self._status.showMessage(f'Exported PDF report: {path}')
        except Exception as e:
            self._status.showMessage(f'PDF export error: {e}')

    def _build_report_html(self) -> str:
        old_name = os.path.basename(self._old_path) if self._old_path else 'Old PDF'
        new_name = os.path.basename(self._new_path) if self._new_path else 'New PDF'
        from html import escape as _esc
        counts = {'del': 0, 'add': 0, 'mod': 0}
        for ch in self._changes:
            counts[ch['kind']] = counts.get(ch['kind'], 0) + 1
        rows = []
        for i, ch in enumerate(self._changes, 1):
            label = {'del': 'Deleted', 'add': 'Added', 'mod': 'Modified'}[ch['kind']]
            old_c = f'<span style="color:#b91c1c">{_esc(ch["old"])}</span>' if ch['old'] else ''
            new_c = f'<span style="color:#15803d">{_esc(ch["new"])}</span>' if ch['new'] else ''
            rows.append(
                f'<tr><td>{i}</td><td><b>{label}</b></td>'
                f'<td>{old_c}</td><td>{new_c}</td></tr>')
        table = ''.join(rows) or '<tr><td colspan="4">No changes detected.</td></tr>'
        return f"""<html><body style="font-family:Arial,sans-serif;color:#1a1a1a">
<h1 style="font-size:18px">Structo Compare Report</h1>
<p style="font-size:12px;color:#475569">{_esc(old_name)} &rarr; {_esc(new_name)}</p>
<p style="font-size:12px"><b>{counts['del']}</b> deleted &nbsp;
<b>{counts['add']}</b> added &nbsp; <b>{counts['mod']}</b> modified &nbsp;
(<b>{len(self._changes)}</b> total)</p>
<table border="1" cellspacing="0" cellpadding="4" width="100%"
 style="font-size:11px;border-collapse:collapse">
<tr style="background:#f1f5f9"><th>#</th><th>Type</th><th>Old</th><th>New</th></tr>
{table}
</table></body></html>"""

    def _build_export_html(self) -> str:
        old_name = os.path.basename(self._old_path) if self._old_path else 'Old PDF'
        new_name = os.path.basename(self._new_path) if self._new_path else 'New PDF'
        css = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Arial, sans-serif; font-size: 13px;
         color: #1a1a1a; background: #f0f0f0; }
  h1 { font-size: 18px; padding: 14px 20px;
       background: #1a1a2e; color: #edf2f4; letter-spacing: 1px; }
  .legend { background: #f8f9fa; padding: 8px 20px; border-bottom: 1px solid #dee2e6;
            display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .chip { padding: 2px 10px; border-radius: 3px; font-size: 11px;
          border: 1px solid rgba(0,0,0,.12); }
  .panels { display: flex; gap: 0; height: calc(100vh - 90px); }
  .panel { flex: 1; overflow-y: auto; background: #fff;
           border-right: 1px solid #ddd; padding: 14px; }
  .panel h2 { font-size: 12px; text-align: center; background: #2b2d42;
              color: #edf2f4; padding: 6px; margin: -14px -14px 10px;
              font-weight: bold; letter-spacing: .5px; }
  p { margin: 3px 0; line-height: 1.6; }
  span[style*="background:#ffb3b3"] { background:#ffb3b3; border-radius:3px; }
  span[style*="background:#b3ffb3"] { background:#b3ffb3; border-radius:3px; }
</style>"""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Structo Compare — {old_name} vs {new_name}</title>
{css}
</head>
<body>
<h1>Structo Compare</h1>
<div class="legend">
  <b>Legend:</b>
  <span class="chip" style="background:#ffb3b3">Removed</span>
  <span class="chip" style="background:#b3ffb3">Added</span>
</div>
<div class="panels">
  <div class="panel">
    <h2>Old — {old_name}</h2>
    {self._old_diff_html}
  </div>
  <div class="panel">
    <h2>New — {new_name}</h2>
    {self._new_diff_html}
  </div>
</div>
</body>
</html>"""

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
        #   del → only old panel has the anchor
        #   add → only new panel has the anchor
        #   mod → both panels
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
            self._set_saved_state('● Unsaved changes', '#d97706')

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

    # ── Collapse / expand panels ──────────────────────────────────────────────
    def _toggle_sidebar(self):
        visible = self.sidebar.isVisible()
        self.sidebar.setVisible(not visible)
        if visible:
            self._btn_toggle_sidebar.setText('▶ Show')
            self._btn_sidebar_tb.setText('Changes ▶')
            self._btn_sidebar_tb.setChecked(True)
            self._sidebar_wrap.setMaximumWidth(80)
        else:
            self._btn_toggle_sidebar.setText('◀ Hide')
            self._btn_sidebar_tb.setText('Changes ◀')
            self._btn_sidebar_tb.setChecked(False)
            self._sidebar_wrap.setMaximumWidth(16777215)
            self._main_splitter.setSizes([1260, 310])

    def _toggle_xml(self):
        visible = self.xml_editor.isVisible()
        self.xml_editor.setVisible(not visible)
        if visible:
            self._btn_toggle_xml.setText('▲ Show')
            self._btn_xml_tb.setText('XML ▲')
            self._btn_xml_tb.setChecked(True)
            self._left_splitter.setSizes([9999, 0])
        else:
            self._btn_toggle_xml.setText('▼ Hide')
            self._btn_xml_tb.setText('XML ▼')
            self._btn_xml_tb.setChecked(False)
            self._left_splitter.setSizes([560, 280])

    # ── Search bar ────────────────────────────────────────────────────────────
    def _open_search(self):
        self._search_bar.setVisible(True)
        self._search_input.setFocus()
        self._search_input.selectAll()

    def _close_search(self):
        self._search_bar.setVisible(False)
        self._search_count_lbl.setText('')

    def _on_search_changed(self, text: str):
        if not text:
            self._search_count_lbl.setText('')
            return
        t = text.lower()
        old_count = self.old_panel.browser.toPlainText().lower().count(t)
        new_count = self.new_panel.browser.toPlainText().lower().count(t)
        total = old_count + new_count
        if total == 0:
            self._search_count_lbl.setText('No matches')
            self._search_count_lbl.setStyleSheet('color:#dc2626;font-size:11px;background:transparent;')
        else:
            self._search_count_lbl.setText(f'{total} match{"es" if total != 1 else ""}')
            self._search_count_lbl.setStyleSheet('color:#059669;font-size:11px;background:transparent;')

    def _search_next(self):
        text = self._search_input.text()
        if not text:
            return
        found_old = self.old_panel.browser.find(text)
        found_new = self.new_panel.browser.find(text)
        if not found_old and not found_new:
            # Wrap: reset cursors and try again from top
            self.old_panel.browser.moveCursor(self.old_panel.browser.textCursor().MoveOperation.Start)
            self.new_panel.browser.moveCursor(self.new_panel.browser.textCursor().MoveOperation.Start)
            self.old_panel.browser.find(text)
            self.new_panel.browser.find(text)

    def _search_prev(self):
        text = self._search_input.text()
        if not text:
            return
        flags = QTextDocument.FindFlag.FindBackward
        found_old = self.old_panel.browser.find(text, flags)
        found_new = self.new_panel.browser.find(text, flags)
        if not found_old and not found_new:
            # Wrap: reset cursors and try again from bottom
            from PySide6.QtGui import QTextCursor
            c_old = self.old_panel.browser.textCursor()
            c_old.movePosition(QTextCursor.MoveOperation.End)
            self.old_panel.browser.setTextCursor(c_old)
            c_new = self.new_panel.browser.textCursor()
            c_new.movePosition(QTextCursor.MoveOperation.End)
            self.new_panel.browser.setTextCursor(c_new)
            self.old_panel.browser.find(text, flags)
            self.new_panel.browser.find(text, flags)

