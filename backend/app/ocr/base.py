from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float


class OCRProvider(ABC):
    @abstractmethod
    def extract_text(self, image_path: Path) -> OCRResult:
        raise NotImplementedError
