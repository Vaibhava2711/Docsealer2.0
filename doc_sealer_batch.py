#!/usr/bin/env python3
"""
DocSealer Batch — Desktop App
Each input file (JPG / PNG / HEIC / PDF / TIFF / …) → one sealed TIFF per page.
Output TIFFs are named originalname_pageN_sealed.tiff
Run: python3 doc_sealer_batch.py
"""

import sys, os, io, math, re, tempfile
from pathlib import Path

# ── PyQt6 ──────────────────────────────────────────────────────────────────
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QListWidget, QListWidgetItem,
    QProgressBar, QFrame, QSizePolicy, QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QDragEnterEvent, QDropEvent

# ── Processing libs ─────────────────────────────────────────────────────────
try:
    from PIL import Image, ImageEnhance, ImageChops
    import img2pdf
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas as rl_canvas
    LIBS_OK = True
except ImportError as e:
    LIBS_OK = False
    LIBS_ERROR = str(e)

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_OK = True
except ImportError:
    HEIC_OK = False

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_OK = True
except ImportError:
    PDF2IMAGE_OK = False

# ── Bundled paths (PyInstaller .exe) ─────────────────────────────────────────
if getattr(sys, 'frozen', False):
    _poppler_path = os.path.join(sys._MEIPASS, 'poppler', 'bin')
    if not os.path.exists(_poppler_path):
        _poppler_path = None
else:
    _poppler_path = None

# ── Constants ───────────────────────────────────────────────────────────────
MAX_TIFF_BYTES   = 5 * 1024 * 1024
RENDER_DPI_START = 150
RENDER_DPI_MIN   = 55
SEAL_MARGIN_PT   = 20
SEAL_OPACITY     = 1.0

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".pdf", ".bmp", ".webp",
                  ".tiff", ".tif", ".heic", ".heif"}

# ── Color Palette ────────────────────────────────────────────────────────────
C = {
    "bg":      "#0F1117",
    "surface": "#1A1D27",
    "card":    "#21253A",
    "accent":  "#4F7AFF",
    "accent2": "#7B5EA7",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "danger":  "#EF4444",
    "text":    "#E8EAF0",
    "muted":   "#6B7280",
    "border":  "#2D3248",
}

STYLE = f"""
QMainWindow, QWidget {{
    background: {C['bg']};
    color: {C['text']};
    font-family: 'Segoe UI', 'SF Pro Display', Helvetica, Arial, sans-serif;
}}
QLabel {{ color: {C['text']}; background: transparent; }}
QPushButton {{
    background: {C['card']};
    color: {C['text']};
    border: 1px solid {C['border']};
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{ background: {C['accent']}; border-color: {C['accent']}; }}
QPushButton:pressed {{ background: #3B5FCC; }}
QPushButton:disabled {{ background: {C['surface']}; color: {C['muted']}; border-color: {C['border']}; }}
QListWidget {{
    background: {C['surface']};
    border: 1px solid {C['border']};
    border-radius: 10px;
    color: {C['text']};
    font-size: 13px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 12px;
    border-radius: 6px;
    margin: 2px 4px;
}}
QListWidget::item:selected {{ background: {C['accent']}; color: white; }}
QListWidget::item:hover:!selected {{ background: {C['card']}; }}
QProgressBar {{
    background: {C['surface']};
    border: 1px solid {C['border']};
    border-radius: 6px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {C['accent']}, stop:1 {C['accent2']});
    border-radius: 6px;
}}
QScrollBar:vertical {{
    background: {C['surface']};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {C['border']};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  Drop Zone
# ═══════════════════════════════════════════════════════════════════════════════
class DropZone(QFrame):
    files_dropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(130)
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)

        self.icon_lbl = QLabel("📂")
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet("font-size: 34px; background: transparent;")

        self.title_lbl = QLabel("Drop files here  or  click to browse")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {C['text']}; background: transparent;")

        self.sub_lbl = QLabel("JPG · PNG · HEIC · PDF · BMP · WEBP · TIFF")
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_lbl.setStyleSheet(
            f"font-size: 11px; color: {C['muted']}; background: transparent;")

        lay.addWidget(self.icon_lbl)
        lay.addWidget(self.title_lbl)
        lay.addWidget(self.sub_lbl)
        self._update_style()

    def _update_style(self):
        border_col = C['accent'] if self._hover else C['border']
        bg_col     = "#1F2640" if self._hover else C['surface']
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg_col};
                border: 2px dashed {border_col};
                border-radius: 14px;
            }}
        """)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._hover = True
            self._update_style()
            self.icon_lbl.setText("📥")

    def dragLeaveEvent(self, e):
        self._hover = False
        self._update_style()
        self.icon_lbl.setText("📂")

    def dropEvent(self, e: QDropEvent):
        self._hover = False
        self._update_style()
        self.icon_lbl.setText("📂")
        paths = [u.toLocalFile() for u in e.mimeData().urls()
                 if Path(u.toLocalFile()).suffix.lower() in SUPPORTED_EXTS]
        if paths:
            self.files_dropped.emit(paths)

    def mousePressEvent(self, e):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Files", "",
            "Documents (*.jpg *.jpeg *.png *.heic *.heif *.pdf *.bmp *.webp *.tiff *.tif)"
        )
        if paths:
            self.files_dropped.emit(paths)


# ═══════════════════════════════════════════════════════════════════════════════
#  Seal Preview
# ═══════════════════════════════════════════════════════════════════════════════
class SealPreview(QLabel):
    seal_loaded = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.seal_path = None
        self.setMinimumSize(100, 100)
        self.setMaximumSize(100, 100)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                background: {C['surface']};
                border: 2px dashed {C['border']};
                border-radius: 50px;
                color: {C['muted']};
                font-size: 11px;
            }}
        """)
        self.setText("No seal\nloaded")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to load your seal image")

    def mousePressEvent(self, e):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Seal Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if path:
            self.load_seal(path)

    def load_seal(self, path: str):
        self.seal_path = path
        pix = QPixmap(path).scaled(
            88, 88,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(pix)
        self.setStyleSheet(f"""
            QLabel {{
                background: {C['surface']};
                border: 2px solid {C['accent']};
                border-radius: 50px;
            }}
        """)
        self.seal_loaded.emit(path)


# ═══════════════════════════════════════════════════════════════════════════════
#  Batch Worker
# ═══════════════════════════════════════════════════════════════════════════════
class BatchWorker(QThread):
    batch_progress = pyqtSignal(int, str)
    page_started   = pyqtSignal(int, int)
    page_done      = pyqtSignal(int, int, float, str)
    page_failed    = pyqtSignal(int, int, str)
    all_done       = pyqtSignal(int, int)

    def __init__(self, input_files: list, seal_path: str, output_folder: str):
        super().__init__()
        self.input_files   = input_files
        self.seal_path     = seal_path
        self.output_folder = Path(output_folder)

    # ── Step 1: Convert any file to PDF bytes ─────────────────────────────────
    def _file_to_pdf_bytes(self, fp: Path) -> bytes:
        if fp.suffix.lower() == ".pdf":
            return fp.read_bytes()

        img = Image.open(fp)

        # Extract ALL frames — critical for multi-frame TIFFs.
        # Single-frame formats (JPG, PNG, BMP, WEBP, HEIC) loop once and exit.
        frames = []
        try:
            while True:
                frame = img.copy()
                if frame.mode not in ("RGB", "L"):
                    frame = frame.convert("RGB")
                frames.append(frame)
                img.seek(img.tell() + 1)
        except EOFError:
            pass

        if not frames:
            # Fallback — should never happen but be safe
            frame = img.convert("RGB") if img.mode not in ("RGB", "L") else img
            frames = [frame]

        tmp_paths = []
        try:
            for frame in frames:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                frame.save(tmp_path, format="PNG")
                tmp_paths.append(tmp_path)
            # img2pdf.convert accepts a list → produces one page per image
            return img2pdf.convert(tmp_paths)
        finally:
            for p in tmp_paths:
                try: os.unlink(p)
                except OSError: pass

    # ── Step 2: Apply seal overlay ────────────────────────────────────────────
    def _make_seal_overlay(self, w_pt: float, h_pt: float,
                           seal_img: Image.Image, rotation: int = 0) -> bytes:
        """
        Create a PDF overlay page containing the seal at the visual bottom-right.

        w_pt, h_pt  — raw PDF page dimensions (from mediabox, NOT swapped)
        rotation    — value of /Rotate key (0, 90, 180, 270)

        Placement in raw PDF coordinates that maps to visual bottom-right:
          Rotate=0   → (w-margin, margin)
          Rotate=90  → (w-margin, margin)
          Rotate=180 → (margin,   h-margin)
          Rotate=270 → (margin,   margin)
        """
        buf = io.BytesIO()
        c   = rl_canvas.Canvas(buf, pagesize=(w_pt, h_pt))

        # Size seal using visual (post-rotation) dimensions
        vis_w = h_pt if rotation in (90, 270) else w_pt
        vis_h = w_pt if rotation in (90, 270) else h_pt
        seal_sz = max(60, min(160, int(min(vis_w, vis_h) * 0.21)))

        if rotation == 180:
            x = SEAL_MARGIN_PT
            y = h_pt - SEAL_MARGIN_PT - seal_sz
        elif rotation == 270:
            x = SEAL_MARGIN_PT
            y = SEAL_MARGIN_PT
        else:
            x = w_pt - SEAL_MARGIN_PT - seal_sz
            y = SEAL_MARGIN_PT

        # Auto-crop solid background from seal image
        rgba = seal_img.convert("RGBA")
        _w, _h = rgba.size
        _px    = rgba.load()
        _corners = [_px[0, 0][:3], _px[_w-1, 0][:3],
                    _px[0, _h-1][:3], _px[_w-1, _h-1][:3]]
        _bg = tuple(sum(ch[i] for ch in _corners) // 4 for i in range(3))
        _bg_img = Image.new("RGB", (_w, _h), _bg)
        _diff   = ImageChops.difference(rgba.convert("RGB"), _bg_img)
        _bbox   = _diff.point(lambda v: 255 if v > 20 else 0).convert("L").getbbox()
        if _bbox:
            pad   = 4
            _bbox = (max(0, _bbox[0]-pad), max(0, _bbox[1]-pad),
                     min(_w, _bbox[2]+pad), min(_h, _bbox[3]+pad))
            rgba  = rgba.crop(_bbox)

        if SEAL_OPACITY < 1.0:
            r, g, b, a = rgba.split()
            a = ImageEnhance.Brightness(a).enhance(SEAL_OPACITY)
            rgba.putalpha(a)

        tmp_seal = io.BytesIO()
        rgba.save(tmp_seal, format="PNG")
        tmp_seal.seek(0)

        c.saveState()
        c.drawImage(rl_canvas.ImageReader(tmp_seal),
                    x, y, seal_sz, seal_sz, mask='auto')
        c.restoreState()
        c.save()
        buf.seek(0)
        return buf.getvalue()

    # ── Filename builder ──────────────────────────────────────────────────────
    @staticmethod
    def _build_filename(fp: Path) -> str:
        return f"{fp.stem}_sealed.tiff"

    # ── Render + save (ONE output file per input, all pages combined) ─────────
    def _render_multipage_tiff(self, fp: Path, sealed_pdf: Path) -> tuple:
        """
        Render every sealed page and combine them into a SINGLE multi-frame
        TIFF (input file → output file, 1:1 — no per-page splitting).
        The whole combined file is kept under MAX_TIFF_BYTES by lowering the
        render DPI for ALL pages together and re-checking total size.
        """
        out_name = self._build_filename(fp)

        out_path = self.output_folder / out_name
        counter  = 1
        base     = out_name.replace(".tiff", "")
        while out_path.exists():
            out_path = self.output_folder / f"{base}_{counter}.tiff"
            counter += 1

        dpi = RENDER_DPI_START
        buf = None
        while dpi >= RENDER_DPI_MIN:
            pages_img = convert_from_path(
                str(sealed_pdf), dpi=dpi, poppler_path=_poppler_path)
            rgb_pages = [p.convert("RGB") for p in pages_img]

            buf = io.BytesIO()
            first, rest = rgb_pages[0], rgb_pages[1:]
            save_kwargs = dict(format="TIFF", compression="jpeg", quality=82,
                                save_all=True)
            if rest:
                save_kwargs["append_images"] = rest
            first.save(buf, **save_kwargs)

            size = buf.tell()
            if size <= MAX_TIFF_BYTES:
                buf.seek(0)
                out_path.write_bytes(buf.getvalue())
                return out_path, size / 1024 / 1024, out_name
            ratio   = MAX_TIFF_BYTES / size
            new_dpi = max(int(dpi * math.sqrt(ratio) * 0.88), RENDER_DPI_MIN)
            if new_dpi >= dpi:
                break
            dpi = new_dpi

        size = buf.tell()
        buf.seek(0)
        out_path.write_bytes(buf.getvalue())
        return out_path, size / 1024 / 1024, out_name

    # ── Main run ──────────────────────────────────────────────────────────────
    def run(self):
        successes = 0
        failures  = 0

        self.batch_progress.emit(0, "Loading seal image…")
        seal_img = Image.open(self.seal_path).convert("RGBA")

        total_pages      = 0
        file_page_counts = []
        for fp in self.input_files:
            try:
                pdf_bytes = self._file_to_pdf_bytes(fp)
                count = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
            except Exception:
                count = 1
            file_page_counts.append(count)
            total_pages += count

        pages_done = 0
        n_files    = len(self.input_files)

        for file_idx, fp in enumerate(self.input_files):
            self.batch_progress.emit(
                int(100 * pages_done / max(total_pages, 1)),
                f"Processing {fp.name}  ({file_idx + 1}/{n_files})…")
            # One result row per input file (output is 1:1 with input now).
            self.page_started.emit(file_idx, 0)
            try:
                pdf_bytes = self._file_to_pdf_bytes(fp)
                rdr       = PdfReader(io.BytesIO(pdf_bytes))
                n_pages   = len(rdr.pages)

                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp    = Path(tmp_dir)
                    writer = PdfWriter()
                    for page_idx, page in enumerate(rdr.pages):
                        self.batch_progress.emit(
                            int(100 * pages_done / max(total_pages, 1)),
                            f"{fp.name} — sealing page {page_idx + 1}/{n_pages}…")
                        pw  = float(page.mediabox.width)
                        ph  = float(page.mediabox.height)
                        rot = int(page.get("/Rotate", 0) or 0)
                        overlay = PdfReader(
                            io.BytesIO(self._make_seal_overlay(pw, ph, seal_img, rot))
                        ).pages[0]
                        page.merge_page(overlay)
                        writer.add_page(page)
                        pages_done += 1

                    sealed_pdf = tmp / "sealed.pdf"
                    with open(str(sealed_pdf), "wb") as fh:
                        writer.write(fh)

                    self.batch_progress.emit(
                        int(100 * pages_done / max(total_pages, 1)),
                        f"{fp.name} — combining {n_pages} page(s) into one TIFF…")
                    try:
                        _, size_mb, display = self._render_multipage_tiff(
                            fp, sealed_pdf)
                        successes += 1
                        self.page_done.emit(file_idx, 0, size_mb, display)
                    except Exception:
                        import traceback
                        failures += 1
                        self.page_failed.emit(
                            file_idx, 0, traceback.format_exc())

            except Exception:
                import traceback
                err = traceback.format_exc()
                failures += 1
                self.page_failed.emit(file_idx, 0, err)
                pages_done += max(file_page_counts[file_idx], 1)

        self.batch_progress.emit(100, "Batch complete.")
        self.all_done.emit(successes, failures)


# ═══════════════════════════════════════════════════════════════════════════════
#  Badge
# ═══════════════════════════════════════════════════════════════════════════════
class Badge(QLabel):
    def __init__(self, text, color):
        super().__init__(text)
        self.setStyleSheet(f"""
            QLabel {{
                background: {color}22;
                color: {color};
                border: 1px solid {color}55;
                border-radius: 10px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DocSealer Batch")
        self.setMinimumSize(700, 820)
        self.resize(740, 880)
        self.setStyleSheet(STYLE)
        self._worker        = None
        self._output_folder = None
        self._build_ui()
        self._check_deps()

    def _check_deps(self):
        issues = []
        if not LIBS_OK:
            issues.append(f"Missing library: {LIBS_ERROR}")
        if not PDF2IMAGE_OK:
            issues.append("Missing: pdf2image  →  pip install pdf2image")
        if not HEIC_OK:
            self.heic_badge.setText("HEIC: off")
            self.heic_badge.setStyleSheet(self.heic_badge.styleSheet().replace(
                C['success'], C['warning']))
        if issues:
            QMessageBox.warning(self, "Missing Dependencies",
                                "\n".join(issues) +
                                "\n\nInstall then restart the app.")

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        lay  = QVBoxLayout(root)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        hdr   = QHBoxLayout()
        title = QLabel("DocSealer Batch")
        title.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {C['text']}; letter-spacing: -0.5px;")
        sub = QLabel("One sealed TIFF per input file · under 5 MB")
        sub.setStyleSheet(f"font-size: 12px; color: {C['muted']};")
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(title)
        title_col.addWidget(sub)

        self.heic_badge = Badge("HEIC: on" if HEIC_OK else "HEIC: off",
                                C['success'] if HEIC_OK else C['warning'])
        size_badge = Badge("< 5 MB per file", C['accent'])

        hdr.addLayout(title_col)
        hdr.addStretch()
        hdr.addWidget(self.heic_badge)
        hdr.addWidget(size_badge)
        lay.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C['border']};")
        lay.addWidget(sep)

        seal_row = QHBoxLayout()
        seal_row.setSpacing(16)
        self.seal_preview = SealPreview()
        self.seal_preview.seal_loaded.connect(self._on_seal_loaded)

        seal_col = QVBoxLayout()
        seal_col.setSpacing(5)
        seal_lbl = QLabel("Your Seal")
        seal_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {C['text']};")
        seal_hint = QLabel("Stamped on every output TIFF.\nPNG with transparency recommended.")
        seal_hint.setStyleSheet(f"font-size: 11px; color: {C['muted']};")
        self.seal_status = QLabel("⚠  No seal loaded")
        self.seal_status.setStyleSheet(f"font-size: 11px; color: {C['warning']};")
        browse_seal_btn = QPushButton("Browse seal…")
        browse_seal_btn.setFixedWidth(120)
        browse_seal_btn.clicked.connect(self._browse_seal)
        seal_col.addWidget(seal_lbl)
        seal_col.addWidget(seal_hint)
        seal_col.addWidget(self.seal_status)
        seal_col.addWidget(browse_seal_btn)
        seal_col.addStretch()

        seal_row.addWidget(self.seal_preview)
        seal_row.addLayout(seal_col)
        seal_row.addStretch()
        lay.addLayout(seal_row)

        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._add_files)
        lay.addWidget(self.drop_zone)

        list_hdr = QHBoxLayout()
        self.file_count_lbl = QLabel("Input files (0)")
        self.file_count_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {C['text']};")
        remove_btn = QPushButton("Remove selected")
        remove_btn.setFixedWidth(140)
        remove_btn.clicked.connect(self._remove_selected)
        clear_btn = QPushButton("Clear all")
        clear_btn.setFixedWidth(90)
        clear_btn.clicked.connect(self._clear_files)
        list_hdr.addWidget(self.file_count_lbl)
        list_hdr.addStretch()
        list_hdr.addWidget(remove_btn)
        list_hdr.addWidget(clear_btn)
        lay.addLayout(list_hdr)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setFixedHeight(130)
        lay.addWidget(self.file_list)

        out_row = QHBoxLayout()
        out_lbl = QLabel("Output folder:")
        out_lbl.setStyleSheet(f"font-size: 12px; color: {C['muted']};")
        self.out_folder_lbl = QLabel("Not set — files will be saved next to input")
        self.out_folder_lbl.setStyleSheet(
            f"font-size: 12px; color: {C['muted']};"
            f"background: {C['surface']}; border-radius: 6px; padding: 6px 10px;")
        self.out_folder_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        browse_out_btn = QPushButton("Browse…")
        browse_out_btn.setFixedWidth(90)
        browse_out_btn.clicked.connect(self._browse_output_folder)
        out_row.addWidget(out_lbl)
        out_row.addWidget(self.out_folder_lbl)
        out_row.addWidget(browse_out_btn)
        lay.addLayout(out_row)

        self.run_btn = QPushButton("▶  Start Batch")
        self.run_btn.setFixedHeight(44)
        self.run_btn.setStyleSheet(
            self.run_btn.styleSheet() +
            f"QPushButton {{ background: {C['accent']}; font-size: 15px; font-weight: 700; }}")
        self.run_btn.clicked.connect(self._run)
        lay.addWidget(self.run_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet(f"font-size: 12px; color: {C['muted']}; padding: 2px;")
        lay.addWidget(self.status_lbl)

        self.summary_frame = QFrame()
        self.summary_frame.setVisible(False)
        sf_lay = QHBoxLayout(self.summary_frame)
        sf_lay.setContentsMargins(16, 10, 16, 10)
        self.summary_lbl = QLabel("")
        sf_lay.addWidget(self.summary_lbl)
        sf_lay.addStretch()
        open_folder_btn = QPushButton("Open output folder")
        open_folder_btn.setFixedWidth(150)
        open_folder_btn.clicked.connect(self._open_folder)
        sf_lay.addWidget(open_folder_btn)
        lay.addWidget(self.summary_frame)

        self.results_header_lbl = QLabel("Results")
        self.results_header_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {C['text']};")
        self.results_header_lbl.setVisible(False)
        lay.addWidget(self.results_header_lbl)

        self.results_list = QListWidget()
        self.results_list.setVisible(False)
        self.results_list.itemClicked.connect(self._on_result_item_clicked)
        lay.addWidget(self.results_list)

    def _on_seal_loaded(self, path: str):
        self.seal_status.setText(f"✅  {Path(path).name}")
        self.seal_status.setStyleSheet(f"font-size: 11px; color: {C['success']};")

    def _browse_seal(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Seal Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.seal_preview.load_seal(path)

    def _add_files(self, paths: list):
        existing = {self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.file_list.count())}
        for p in paths:
            if p in existing or p == self.seal_preview.seal_path:
                continue
            fp   = Path(p)
            item = QListWidgetItem()
            item.setText(
                f"  {fp.name}   ({fp.suffix.upper().lstrip('.')}  ·  {fp.stat().st_size // 1024} KB)")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.file_list.addItem(item)
        self._update_file_count()

    def _remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
        self._update_file_count()

    def _clear_files(self):
        self.file_list.clear()
        self._update_file_count()

    def _update_file_count(self):
        self.file_count_lbl.setText(f"Input files ({self.file_list.count()})")

    def _browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self._output_folder = folder
            self.out_folder_lbl.setText(folder)
            self.out_folder_lbl.setStyleSheet(
                f"font-size: 12px; color: {C['text']};"
                f"background: {C['surface']}; border-radius: 6px; padding: 6px 10px;")

    def _validate(self) -> bool:
        if self.file_list.count() == 0:
            QMessageBox.warning(self, "No Files", "Please add at least one input file.")
            return False
        if not self.seal_preview.seal_path:
            QMessageBox.warning(self, "No Seal", "Please load your seal image first.")
            return False
        if not self._output_folder:
            QMessageBox.warning(self, "No Output Folder", "Please choose an output folder.")
            return False
        return True

    def _run(self):
        if not self._validate():
            return
        files = [Path(self.file_list.item(i).data(Qt.ItemDataRole.UserRole))
                 for i in range(self.file_list.count())]

        self.run_btn.setEnabled(False)
        self.summary_frame.setVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_lbl.setText("Starting batch…")
        self.status_lbl.setStyleSheet(
            f"font-size: 12px; color: {C['muted']}; padding: 2px;")

        self.results_list.clear()
        self._page_items   = {}
        self._file_headers = {}

        for fi, fp in enumerate(files):
            header = QListWidgetItem(f"  📄  {fp.name}")
            header.setForeground(QColor(C['text']))
            header.setFlags(header.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.results_list.addItem(header)
            self._file_headers[fi] = header

        self.results_header_lbl.setVisible(True)
        self.results_list.setVisible(True)

        self._worker = BatchWorker(
            files, self.seal_preview.seal_path, self._output_folder)
        self._worker.batch_progress.connect(self._on_batch_progress)
        self._worker.page_started.connect(self._on_page_started)
        self._worker.page_done.connect(self._on_page_done)
        self._worker.page_failed.connect(self._on_page_failed)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _on_batch_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.status_lbl.setText(msg)

    def _get_or_create_page_item(self, file_idx: int, page_idx: int) -> QListWidgetItem:
        # page_idx is always 0 now — one output file per input file.
        key = (file_idx, page_idx)
        if key in self._page_items:
            return self._page_items[key]
        fp   = Path(self.file_list.item(file_idx).data(Qt.ItemDataRole.UserRole))
        item = QListWidgetItem(
            f"      ⏳  {fp.stem}_sealed.tiff  →  pending…")
        item.setForeground(QColor(C['muted']))
        header_row = self.results_list.row(self._file_headers[file_idx])
        self.results_list.insertItem(header_row + 1 + page_idx, item)
        self._page_items[key] = item
        return item

    def _on_page_started(self, file_idx: int, page_idx: int):
        fp   = Path(self.file_list.item(file_idx).data(Qt.ItemDataRole.UserRole))
        item = self._get_or_create_page_item(file_idx, page_idx)
        item.setText(f"      ⚙️  {fp.stem}_sealed.tiff  →  sealing & rendering…")
        item.setForeground(QColor(C['accent']))
        self.results_list.scrollToItem(item)

    def _on_page_done(self, file_idx: int, page_idx: int,
                      size_mb: float, display: str):
        fp    = Path(self.file_list.item(file_idx).data(Qt.ItemDataRole.UserRole))
        item  = self._get_or_create_page_item(file_idx, page_idx)
        under = size_mb <= 5.0
        icon  = "✅" if under else "⚠️"
        color = C['success'] if under else C['warning']
        name  = display if display else f"{fp.stem}_sealed.tiff"
        item.setText(f"      {icon}  {name}  ({size_mb:.2f} MB)")
        item.setForeground(QColor(color))
        self.results_list.scrollToItem(item)

    def _on_page_failed(self, file_idx: int, page_idx: int, err: str):
        fp   = Path(self.file_list.item(file_idx).data(Qt.ItemDataRole.UserRole))
        item = self._get_or_create_page_item(file_idx, page_idx)
        item.setText(
            f"      ❌  {fp.stem}_sealed.tiff  →  failed (click to see error)")
        item.setForeground(QColor(C['danger']))
        item.setData(Qt.ItemDataRole.UserRole, err)
        self.results_list.scrollToItem(item)

    def _on_result_item_clicked(self, item: QListWidgetItem):
        err = item.data(Qt.ItemDataRole.UserRole)
        if err and "❌" in item.text():
            QMessageBox.critical(self, "Error Details", err)

    def _on_all_done(self, successes: int, failures: int):
        self.run_btn.setEnabled(True)
        total = successes + failures
        if failures == 0:
            color  = C['success']
            msg    = f"✅  All {successes} page(s) sealed successfully."
            border = C['success']
        elif successes == 0:
            color  = C['danger']
            msg    = f"❌  All {failures} page(s) failed."
            border = C['danger']
        else:
            color  = C['warning']
            msg    = f"⚠️  {successes} succeeded, {failures} failed."
            border = C['warning']

        self.summary_lbl.setText(msg)
        self.summary_lbl.setStyleSheet(
            f"font-size: 13px; color: {color}; font-weight: 600;")
        self.summary_frame.setStyleSheet(f"""
            QFrame {{
                background: {border}18;
                border: 1px solid {border}44;
                border-radius: 10px;
            }}""")
        self.summary_frame.setVisible(True)
        self.status_lbl.setText(
            f"Batch complete — {successes}/{total} pages processed.")

    def _open_folder(self):
        if self._output_folder:
            import subprocess
            if sys.platform == "win32":
                os.startfile(self._output_folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self._output_folder])


# ═══════════════════════════════════════════════════════════════════════════════
#  Entry Point
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DocSealer Batch")
    app.setOrganizationName("DocSealer")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
