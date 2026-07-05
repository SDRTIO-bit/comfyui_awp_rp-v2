"""ComfyUI nodes for Novel Mode — Phase 6.

Provides 8 nodes for novel writing workflow:
- AWPV2NovelProjectCreate: Create novel project
- AWPV2NovelVolumePlan: Create volume plan
- AWPV2NovelChapterPlan: Architect plans a chapter
- AWPV2NovelChapterWrite: Writer generates chapter text
- AWPV2NovelChapterRevise: Revise a chapter
- AWPV2NovelLedgerView: View ledger items
- AWPV2NovelExport: Export to Markdown
- AWPV2NovelBatchWrite: Batch write multiple chapters
"""

from __future__ import annotations

from typing import Any


class AWPV2NovelProjectCreate:
    """Create a novel project."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "title": ("STRING", {"default": ""}),
                "genre": ("STRING", {"default": "玄幻"}),
            },
            "optional": {
                "target_platform": ("STRING", {"default": ""}),
                "target_reader": ("STRING", {"default": ""}),
                "core_emotion": ("STRING", {"default": ""}),
                "one_sentence_pitch": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("NOVEL_PROJECT", "STRING")
    RETURN_NAMES = ("novel_project", "project_id")
    FUNCTION = "execute"
    CATEGORY = "AWP/Novel"

    def execute(self, title: str, genre: str, **kwargs) -> tuple[dict, str]:
        import uuid
        from ..contracts.novel_project import NovelProject
        from ..runtime.runtime_store_factory import RuntimeStoreFactory

        project_id = f"novel-{uuid.uuid4().hex[:8]}"
        project = NovelProject(
            project_id=project_id,
            title=title,
            genre=genre,
            target_platform=kwargs.get("target_platform", ""),
            target_reader=kwargs.get("target_reader", ""),
            core_emotion=kwargs.get("core_emotion", ""),
            one_sentence_pitch=kwargs.get("one_sentence_pitch", ""),
        )

        factory = RuntimeStoreFactory.from_env()
        factory.registry.novel_project_store.create(project)

        return (project.to_dict(), project_id)


class AWPV2NovelVolumePlan:
    """Create a volume plan for a novel project."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "novel_project": ("NOVEL_PROJECT",),
                "title": ("STRING", {"default": ""}),
                "chapter_start": ("INT", {"default": 1, "min": 1}),
                "chapter_end": ("INT", {"default": 10, "min": 1}),
                "core_conflict": ("STRING", {"default": ""}),
            },
            "optional": {
                "emotional_arc": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("VOLUME_PLAN",)
    RETURN_NAMES = ("volume_plan",)
    FUNCTION = "execute"
    CATEGORY = "AWP/Novel"

    def execute(self, novel_project: dict, title: str, chapter_start: int,
                chapter_end: int, core_conflict: str, **kwargs) -> tuple[dict]:
        import uuid
        from ..contracts.novel_volume import VolumePlan
        from ..runtime.runtime_store_factory import RuntimeStoreFactory

        factory = RuntimeStoreFactory.from_env()
        volume_id = f"vol-{uuid.uuid4().hex[:8]}"
        # Compute next volume index
        existing = factory.registry.novel_volume_store.list_by_project(novel_project["project_id"])
        next_index = max((v.index for v in existing), default=0) + 1
        volume = VolumePlan(
            volume_id=volume_id,
            project_id=novel_project["project_id"],
            index=next_index,
            title=title,
            chapter_start=chapter_start,
            chapter_end=chapter_end,
            core_conflict=core_conflict,
            emotional_arc=kwargs.get("emotional_arc", ""),
        )

        factory.registry.novel_volume_store.save(volume)

        return (volume.to_dict(),)


class AWPV2NovelChapterPlan:
    """Architect plans a chapter."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "project_id": ("STRING",),
                "chapter_index": ("INT", {"default": 1, "min": 1}),
            },
            "optional": {
                "task_description": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("CHAPTER_PLAN",)
    RETURN_NAMES = ("chapter_plan",)
    FUNCTION = "execute"
    CATEGORY = "AWP/Novel"

    def execute(self, project_id: str, chapter_index: int, **kwargs) -> tuple[dict]:
        from ..runtime.novel_engine import NovelEngine
        from ..runtime.runtime_store_factory import RuntimeStoreFactory

        factory = RuntimeStoreFactory.from_env()
        engine = NovelEngine(factory.registry)
        plan = engine.plan_chapter(
            project_id=project_id,
            chapter_index=chapter_index,
            task_description=kwargs.get("task_description", ""),
        )

        return (plan.to_dict(),)


class AWPV2NovelChapterWrite:
    """Writer generates chapter text."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "project_id": ("STRING",),
                "chapter_index": ("INT", {"default": 1, "min": 1}),
            },
        }

    RETURN_TYPES = ("CHAPTER_DRAFT", "STRING")
    RETURN_NAMES = ("chapter_draft", "chapter_text")
    FUNCTION = "execute"
    CATEGORY = "AWP/Novel"

    def execute(self, project_id: str, chapter_index: int) -> tuple[dict, str]:
        from ..runtime.novel_engine import NovelEngine
        from ..runtime.runtime_store_factory import RuntimeStoreFactory

        factory = RuntimeStoreFactory.from_env()
        engine = NovelEngine(factory.registry)
        draft = engine.write_chapter(
            project_id=project_id,
            chapter_index=chapter_index,
        )

        return (draft.to_dict(), draft.text)


class AWPV2NovelChapterRevise:
    """Revise a chapter with feedback."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "project_id": ("STRING",),
                "chapter_index": ("INT", {"default": 1, "min": 1}),
            },
            "optional": {
                "feedback": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("CHAPTER_DRAFT", "STRING")
    RETURN_NAMES = ("chapter_draft", "chapter_text")
    FUNCTION = "execute"
    CATEGORY = "AWP/Novel"

    def execute(self, project_id: str, chapter_index: int, **kwargs) -> tuple[dict, str]:
        from ..runtime.novel_engine import NovelEngine
        from ..runtime.runtime_store_factory import RuntimeStoreFactory

        factory = RuntimeStoreFactory.from_env()
        engine = NovelEngine(factory.registry)
        draft = engine.revise_chapter(
            project_id=project_id,
            chapter_index=chapter_index,
            feedback=kwargs.get("feedback", ""),
        )

        return (draft.to_dict(), draft.text)


class AWPV2NovelLedgerView:
    """View ledger items for a novel project."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "project_id": ("STRING",),
            },
            "optional": {
                "section": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("LEDGER_ITEMS", "STRING")
    RETURN_NAMES = ("ledger_items", "summary")
    FUNCTION = "execute"
    CATEGORY = "AWP/Novel"

    def execute(self, project_id: str, **kwargs) -> tuple[list, str]:
        from ..runtime.runtime_store_factory import RuntimeStoreFactory

        factory = RuntimeStoreFactory.from_env()
        section = kwargs.get("section", "")
        items = factory.registry.novel_ledger_store.list_by_project(project_id, section)

        items_dicts = [i.to_dict() for i in items]
        summary = f"{len(items)} 条记录"
        if section:
            summary += f" (section={section})"

        return (items_dicts, summary)


class AWPV2NovelExport:
    """Export novel project to Markdown (placeholder)."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "project_id": ("STRING",),
                "output_dir": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("export_path",)
    FUNCTION = "execute"
    CATEGORY = "AWP/Novel"

    def execute(self, project_id: str, output_dir: str) -> tuple[str]:
        # Placeholder — NovelMarkdownExporter not yet implemented
        return (f"[Export placeholder: {project_id} → {output_dir}]",)


class AWPV2NovelBatchWrite:
    """Batch write multiple chapters."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "project_id": ("STRING",),
                "chapter_start": ("INT", {"default": 1, "min": 1}),
                "chapter_end": ("INT", {"default": 3, "min": 1}),
            },
        }

    RETURN_TYPES = ("CHAPTER_DRAFTS", "STRING")
    RETURN_NAMES = ("chapter_drafts", "summary")
    FUNCTION = "execute"
    CATEGORY = "AWP/Novel"

    def execute(self, project_id: str, chapter_start: int, chapter_end: int) -> tuple[list, str]:
        from ..runtime.novel_engine import NovelEngine
        from ..runtime.runtime_store_factory import RuntimeStoreFactory

        factory = RuntimeStoreFactory.from_env()
        engine = NovelEngine(factory.registry)
        drafts = engine.batch_write(
            project_id=project_id,
            chapter_start=chapter_start,
            chapter_end=chapter_end,
        )

        drafts_dicts = [d.to_dict() for d in drafts]
        summary = f"生成 {len(drafts)} 章 (第{chapter_start}-{chapter_end}章)"

        return (drafts_dicts, summary)
