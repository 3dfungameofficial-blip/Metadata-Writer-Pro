"""Plugin interface for metadata writers + dynamic registry."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from metadata_writer_pro.app.core.csv_manager import MetadataModel


class MetadataProcessor(ABC):
    """Interface every media processor must implement."""

    name: str = "base"

    @abstractmethod
    def supports(self, file_path: Path) -> bool:
        ...

    @abstractmethod
    def write_metadata(self, file_path: Path, metadata: MetadataModel, *, overwrite: bool = True) -> None:
        ...

    def verify(self, file_path: Path, metadata: MetadataModel) -> bool:
        """Best-effort read-back verification. Default: file still readable."""
        return file_path.is_file() and file_path.stat().st_size > 0


class ProcessorRegistry:
    def __init__(self) -> None:
        self._processors: list[MetadataProcessor] = []

    def register(self, processor: MetadataProcessor) -> None:
        self._processors.append(processor)

    def for_file(self, file_path: Path) -> MetadataProcessor | None:
        for proc in self._processors:
            try:
                if proc.supports(Path(file_path)):
                    return proc
            except Exception:
                continue
        return None

    @property
    def processors(self) -> list[MetadataProcessor]:
        return list(self._processors)


def build_default_registry() -> ProcessorRegistry:
    from metadata_writer_pro.app.metadata.image import ImageMetadataProcessor
    from metadata_writer_pro.app.metadata.video import VideoMetadataProcessor

    reg = ProcessorRegistry()
    reg.register(ImageMetadataProcessor())
    reg.register(VideoMetadataProcessor())
    return reg
