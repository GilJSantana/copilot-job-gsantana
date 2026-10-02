"""Contratos HTTP (JSON) da API. Isolam o formato público das entidades de domínio."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.domain.models import (
    CandidateProfile,
    CareerHistory,
    CVVersion,
    JobPosting,
    JobSearchCriteria,
    JobSite,
    MatchResult,
    MatchVerdict,
    OutreachChannel,
    OutreachLanguage,
    OutreachMessage,
    WorkMode,
)


class SearchIn(BaseModel):
    search_term: str = Field(min_length=1, max_length=200)
    location: str = Field(default="", max_length=200)
    sites: list[JobSite] = Field(default=[JobSite.LINKEDIN, JobSite.INDEED], min_length=1)
    results_wanted: int = Field(default=20, ge=1, le=100)
    hours_old: int | None = Field(default=72, ge=1)
    remote_only: bool = False

    def to_criteria(self) -> JobSearchCriteria:
        return JobSearchCriteria(
            search_term=self.search_term.strip(),
            location=self.location.strip(),
            sites=tuple(dict.fromkeys(self.sites)),
            results_wanted=self.results_wanted,
            hours_old=self.hours_old,
            remote_only=self.remote_only,
        )


class ListingOut(BaseModel):
    source: JobSite
    url: str


class SalaryOut(BaseModel):
    min_amount: float | None
    max_amount: float | None
    currency: str
    interval: str


class MatchOut(BaseModel):
    score: float
    verdict: MatchVerdict
    keyword_score: float
    llm_score: float | None
    used_llm: bool
    matched_skills: list[str]
    strengths: list[str]
    gaps: list[str]
    rationale: str
    provider: str
    # None quando o perfil não pôde ser carregado para comparar
    is_current: bool | None = None

    @classmethod
    def from_domain(cls, result: MatchResult, profile: CandidateProfile | None) -> "MatchOut":
        return cls(
            score=result.score,
            verdict=result.verdict,
            keyword_score=result.keyword_score,
            llm_score=result.llm_score,
            used_llm=result.used_llm,
            matched_skills=list(result.matched_skills),
            strengths=list(result.strengths),
            gaps=list(result.gaps),
            rationale=result.rationale,
            provider=result.provider,
            is_current=result.is_current_for(profile) if profile else None,
        )


class JobSummaryOut(BaseModel):
    key: str
    title: str
    company: str
    location: str
    work_mode: WorkMode
    source: JobSite
    url: str
    other_listings: list[ListingOut]
    date_posted: date | None
    salary: SalaryOut | None
    job_type: str | None
    is_new: bool = False
    match: MatchOut | None = None

    @classmethod
    def from_domain(
        cls,
        job: JobPosting,
        *,
        match: MatchResult | None = None,
        profile: CandidateProfile | None = None,
        is_new: bool = False,
    ) -> "JobSummaryOut":
        return cls(**_job_fields(job, match, profile, is_new))


class JobDetailOut(JobSummaryOut):
    description: str
    skills: list[str]

    @classmethod
    def from_domain(
        cls,
        job: JobPosting,
        *,
        match: MatchResult | None = None,
        profile: CandidateProfile | None = None,
        is_new: bool = False,
    ) -> "JobDetailOut":
        return cls(
            **_job_fields(job, match, profile, is_new),
            description=job.description,
            skills=list(job.skills),
        )


def _job_fields(
    job: JobPosting,
    match: MatchResult | None,
    profile: CandidateProfile | None,
    is_new: bool,
) -> dict:
    salary = job.salary
    return {
        "key": job.dedup_key,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "work_mode": job.work_mode,
        "source": job.source,
        "url": job.url,
        "other_listings": [ListingOut(source=l.source, url=l.url) for l in job.other_listings],
        "date_posted": job.date_posted,
        "salary": SalaryOut(
            min_amount=salary.min_amount,
            max_amount=salary.max_amount,
            currency=salary.currency,
            interval=salary.interval,
        )
        if salary
        else None,
        "job_type": job.job_type,
        "is_new": is_new,
        "match": MatchOut.from_domain(match, profile) if match else None,
    }


class SearchOut(BaseModel):
    total_fetched: int
    duplicates_removed: int
    new_count: int
    jobs: list[JobSummaryOut]


class ProfileOut(BaseModel):
    full_name: str
    headline: str
    summary: str
    years_of_experience: float
    skills: list[str]
    target_roles: list[str]
    preferred_locations: list[str]
    preferred_work_modes: list[WorkMode]
    languages: list[str]
    fingerprint: str

    @classmethod
    def from_domain(cls, profile: CandidateProfile) -> "ProfileOut":
        return cls(
            full_name=profile.full_name,
            headline=profile.headline,
            summary=profile.summary,
            years_of_experience=profile.years_of_experience,
            skills=list(profile.skills),
            target_roles=list(profile.target_roles),
            preferred_locations=list(profile.preferred_locations),
            preferred_work_modes=list(profile.preferred_work_modes),
            languages=list(profile.languages),
            fingerprint=profile.fingerprint,
        )


class HealthOut(BaseModel):
    status: str
    llm_provider: str


class OutreachIn(BaseModel):
    channel: OutreachChannel
    language: OutreachLanguage = OutreachLanguage.PT
    recipient_name: str | None = Field(default=None, max_length=100)


class OutreachOut(BaseModel):
    channel: OutreachChannel
    language: OutreachLanguage
    subject: str | None
    body: str
    length: int
    max_length: int
    provider: str
    created_at: datetime | None
    # False quando o perfil mudou depois do rascunho: pode citar algo desatualizado
    is_current: bool | None = None

    @classmethod
    def from_domain(
        cls, message: OutreachMessage, profile: CandidateProfile | None = None
    ) -> "OutreachOut":
        return cls(
            channel=message.channel,
            language=message.language,
            subject=message.subject,
            body=message.body,
            length=len(message.body),
            max_length=message.channel.max_length,
            provider=message.provider,
            created_at=message.created_at,
            is_current=message.profile_fingerprint == profile.fingerprint if profile else None,
        )


class CVTailorIn(BaseModel):
    language: OutreachLanguage = OutreachLanguage.PT


class TailoredExperienceOut(BaseModel):
    experience_id: str
    title: str
    company: str
    highlights: list[str]


class CVVersionOut(BaseModel):
    id: str
    job_key: str
    language: OutreachLanguage
    headline: str
    summary: str
    skills: list[str]
    experiences: list[TailoredExperienceOut]
    matched_keywords: list[str]
    template: str
    provider: str
    created_at: datetime | None
    pdf_url: str
    download_name: str
    # False quando o histórico mudou depois desta versão; None se ele não pôde ser lido
    is_current: bool | None = None

    @classmethod
    def from_domain(cls, version: CVVersion, history: CareerHistory | None = None) -> "CVVersionOut":
        cv = version.content
        experiences = []
        for tailored in cv.experiences:
            original = history.experience(tailored.experience_id) if history else None
            experiences.append(
                TailoredExperienceOut(
                    experience_id=tailored.experience_id,
                    # a experiência pode ter sido removida do histórico depois da versão
                    title=original.title if original else "",
                    company=original.company if original else "",
                    highlights=list(tailored.highlights),
                )
            )
        return cls(
            id=version.id,
            job_key=version.job_key,
            language=cv.language,
            headline=cv.headline,
            summary=cv.summary,
            skills=list(cv.skills),
            experiences=experiences,
            matched_keywords=list(cv.matched_keywords),
            template=version.template,
            provider=version.provider,
            created_at=version.created_at,
            pdf_url=f"/api/cvs/{version.id}/pdf",
            download_name=version.download_name,
            is_current=version.is_current_for(history) if history else None,
        )
