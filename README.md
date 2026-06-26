# Structo Compare Tool

A desktop application for side-by-side PDF document comparison with intelligent word-level diffing, rich text styling detection, and an optional XML editor for structured document workflows.

---

## Features

- **Side-by-side PDF comparison** — load two PDFs and see exactly what changed
- **Word-stream diffing** — reflow-safe comparison that ignores pagination differences between versions
- **Rich text styling** — detects bold, italic, underline, and strikethrough from font flags, font names, and PDF drawing annotations
- **Two-level diff algorithm** — block-level pass first, then word-level sub-diffs on changed ranges for accuracy and speed
- **Color-coded changes** — red for removed text, green for added, orange for modified
- **Editable panels** — fix OCR errors or alignment issues in-place and re-run the diff without reloading the PDFs
- **Changes sidebar** — lists all modifications with statistics; click any entry to jump to that location
- **Toolbar search** — find text across both panels simultaneously with pink highlighting
- **Scroll sync** — optionally lock both panels to scroll together
- **PDF Page View** — render pages as images for visual layout inspection with zoom controls
- **XML editor** — optional structured XML/XHTML editing with live preview, syntax highlighting, and IntelliSense for Structo semantic tags
- **Export** — save results in WF2 format (XML with diff metadata tracking user edits)
- **Large document support** — handles PDFs up to 3,000 pages with parallel extraction and chunked HTML loading

---

## Requirements

- Python 3.11 or later

---

## Installation

```bash
pip install -r requirements.txt
```

**Dependencies:**

| Package | Version |
|---|---|
| PySide6 | ≥ 6.5.0 |
| PyMuPDF | ≥ 1.23.0 |
| lxml | ≥ 4.9.0 |
| PyInstaller | ≥ 6.0.0 |

---

## Running from Source

```bash
python main.py
```

---

## Building an Executable

**Windows (cmd):**
```cmd
build_exe.bat
```

**Unix/Linux/macOS:**
```bash
bash build_exe.sh
```

**Manual:**
```bash
pyinstaller structo_compare.spec
```

Output is written to `dist/StructoCompare.exe`.

---

## Usage

### 1. Upload
- Select the **Old PDF** and **New PDF** using drag-and-drop or the file browser
- Optionally add an **XML file** as a structured baseline
- Click **Compare**

### 2. Processing
- A progress bar tracks PDF extraction and diff computation

### 3. Workspace
- The **left panels** show the old and new document text side-by-side
- The **right sidebar** lists all changes; click any entry to scroll to it
- The **toolbar** provides search, change navigation, mode toggles, and export

### 4. Editing & Re-comparing
- Edit either panel directly to correct OCR or alignment issues
- Press **Ctrl+R** (or click **⟳ Re-Compare**) to re-run the diff from edited text

### 5. Export
- Click **Export ▾** and save in WF2 format

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+R` | Re-Compare |
| `Ctrl+F` | Focus search bar |
| `F3` / `Shift+F3` | Next / Previous change |
| `Alt+Down` / `Alt+Up` | Navigate changes |
| `Enter` / `Shift+Enter` | Search next / previous |
| `Ctrl++` / `Ctrl+-` | Zoom in / out (PDF Page View) |
| `Ctrl+S` | Save XML (XML editor) |
| `Ctrl+E` | Export |

---

## Project Structure

```
structo-compare-tool/
├── main.py                     # Entry point
├── requirements.txt
├── structo_compare.spec        # PyInstaller config
├── build_exe.sh / build_exe.bat
├── models/
│   └── document.py             # Core data model (TextSpan, TextBlock, Document)
├── logic/
│   ├── pdf_extractor.py        # PDF → Document (text + styling + structure)
│   ├── xml_extractor.py        # XML/HTML → Document
│   ├── text_parser.py          # Edited panel text → Document
│   └── differ.py               # Two-level word-stream diff engine
├── ui/
│   ├── main_window.py          # Upload, processing, and workspace screens
│   ├── document_panel.py       # Editable side-by-side panels
│   └── xml_editor.py           # XML editor with preview and IntelliSense
└── tests/
    ├── test_structure.py
    ├── test_pdf_extractor.py
    └── test_panel_roundtrip.py
```

---

## Running Tests

```bash
pytest tests/
```

---

## CI/CD

GitHub Actions builds a Windows executable on every push to `main`/`master` using Python 3.11 and uploads it as a 30-day artifact. See `.github/workflows/build-exe.yml`.
