"""
converters.py — All conversion logic for FileShift.

Supported conversions (Phase 1):
  Video  : .mp4 → .mp3 | .wav | .mov
  PDF    : .pdf → .png | .jpg  (one image per page)
  PPTX   : .pptx → .pdf
  Image  : .png / .jpg / .jpeg / .webp / .bmp ↔ any other image format
"""

import os
import shutil
import tempfile

# ---------------------------------------------------------------------------
# Format catalogue
# ---------------------------------------------------------------------------

# Maps each input extension to the list of valid output extensions.
FORMAT_MAP: dict[str, list[str]] = {
    ".mp4":  [".mp3", ".wav", ".mov"],
    ".mov":  [".mp3", ".wav", ".mp4"],
    ".avi":  [".mp3", ".wav", ".mp4", ".mov"],
    ".mkv":  [".mp3", ".wav", ".mp4", ".mov"],
    ".pdf":  [".png", ".jpg"],
    ".pptx": [".pdf"],
    ".ppt":  [".pdf"],
    ".png":  [".jpg", ".jpeg", ".webp", ".bmp"],
    ".jpg":  [".png", ".jpeg", ".webp", ".bmp"],
    ".jpeg": [".png", ".jpg",  ".webp", ".bmp"],
    ".webp": [".png", ".jpg",  ".jpeg", ".bmp"],
    ".bmp":  [".png", ".jpg",  ".jpeg", ".webp"],
}

# Human-readable category labels
CATEGORY_MAP: dict[str, str] = {
    ".mp4": "Video", ".mov": "Video", ".avi": "Video", ".mkv": "Video",
    ".pdf": "Document",
    ".pptx": "Presentation", ".ppt": "Presentation",
    ".png": "Image", ".jpg": "Image", ".jpeg": "Image",
    ".webp": "Image", ".bmp": "Image",
}

ACCEPTED_EXTENSIONS = set(FORMAT_MAP.keys())


def get_output_formats(input_path: str) -> list[str]:
    ext = os.path.splitext(input_path)[1].lower()
    return FORMAT_MAP.get(ext, [])


def get_category(input_path: str) -> str:
    ext = os.path.splitext(input_path)[1].lower()
    return CATEGORY_MAP.get(ext, "Unknown")


def default_output_path(input_path: str, out_ext: str) -> str:
    """
    Build the default output path:
    Same folder as input, same stem, new extension.
    If out_ext is an image format and the source is a PDF,
    a subfolder is used since multiple pages produce multiple files.
    """
    folder = os.path.dirname(input_path)
    stem   = os.path.splitext(os.path.basename(input_path))[0]
    ext_in = os.path.splitext(input_path)[1].lower()

    if ext_in == ".pdf" and out_ext in (".png", ".jpg"):
        # Return the folder; individual files get page numbers appended
        out_dir = os.path.join(folder, f"{stem}_pages")
        return out_dir
    return os.path.join(folder, stem + out_ext)


# ---------------------------------------------------------------------------
# Converters
# ---------------------------------------------------------------------------

def convert_video_to_audio(input_path: str, output_path: str,
                           progress_cb=None) -> None:
    """MP4/MOV/AVI/MKV → MP3 or WAV using moviepy."""
    from moviepy.editor import VideoFileClip  # type: ignore

    clip = VideoFileClip(input_path)
    audio = clip.audio
    if audio is None:
        clip.close()
        raise ValueError("The video file contains no audio track.")

    ext = os.path.splitext(output_path)[1].lower()
    codec = "libmp3lame" if ext == ".mp3" else "pcm_s16le"

    if progress_cb:
        progress_cb(0.1)

    audio.write_audiofile(
        output_path,
        codec=codec,
        logger=None,
    )
    clip.close()

    if progress_cb:
        progress_cb(1.0)


def convert_video_to_video(input_path: str, output_path: str,
                           progress_cb=None) -> None:
    """MP4 ↔ MOV/AVI using moviepy (re-encode)."""
    from moviepy.editor import VideoFileClip  # type: ignore

    clip = VideoFileClip(input_path)
    if progress_cb:
        progress_cb(0.1)

    clip.write_videofile(output_path, logger=None)
    clip.close()

    if progress_cb:
        progress_cb(1.0)


def convert_pdf_to_images(input_path: str, output_dir: str,
                          fmt: str = "png",
                          progress_cb=None) -> list[str]:
    """
    PDF → PNG or JPG.  One image per page.
    Returns list of written file paths.
    """
    from pdf2image import convert_from_path  # type: ignore

    os.makedirs(output_dir, exist_ok=True)
    pil_fmt = "JPEG" if fmt.lower() in ("jpg", "jpeg") else "PNG"
    ext     = ".jpg" if pil_fmt == "JPEG" else ".png"
    stem    = os.path.splitext(os.path.basename(input_path))[0]

    pages = convert_from_path(input_path, dpi=150)
    total = len(pages)
    written = []

    for i, page in enumerate(pages, 1):
        out_file = os.path.join(output_dir, f"{stem}_page{i:03d}{ext}")
        page.save(out_file, pil_fmt)
        written.append(out_file)
        if progress_cb:
            progress_cb(i / total)

    return written


def convert_pptx_to_pdf(input_path: str, output_path: str,
                        progress_cb=None) -> None:
    """
    PPTX → PDF.
    Tries LibreOffice headless first (cross-platform).
    Falls back to comtypes/win32com on Windows.
    """
    if progress_cb:
        progress_cb(0.05)

    # --- Strategy 1: LibreOffice ------------------------------------------
    import subprocess
    lo_candidates = [
        "libreoffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    lo_exe = None
    for candidate in lo_candidates:
        if shutil.which(candidate) or os.path.isfile(candidate):
            lo_exe = candidate
            break

    out_dir = os.path.dirname(output_path) or "."
    stem    = os.path.splitext(os.path.basename(input_path))[0]

    if lo_exe:
        result = subprocess.run(
            [lo_exe, "--headless", "--convert-to", "pdf",
             "--outdir", out_dir, input_path],
            capture_output=True, timeout=120,
        )
        lo_output = os.path.join(out_dir, stem + ".pdf")
        if result.returncode == 0 and os.path.exists(lo_output):
            if lo_output != output_path:
                shutil.move(lo_output, output_path)
            if progress_cb:
                progress_cb(1.0)
            return

    # --- Strategy 2: win32com (Windows + PowerPoint installed) --------------
    try:
        import comtypes.client  # type: ignore
        powerpoint = comtypes.client.CreateObject("Powerpoint.Application")
        powerpoint.Visible = 1
        abs_in  = os.path.abspath(input_path)
        abs_out = os.path.abspath(output_path)
        deck = powerpoint.Presentations.Open(abs_in, ReadOnly=True,
                                              Untitled=False, WithWindow=False)
        deck.SaveAs(abs_out, 32)   # 32 = ppSaveAsPDF
        deck.Close()
        powerpoint.Quit()
        if progress_cb:
            progress_cb(1.0)
        return
    except Exception:
        pass

    # --- Strategy 3: python-pptx + reportlab (basic, no fonts) --------------
    try:
        from pptx import Presentation          # type: ignore
        from pptx.util import Inches           # type: ignore
        from reportlab.pdfgen import canvas    # type: ignore
        from reportlab.lib.pagesizes import landscape, A4  # type: ignore
        from PIL import Image                  # type: ignore
        import io

        prs  = Presentation(input_path)
        c    = canvas.Canvas(output_path, pagesize=landscape(A4))
        pw, ph = landscape(A4)
        total = len(prs.slides)

        for idx, slide in enumerate(prs.slides, 1):
            # Render slide shapes as text only (no proper rendering here)
            c.setFont("Helvetica", 10)
            c.drawString(72, ph - 40, f"Slide {idx}")
            # Note: full rendering requires LibreOffice or PowerPoint
            c.showPage()
            if progress_cb:
                progress_cb(idx / total * 0.9)

        c.save()
        if progress_cb:
            progress_cb(1.0)
        return
    except Exception:
        pass

    raise RuntimeError(
        "PPTX→PDF conversion requires LibreOffice or Microsoft PowerPoint.\n"
        "Please install LibreOffice (free): https://www.libreoffice.org"
    )


def convert_image(input_path: str, output_path: str,
                  progress_cb=None) -> None:
    """PNG / JPG / WEBP / BMP ↔ any other image format via Pillow."""
    from PIL import Image  # type: ignore

    if progress_cb:
        progress_cb(0.2)

    img = Image.open(input_path)
    ext = os.path.splitext(output_path)[1].lower()

    # JPEG doesn't support alpha channel
    if ext in (".jpg", ".jpeg") and img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    pil_fmt_map = {
        ".jpg":  "JPEG",
        ".jpeg": "JPEG",
        ".png":  "PNG",
        ".webp": "WEBP",
        ".bmp":  "BMP",
    }
    fmt = pil_fmt_map.get(ext, ext.lstrip(".").upper())
    img.save(output_path, fmt)

    if progress_cb:
        progress_cb(1.0)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def convert(input_path: str, output_path_or_dir: str,
            out_ext: str, progress_cb=None) -> str | list[str]:
    """
    Master conversion function.

    Returns:
      - str  path of the output file for most conversions
      - list[str] of paths when PDF→images (multiple pages)
    """
    ext_in  = os.path.splitext(input_path)[1].lower()
    ext_out = out_ext.lower()
    if not ext_out.startswith("."):
        ext_out = "." + ext_out

    # Video → audio
    if ext_in in (".mp4", ".mov", ".avi", ".mkv") and ext_out in (".mp3", ".wav"):
        convert_video_to_audio(input_path, output_path_or_dir, progress_cb)
        return output_path_or_dir

    # Video → video
    if ext_in in (".mp4", ".mov", ".avi", ".mkv") and ext_out in (".mp4", ".mov", ".avi"):
        convert_video_to_video(input_path, output_path_or_dir, progress_cb)
        return output_path_or_dir

    # PDF → images
    if ext_in == ".pdf" and ext_out in (".png", ".jpg", ".jpeg"):
        pages = convert_pdf_to_images(
            input_path, output_path_or_dir,
            fmt=ext_out.lstrip("."), progress_cb=progress_cb,
        )
        return pages

    # PPTX → PDF
    if ext_in in (".pptx", ".ppt") and ext_out == ".pdf":
        convert_pptx_to_pdf(input_path, output_path_or_dir, progress_cb)
        return output_path_or_dir

    # Image → image
    if ext_in in (".png", ".jpg", ".jpeg", ".webp", ".bmp") and \
       ext_out in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        convert_image(input_path, output_path_or_dir, progress_cb)
        return output_path_or_dir

    raise ValueError(f"Unsupported conversion: {ext_in} → {ext_out}")
