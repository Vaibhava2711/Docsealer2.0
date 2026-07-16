# DocSealer Batch

A desktop app that takes any number of input documents (JPG, PNG, HEIC, BMP,
WEBP, TIFF, or PDF — including multi-page/multi-frame files), stamps your
seal image on the visual bottom-right of **every page**, and produces
**exactly one sealed, multi-frame TIFF per input file** — automatically
compressed to stay under 5 MB.

- 2 input files in → 2 output TIFF files out (regardless of page count).
- Seal placement is rotation-aware: it always lands bottom-right visually,
  even on pages with `/Rotate` 90°/180°/270° set.

## Features

- Drag-and-drop or click-to-browse file picker
- Multi-format input support: JPG, JPEG, PNG, BMP, WEBP, TIFF/TIF (multi-frame),
  HEIC/HEIF, PDF
- Seal image auto-crops its own background and is stamped at a consistent
  size/position on every page
- Combined multi-page output is iteratively re-rendered at a lower DPI until
  it fits under 5 MB
- Live per-file progress, results list, and error details on failure
- Dark-themed UI

## Requirements

- Python 3.10+
- [Poppler](https://poppler.freedesktop.org/) installed and on your `PATH`
  (needed by `pdf2image` to rasterize PDF pages)
  - **Windows:** download a prebuilt Poppler zip (e.g. from
    [oschwartz10612/poppler-windows releases](https://github.com/oschwartz10612/poppler-windows/releases)),
    extract it, and add its `Library/bin` (or `bin`) folder to your `PATH` —
    or see the "Building the .exe" section below to bundle it directly.
  - **macOS:** `brew install poppler`
  - **Linux:** `sudo apt install poppler-utils` (Debian/Ubuntu) or your
    distro's equivalent

## Setup (run from source)

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 doc_sealer_batch.py
```

## Usage

1. Load your seal image (click the circular seal preview or "Browse seal…").
2. Drag in the files you want sealed (or click the drop zone to browse).
3. Choose an output folder.
4. Click **Start Batch**.
5. Each input file produces one `<originalname>_sealed.tiff` in the output
   folder, with the seal stamped on every page and the whole file kept under
   5 MB.

## Building the Windows .exe

There are two ways to get a `.exe`: **locally** with PyInstaller, or
**automatically via GitHub Actions** (recommended — no local Windows machine
needed).

### Option A: Build via GitHub Actions (no local Windows machine needed)

This repo includes `.github/workflows/build-exe.yml`, which runs on GitHub's
own Windows runners and does everything for you:

1. Push this repo to GitHub (see the "Push to GitHub" steps at the bottom of
   this README).
2. GitHub Actions will automatically:
   - Install Python + dependencies
   - Download a Windows Poppler build and bundle it into the app (so end
     users don't need Poppler installed separately)
   - Run PyInstaller and zip the result
3. **Get the build:**
   - **Every push to `main`** → go to the **Actions** tab on GitHub → open
     the latest run → download the `DocSealerBatch-windows` artifact from
     the "Artifacts" section at the bottom of the run summary.
   - **Tagged releases** → push a version tag, and the workflow will also
     attach the zip directly to a GitHub Release:
     ```bash
     git tag v1.0.0
     git push origin v1.0.0
     ```
     Then check the **Releases** page of your repo.
4. You can also trigger a build manually any time: go to **Actions** →
   **Build Windows EXE** → **Run workflow**.

If the Poppler version pinned in the workflow (`POPPLER_VERSION` near the
top of `build-exe.yml`) ever goes stale/unavailable, just bump it to a
current release tag from
[oschwartz10612/poppler-windows releases](https://github.com/oschwartz10612/poppler-windows/releases).

### Option B: Build locally

This project also ships with a ready-to-use PyInstaller spec (`build.spec`)
for building on your own Windows machine.

#### 1. (Optional but recommended) Bundle Poppler into the exe

So end users don't need to install Poppler themselves:

1. Download a Windows Poppler build, e.g. from
   [oschwartz10612/poppler-windows releases](https://github.com/oschwartz10612/poppler-windows/releases).
2. Extract it, and copy its `bin` folder into this project as:
   ```
   docsealer-batch/
     poppler/
       bin/
         pdftoppm.exe
         pdfinfo.exe
         ... (other poppler binaries/DLLs)
   ```
3. `build.spec` automatically detects and bundles this `poppler/` folder if
   it's present at build time. (It's excluded from git via `.gitignore`
   since it's a large platform-specific binary — download it fresh on
   whichever machine you build the exe on, or remove it from `.gitignore`
   if you'd rather commit it.)

If you skip this step, the exe will still work as long as Poppler is
installed and on the `PATH` of whichever machine runs it.

#### 2. Build

On Windows, from the project root:

```bat
build_windows.bat
```

Or manually:

```bash
pip install -r requirements.txt
pip install pyinstaller
pyinstaller build.spec --noconfirm
```

The finished executable will be at `dist/DocSealerBatch/DocSealerBatch.exe`.
Zip up the whole `dist/DocSealerBatch/` folder when distributing it — the
`.exe` alone won't include its bundled dependencies.

## Push to GitHub

```bash
cd docsealer-batch
git init
git add .
git commit -m "Initial commit: DocSealer Batch"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

Once pushed, the `build-exe.yml` workflow kicks in automatically — check
the **Actions** tab on your repo to watch it build.

## Project structure

```
docsealer-batch/
├── .github/
│   └── workflows/
│       └── build-exe.yml   # GitHub Actions: builds the exe on every push/tag
├── doc_sealer_batch.py     # main application
├── requirements.txt        # Python dependencies
├── build.spec              # PyInstaller build config
├── build_windows.bat       # one-step local Windows exe build script
├── .gitignore
└── README.md
```

## Notes

- Output naming: if `<name>_sealed.tiff` already exists in the output
  folder, a numeric suffix is appended (`<name>_sealed_1.tiff`, etc.) so
  existing files are never overwritten.
- Very large or very high-page-count input files may take a bit longer to
  render at start (multiple DPI passes) if the initial render exceeds 5 MB.
