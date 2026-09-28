"""Tabelas do banco. São detalhes de persistência: o domínio nunca as vê."""

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, MetaData, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Nomes explícitos de constraints: o Alembic precisa deles para alterar
    # tabelas no SQLite (que recria a tabela inteira em "batch mode").
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class JobRow(Base):
    __tablename__ = "jobs"

    # id sequencial preserva a ordem de inserção dentro de uma mesma busca
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dedup_key: Mapped[str] = mapped_column(String(16), unique=True, index=True)

    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str] = mapped_column(String(2000))
    source: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text, default="")
    work_mode: Mapped[str] = mapped_column(String(20))
    job_type: Mapped[str | None] = mapped_column(String(50))
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    external_id: Mapped[str | None] = mapped_column(String(200))
    # [{"source": "indeed", "url": "..."}]: anúncios da mesma vaga em outras fontes
    other_listings: Mapped[list[dict[str, str]]] = mapped_column(
        JSON, default=list, server_default=text("'[]'")
    )
    date_posted: Mapped[date | None] = mapped_column(Date)

    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_currency: Mapped[str | None] = mapped_column(String(10))
    salary_interval: Mapped[str | None] = mapped_column(String(20))

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MatchResultRow(Base):
    __tablename__ = "match_results"

    job_key: Mapped[str] = mapped_column(
        ForeignKey("jobs.dedup_key", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(Float, index=True)
    keyword_score: Mapped[float] = mapped_column(Float)
    llm_score: Mapped[float | None] = mapped_column(Float)
    matched_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    strengths: Mapped[list[str]] = mapped_column(JSON, default=list)
    gaps: Mapped[list[str]] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(100), default="")
    profile_fingerprint: Mapped[str] = mapped_column(String(16), default="", index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutreachRow(Base):
    __tablename__ = "outreach_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_key: Mapped[str] = mapped_column(
        ForeignKey("jobs.dedup_key", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(30))
    language: Mapped[str] = mapped_column(String(5))
    subject: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(100), default="")
    profile_fingerprint: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
