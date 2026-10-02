"""Gerador de PDF do CV (porta `ICVGenerator`) sobre o compilador Typst."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import typst

from app.domain.exceptions import CVRenderError
from app.domain.interfaces import ICVGenerator
from app.domain.models import CareerHistory, TailoredCV

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = Path("templates/cv/ats_base.typ")


class TypstPdfAdapter(ICVGenerator):
    """Compila o template Typst com os dados do CV (passados como JSON em sys.inputs)."""

    def __init__(
        self,
        template_path: Path = DEFAULT_TEMPLATE,
        *,
        pdf_standard: str | None = "ua-1",
        font_paths: tuple[Path, ...] = (),
    ) -> None:
        # falha na subida, não na primeira geração de CV
        if not template_path.is_file():
            raise ValueError(f"Template de CV não encontrado: {template_path}")
        self._template_path = template_path
        self._pdf_standards = [pdf_standard] if pdf_standard else []
        self._font_paths = [str(path) for path in font_paths]

    @property
    def template(self) -> str:
        return self._template_path.stem

    async def generate_pdf(self, history: CareerHistory, cv: TailoredCV) -> bytes:
        data = build_render_data(history, cv)
        # compilação é CPU-bound e síncrona: fora do event loop
        return await asyncio.to_thread(self._compile, data)

    def _compile(self, data: dict[str, Any]) -> bytes:
        try:
            pdf, warnings = typst.compile_with_warnings(
                str(self._template_path),
                sys_inputs={"cv": json.dumps(data, ensure_ascii=False)},
                pdf_standards=self._pdf_standards,
                font_paths=self._font_paths,
            )
        except typst.TypstError as exc:
            raise CVRenderError(f"Falha ao compilar {self._template_path.name}: {exc}") from exc
        for warning in warnings:
            # fontes da lista de preferência ausentes na máquina são esperadas
            logger.debug("Typst: %s", warning.message)
        return pdf


def build_render_data(history: CareerHistory, cv: TailoredCV) -> dict[str, Any]:
    """Monta o JSON esperado pelo template (formato de templates/cv/ats_base.example.json).

    Fatos imutáveis (nome, contato, datas, empresas, formação) vêm do histórico;
    o que é otimizado por vaga (headline, resumo, skills, highlights) vem do CV.
    """
    contact = history.contact
    experiences = []
    for tailored in cv.experiences:
        experience = history.experience(tailored.experience_id)
        if experience is None:
            # o CV é validado antes de chegar aqui; isso indica erro de programação
            raise CVRenderError(f"experiência {tailored.experience_id} não existe no histórico")
        experiences.append(
            {
                "title": experience.title,
                "company": experience.company,
                "location": experience.location,
                "start": experience.start,
                "end": experience.end,
                "highlights": list(tailored.highlights),
            }
        )
    return {
        "lang": cv.language.value,
        "name": history.full_name,
        "headline": cv.headline,
        "contact": {
            "email": contact.email,
            "phone": contact.phone,
            "location": contact.location,
            "linkedin": contact.linkedin,
            "github": contact.github,
            "website": contact.website,
        },
        "summary": cv.summary,
        "skills": list(cv.skills),
        "experiences": experiences,
        "education": [
            {"degree": e.degree, "institution": e.institution, "start": e.start, "end": e.end}
            for e in history.education
        ],
        "certifications": [
            {"name": c.name, "issuer": c.issuer, "year": c.year} for c in history.certifications
        ],
        "languages": list(history.languages),
        "keywords": list(cv.matched_keywords),
    }
