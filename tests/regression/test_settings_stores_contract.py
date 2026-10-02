"""Contrato dos stores do painel: rodam contra o SQLite real e contra os dublês em memória."""

import pytest

from app.domain.exceptions import ProfileBlockNotFoundError
from app.domain.interfaces import IProfileBlockStore, IPromptTemplateStore, ISystemConfigStore
from app.domain.models import ProfileBlock, ProfileBlockCategory, PromptName, PromptTemplate
from app.repositories.profile_block_store import SqlAlchemyProfileBlockStore
from app.repositories.prompt_template_store import SqlAlchemyPromptTemplateStore
from app.repositories.system_config_store import SqlAlchemySystemConfigStore
from tests.doubles import InMemoryProfileBlockStore, InMemoryPromptTemplateStore, InMemorySystemConfigStore

pytestmark = pytest.mark.regression


@pytest.fixture(params=["sqlite", "in_memory"])
def configs(request, session_factory) -> ISystemConfigStore:
    if request.param == "sqlite":
        return SqlAlchemySystemConfigStore(session_factory)
    return InMemorySystemConfigStore()


@pytest.fixture(params=["sqlite", "in_memory"])
def blocks(request, session_factory) -> IProfileBlockStore:
    if request.param == "sqlite":
        return SqlAlchemyProfileBlockStore(session_factory)
    return InMemoryProfileBlockStore()


@pytest.fixture(params=["sqlite", "in_memory"])
def prompts(request, session_factory) -> IPromptTemplateStore:
    if request.param == "sqlite":
        return SqlAlchemyPromptTemplateStore(session_factory)
    return InMemoryPromptTemplateStore()


# --- system_configs -------------------------------------------------------------------


async def test_configs_are_read_by_prefix(configs):
    await configs.set_many({"llm.provider": "ollama", "llm.ollama_model": "llama3.1", "scrapers.x": "1"})

    assert await configs.get_many("llm.") == {"llm.provider": "ollama", "llm.ollama_model": "llama3.1"}
    assert await configs.get_many("nada.") == {}


async def test_saving_a_key_again_replaces_its_value(configs):
    await configs.set_many({"llm.provider": "ollama"})
    await configs.set_many({"llm.provider": "gemini"})

    assert await configs.get_many("llm.provider") == {"llm.provider": "gemini"}


async def test_prefix_wildcards_are_literal(configs):
    """`_` e `%` são curingas do LIKE: o prefixo precisa casar literalmente."""
    await configs.set_many({"a_b.x": "1", "aXb.x": "2", "a%c": "3"})

    assert await configs.get_many("a_b.") == {"a_b.x": "1"}
    assert await configs.get_many("a%") == {"a%c": "3"}


async def test_values_keep_unicode_and_line_breaks(configs):
    value = '{"summary": "Engenharia de dados\\ncom +20 anos — São Paulo"}'
    await configs.set_many({"profile.details": value})

    assert (await configs.get_many("profile."))["profile.details"] == value


# --- profile_core ---------------------------------------------------------------------


def skill(title: str, **overrides) -> ProfileBlock:
    return ProfileBlock(category=ProfileBlockCategory.SKILL, title=title, **overrides)


async def test_new_blocks_get_an_id_and_timestamp(blocks):
    saved = await blocks.save(skill("Python"))

    assert saved.id is not None
    assert saved.updated_at is not None and saved.updated_at.tzinfo is not None
    assert await blocks.get(saved.id) == saved


async def test_blocks_are_listed_in_insertion_order_and_by_category(blocks):
    python = await blocks.save(skill("Python"))
    metric = await blocks.save(ProfileBlock(category=ProfileBlockCategory.METRIC, title="20TB no S3", content="AWS"))
    sql = await blocks.save(skill("SQL"))

    assert [b.id for b in await blocks.list_all()] == [python.id, metric.id, sql.id]
    assert [b.title for b in await blocks.list_all(ProfileBlockCategory.SKILL)] == ["Python", "SQL"]
    assert await blocks.list_all(ProfileBlockCategory.EXPERIENCE) == []


async def test_saving_an_existing_block_updates_it(blocks):
    saved = await blocks.save(skill("Pyhton"))

    updated = await blocks.save(skill("Python", id=saved.id, is_active=False))

    assert updated.id == saved.id
    assert updated.updated_at > saved.updated_at
    stored = await blocks.get(saved.id)
    assert (stored.title, stored.is_active) == ("Python", False)
    assert len(await blocks.list_all()) == 1


async def test_updating_or_deleting_a_missing_block_fails(blocks):
    with pytest.raises(ProfileBlockNotFoundError):
        await blocks.save(skill("Python", id=999))
    with pytest.raises(ProfileBlockNotFoundError):
        await blocks.delete(999)
    assert await blocks.get(999) is None


async def test_delete_removes_only_that_block(blocks):
    python = await blocks.save(skill("Python"))
    sql = await blocks.save(skill("SQL"))

    await blocks.delete(python.id)

    assert [b.id for b in await blocks.list_all()] == [sql.id]


async def test_add_many_inserts_all_blocks(blocks):
    await blocks.add_many([skill("Python"), skill("SQL"), skill("AWS", is_active=False)])

    stored = await blocks.list_all()
    assert [(b.title, b.is_active) for b in stored] == [("Python", True), ("SQL", True), ("AWS", False)]
    assert len({b.id for b in stored}) == 3


# --- prompt_templates -----------------------------------------------------------------


async def test_prompts_are_saved_replaced_and_deleted(prompts):
    assert await prompts.get(PromptName.MATCH_ENGINE) is None

    await prompts.save(PromptTemplate(name=PromptName.MATCH_ENGINE, template_text="v1"))
    saved = await prompts.save(PromptTemplate(name=PromptName.MATCH_ENGINE, template_text="v2", is_active=False))

    stored = await prompts.get(PromptName.MATCH_ENGINE)
    assert (stored.template_text, stored.is_active) == ("v2", False)
    assert stored.updated_at == saved.updated_at
    assert await prompts.get(PromptName.CV_TAILOR) is None

    await prompts.delete(PromptName.MATCH_ENGINE)
    await prompts.delete(PromptName.MATCH_ENGINE)  # idempotente
    assert await prompts.get(PromptName.MATCH_ENGINE) is None
