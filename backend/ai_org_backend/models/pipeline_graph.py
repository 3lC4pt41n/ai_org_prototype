"""SQLModel records for persisted PipelineGraph v2 objects."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class PipelineGraphRecord(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "pipeline_graphs"

    id: str = Field(primary_key=True, max_length=100)
    template_family: Optional[str] = Field(default=None, max_length=100)
    intent_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    version: int = Field(default=1)
    checksum: str = Field(max_length=64)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PipelineNodeRecord(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "pipeline_nodes"

    id: str = Field(primary_key=True, max_length=100)
    graph_id: str = Field(foreign_key="pipeline_graphs.id", index=True, max_length=100)
    kind: str = Field(max_length=50)
    capability: str = Field(max_length=255)
    input_schema_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("input_schema", JSON, nullable=False),
    )
    output_schema_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("output_schema", JSON, nullable=False),
    )
    retry_policy_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("retry_policy", JSON, nullable=False),
    )
    timeout_s: int = Field(default=300)
    max_revisions: int = Field(default=0)
    requires_human_approval: bool = Field(default=False)
    cost_budget_json: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column("cost_budget", JSON, nullable=True),
    )
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )


class PipelineEdgeRecord(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "pipeline_edges"

    id: Optional[int] = Field(default=None, primary_key=True)
    graph_id: str = Field(foreign_key="pipeline_graphs.id", index=True, max_length=100)
    source: str = Field(max_length=100)
    target: str = Field(max_length=100)
    condition: Optional[str] = Field(default=None, max_length=500)
    activation: str = Field(default="all", max_length=20)
    edge_type: str = Field(default="control", max_length=30)


class RunRecord(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "runs"

    id: str = Field(primary_key=True, max_length=100)
    graph_id: Optional[str] = Field(default=None, foreign_key="pipeline_graphs.id", index=True)
    state: str = Field(max_length=30)
    current_node: Optional[str] = Field(default=None, max_length=100)
    terminal_reason: Optional[str] = Field(default=None, max_length=500)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)
