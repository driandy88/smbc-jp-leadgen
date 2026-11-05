from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Run(Base):
    """One retrieval: keywords x selected areas, searched hex by hex."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author: Mapped[str] = mapped_column(String(200))
    mock: Mapped[bool] = mapped_column(Boolean, default=True)
    # queued | running | cancelling | cancelled | done | failed
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str | None] = mapped_column(Text)

    keywords: Mapped[list] = mapped_column(JSON)
    # [{"city": "osaka-shi", "area": "27127"}, ...]; area is an N03 code
    areas: Mapped[list] = mapped_column(JSON)
    base_res: Mapped[int] = mapped_column(Integer)
    max_res: Mapped[int] = mapped_column(Integer)

    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    done_tasks: Mapped[int] = mapped_column(Integer, default=0)
    raw_hits: Mapped[int] = mapped_column(Integer, default=0)
    unique_places: Mapped[int] = mapped_column(Integer, default=0)
    saturated: Mapped[int] = mapped_column(Integer, default=0)
    splits: Mapped[int] = mapped_column(Integer, default=0)
    api_calls: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimate: Mapped[dict | None] = mapped_column(JSON)
    raw_prefix: Mapped[str | None] = mapped_column(String(500))


class RunCell(Base):
    """A hex x keyword search. Base cells are queued up front; split children are added as found."""

    __tablename__ = "run_cells"
    __table_args__ = (Index("ix_run_cells_run_status", "run_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    hex_id: Mapped[str] = mapped_column(String(20))
    res: Mapped[int] = mapped_column(Integer)
    keyword: Mapped[str] = mapped_column(String(200))
    area: Mapped[str] = mapped_column(String(20))
    parent: Mapped[str | None] = mapped_column(String(20))
    # queued | active | done | split | saturated | error
    status: Mapped[str] = mapped_column(String(12), default="queued")
    results: Mapped[int] = mapped_column(Integer, default=0)
    calls: Mapped[int] = mapped_column(Integer, default=0)


class Place(Base):
    """A unique Google place within a run. Re-hits from other hexes/keywords only add to `keywords`/`hits`."""

    __tablename__ = "places"
    __table_args__ = (UniqueConstraint("run_id", "place_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    place_id: Mapped[str] = mapped_column(String(200))
    area: Mapped[str | None] = mapped_column(String(20))
    hex_id: Mapped[str] = mapped_column(String(20))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    hits: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSON)


class RunLog(Base):
    __tablename__ = "run_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text)


class Version(Base):
    """A saved, filtered snapshot of a run."""

    __tablename__ = "versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    filters: Mapped[dict] = mapped_column(JSON)
    place_ids: Mapped[list] = mapped_column(JSON)
    rows: Mapped[int] = mapped_column(Integer)
    export_uri: Mapped[str | None] = mapped_column(String(500))
    analysis: Mapped[dict | None] = mapped_column(JSON)
    # Set on a combined version: {"versions": [source ids], "runs": [every run its places come from]}
    sources: Mapped[dict | None] = mapped_column(JSON)
    # The feature list profile, worked out once (it reads every payload); loaded only when asked for
    features: Mapped[dict | None] = mapped_column(JSON, deferred=True)


class ApiCall(Base):
    """Every billable external call (Places, Vertex), real or mock. The billing panel reads this table."""

    __tablename__ = "api_calls"
    __table_args__ = (Index("ix_api_calls_ts", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    run_id: Mapped[int | None] = mapped_column(Integer, index=True)
    version_id: Mapped[int | None] = mapped_column(Integer)
    # places.searchText | vertex.gemini | vertex.claude
    api: Mapped[str] = mapped_column(String(40))
    sku: Mapped[str] = mapped_column(String(80))
    mock: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(40))
    latency_ms: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float)
    hex_id: Mapped[str | None] = mapped_column(String(20))
    res: Mapped[int | None] = mapped_column(Integer)
    keyword: Mapped[str | None] = mapped_column(String(200))
    page: Mapped[int | None] = mapped_column(Integer)
    results: Mapped[int | None] = mapped_column(Integer)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)


class WebSearch(Base):
    """One run of the website-finder agent over merchants of a version that list no website."""

    __tablename__ = "web_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("versions.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author: Mapped[str] = mapped_column(String(200))
    mock: Mapped[bool] = mapped_column(Boolean, default=True)
    # queued | running | cancelling | cancelled | done | failed
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str | None] = mapped_column(Text)
    workers: Mapped[int] = mapped_column(Integer, default=4)
    area: Mapped[str | None] = mapped_column(String(100))
    total: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    # AgentPrompt.version the run used; 0 = the built-in default
    prompt_version: Mapped[int] = mapped_column(Integer, default=0)


class WebFind(Base):
    """What the agent decided for one merchant: does a website that really belongs to it exist."""

    __tablename__ = "web_finds"
    __table_args__ = (Index("ix_web_finds_search_status", "search_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("web_searches.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[int] = mapped_column(Integer, index=True)
    place_id: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(300))
    # queued | searching | done | error | skipped
    status: Mapped[str] = mapped_column(String(12), default="queued")
    exists: Mapped[bool | None] = mapped_column(Boolean)
    website: Mapped[str | None] = mapped_column(String(1000))
    # own | group (the chain's official store page) — only when exists
    site_type: Mapped[str | None] = mapped_column(String(20))
    social: Mapped[str | None] = mapped_column(String(1000))
    confidence: Mapped[str | None] = mapped_column(String(10))
    reason: Mapped[str | None] = mapped_column(Text)
    queries: Mapped[list | None] = mapped_column(JSON)
    sources: Mapped[list | None] = mapped_column(JSON)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentPrompt(Base):
    """A saved version of the website-finder agent's system prompt; the newest one is used for new runs."""

    __tablename__ = "agent_prompts"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    text: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(String(300), default="")
    author: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
