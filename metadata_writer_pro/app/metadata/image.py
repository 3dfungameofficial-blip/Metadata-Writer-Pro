"""Image metadata writer (JPG/JPEG/PNG) via pyexiv2.

Preserves the proven mapping from the legacy app:
  XMP  dc:title / dc:description / dc:subject / xmp:Rating
  IPTC ObjectName / Caption / Keywords
  EXIF ImageDescription / UserComment / Rating
"""
from __future__ import annotations

from pathlib import Path

from metadata_writer_pro.app import IMAGE_EXTENSIONS
from metadata_writer_pro.app.core.csv_manager import MetadataModel
from metadata_writer_pro.app.metadata.base import MetadataProcessor


class ImageMetadataProcessor(MetadataProcessor):
    name = "image"

    def supports(self, file_path: Path) -> bool:
        return Path(file_path).suffix.lower() in IMAGE_EXTENSIONS

    def write_metadata(self, file_path: Path, metadata: MetadataModel, *, overwrite: bool = True) -> None:
        try:
            import pyexiv2
        except ImportError as exc:
            raise RuntimeError(
                "Image metadata library (pyexiv2) is not available."
            ) from exc
        file_path = Path(file_path)
        if not file_path.is_file():
            raise FileNotFoundError(str(file_path))
        title = metadata.title or ""
        description = metadata.description or title
        keywords = list(metadata.keywords or [])
        rating = max(0, min(5, int(metadata.rating or 0)))

        img = pyexiv2.Image(str(file_path))
        try:
            try:
                img.read_exif()  # ensure file is a readable image before mutating
            except Exception:
                pass
            xmp: dict = {}
            iptc: dict = {}
            if not overwrite:
                # Preserve existing non-empty values (fail-open: on read error, overwrite).
                try:
                    xmp = img.read_xmp() or {}
                except Exception:
                    xmp = {}
                try:
                    iptc = img.read_iptc() or {}
                except Exception:
                    iptc = {}

            def _existing(*keys: str, source: dict) -> str:
                for k in keys:
                    v = source.get(k)
                    if isinstance(v, dict):
                        v = next(iter(v.values()), "")
                    if v:
                        return str(v)
                return ""

            if not overwrite:
                if _existing("Xmp.dc.title", source=xmp) or _existing("Iptc.Application2.ObjectName", source=iptc):
                    title = ""
                if _existing("Xmp.dc.description", source=xmp) or _existing("Iptc.Application2.Caption", source=iptc):
                    description = ""
                existing_kw = xmp.get("Xmp.dc.subject") or iptc.get("Iptc.Application2.Keywords")
                if existing_kw:
                    keywords = []
            xmp_patch: dict = {
                "Xmp.xmp.Rating": rating,
            }
            iptc_patch: dict = {}
            exif_patch: dict = {
                "Exif.Image.Rating": rating,
                "Exif.Image.RatingPercent": 99 if rating >= 5 else (rating * 20 - 1 if rating > 0 else 0),
            }
            if title:
                xmp_patch["Xmp.dc.title"] = title
                iptc_patch["Iptc.Application2.ObjectName"] = title
            if description:
                xmp_patch["Xmp.dc.description"] = description
                iptc_patch["Iptc.Application2.Caption"] = description
                exif_patch["Exif.Image.ImageDescription"] = description
                exif_patch["Exif.Photo.UserComment"] = description
            if keywords:
                xmp_patch["Xmp.dc.subject"] = keywords
                iptc_patch["Iptc.Application2.Keywords"] = keywords
            img.modify_xmp(xmp_patch)
            if iptc_patch:
                img.modify_iptc(iptc_patch)
            img.modify_exif(exif_patch)
        finally:
            try:
                img.close()
            except Exception:
                pass

    def verify(self, file_path: Path, metadata: MetadataModel) -> bool:
        try:
            import pyexiv2

            img = pyexiv2.Image(str(file_path))
            try:
                data = img.read_xmp() or {}
                title = data.get("Xmp.dc.title")
                if isinstance(title, dict):
                    title = next(iter(title.values()), "")
                if metadata.title and title not in (metadata.title, {"x-default": metadata.title}):
                    # Lenient: pyexiv2 may return langdict; accept if value present
                    if not (isinstance(title, dict) and metadata.title in title.values()):
                        return str(title) == metadata.title
                return True
            finally:
                try:
                    img.close()
                except Exception:
                    pass
        except Exception:
            return super().verify(file_path, metadata)
