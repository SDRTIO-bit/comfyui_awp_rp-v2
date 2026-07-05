"""Novel storage interfaces — abstract contracts for novel mode stores.

Implementations must be swappable (SQLite, in-memory for tests).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..contracts.novel_project import NovelProject
from ..contracts.novel_volume import VolumePlan
from ..contracts.novel_chapter import ChapterPlan
from ..contracts.novel_draft import ChapterDraft
from ..contracts.novel_ledger import LedgerItem
from ..contracts.novel_character import NovelCharacter
from ..contracts.novel_batch import BatchProgress
from ..contracts.novel_reference import ReferenceBook


class NovelProjectStore(ABC):
    """Interface for NovelProject persistence."""

    @abstractmethod
    def create(self, project: NovelProject) -> None:
        ...

    @abstractmethod
    def load(self, project_id: str) -> NovelProject | None:
        ...

    @abstractmethod
    def list_all(self) -> list[NovelProject]:
        ...

    @abstractmethod
    def update(self, project: NovelProject) -> None:
        ...

    @abstractmethod
    def delete(self, project_id: str) -> None:
        ...


class NovelVolumeStore(ABC):
    """Interface for VolumePlan persistence."""

    @abstractmethod
    def save(self, volume: VolumePlan) -> None:
        ...

    @abstractmethod
    def load(self, volume_id: str) -> VolumePlan | None:
        ...

    @abstractmethod
    def list_by_project(self, project_id: str) -> list[VolumePlan]:
        ...

    @abstractmethod
    def delete(self, volume_id: str) -> None:
        ...


class NovelChapterPlanStore(ABC):
    """Interface for ChapterPlan persistence."""

    @abstractmethod
    def save(self, plan: ChapterPlan) -> None:
        ...

    @abstractmethod
    def load(self, chapter_id: str) -> ChapterPlan | None:
        ...

    @abstractmethod
    def load_by_index(self, project_id: str, chapter_index: int) -> ChapterPlan | None:
        ...

    @abstractmethod
    def list_by_project(self, project_id: str) -> list[ChapterPlan]:
        ...

    @abstractmethod
    def get_next_index(self, project_id: str) -> int:
        ...


class NovelChapterDraftStore(ABC):
    """Interface for ChapterDraft persistence."""

    @abstractmethod
    def save(self, draft: ChapterDraft) -> None:
        ...

    @abstractmethod
    def load(self, draft_id: str) -> ChapterDraft | None:
        ...

    @abstractmethod
    def load_latest(self, chapter_id: str) -> ChapterDraft | None:
        ...

    @abstractmethod
    def list_by_chapter(self, chapter_id: str) -> list[ChapterDraft]:
        ...


class NovelLedgerStore(ABC):
    """Interface for LedgerItem persistence."""

    @abstractmethod
    def upsert(self, item: LedgerItem) -> None:
        ...

    @abstractmethod
    def load(self, item_id: str) -> LedgerItem | None:
        ...

    @abstractmethod
    def list_by_project(self, project_id: str, section: str = "") -> list[LedgerItem]:
        ...

    @abstractmethod
    def resolve(self, item_id: str) -> None:
        ...

    @abstractmethod
    def search(self, project_id: str, query: str) -> list[LedgerItem]:
        ...


class NovelCharacterStore(ABC):
    """Interface for NovelCharacter persistence."""

    @abstractmethod
    def save(self, character: NovelCharacter) -> None:
        ...

    @abstractmethod
    def load(self, character_id: str) -> NovelCharacter | None:
        ...

    @abstractmethod
    def list_by_project(self, project_id: str) -> list[NovelCharacter]:
        ...

    @abstractmethod
    def delete(self, character_id: str) -> None:
        ...


class NovelBatchProgressStore(ABC):
    """Interface for BatchProgress persistence."""

    @abstractmethod
    def save(self, progress: BatchProgress) -> None:
        ...

    @abstractmethod
    def load(self, batch_id: str) -> BatchProgress | None:
        ...

    @abstractmethod
    def list_by_project(self, project_id: str) -> list[BatchProgress]:
        ...


class NovelReferenceBookStore(ABC):
    """Interface for ReferenceBook persistence."""

    @abstractmethod
    def save(self, book: ReferenceBook) -> None:
        ...

    @abstractmethod
    def load(self, book_id: str) -> ReferenceBook | None:
        ...

    @abstractmethod
    def list_by_project(self, project_id: str) -> list[ReferenceBook]:
        ...

    @abstractmethod
    def delete(self, book_id: str) -> None:
        ...
