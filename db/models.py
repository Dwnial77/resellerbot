from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Panel(Base):
    """3x-ui panel connection (one physical panel per row)."""

    __tablename__ = "panels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sub_public_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_vision_flow: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_reseller_group: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    resellers: Mapped[list["Reseller"]] = relationship(back_populates="panel")
    reseller_assignments: Mapped[list["ResellerPanel"]] = relationship(
        back_populates="panel"
    )


class Reseller(Base):
    __tablename__ = "resellers"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    panel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("panels.id"), nullable=False, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quota_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lifetime_allocated_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    allowed_inbound_ids: Mapped[str] = mapped_column(String(255), nullable=False)
    attach_inbound_ids: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_clients: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    panel: Mapped["Panel"] = relationship(back_populates="resellers")
    clients: Mapped[list["ClientRecord"]] = relationship(back_populates="reseller")
    panel_assignments: Mapped[list["ResellerPanel"]] = relationship(
        back_populates="reseller"
    )


class ResellerPanel(Base):
    """Per-panel quota, inbounds, and limits for a reseller."""

    __tablename__ = "reseller_panels"

    reseller_tg_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("resellers.telegram_id"),
        primary_key=True,
    )
    panel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("panels.id"), primary_key=True, index=True
    )
    quota_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lifetime_allocated_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    allowed_inbound_ids: Mapped[str] = mapped_column(String(255), nullable=False)
    attach_inbound_ids: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_clients: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    reseller: Mapped["Reseller"] = relationship(back_populates="panel_assignments")
    panel: Mapped["Panel"] = relationship(back_populates="reseller_assignments")


class ClientRecord(Base):
    __tablename__ = "client_records"
    __table_args__ = (
        UniqueConstraint("panel_id", "email", name="uq_client_panel_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reseller_tg_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("resellers.telegram_id"), nullable=False, index=True
    )
    panel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("panels.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(128), nullable=False)
    sub_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inbound_ids: Mapped[str] = mapped_column(String(64), nullable=False)
    allocated_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expiry_time: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    reseller: Mapped["Reseller"] = relationship(back_populates="clients")


class UsageAlertSent(Base):
    """Tracks which usage thresholds were already notified (avoid duplicate alerts)."""

    __tablename__ = "usage_alert_sent"
    __table_args__ = (
        UniqueConstraint(
            "reseller_tg_id",
            "alert_kind",
            "client_email",
            "threshold_percent",
            name="uq_usage_alert",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reseller_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    alert_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    client_email: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    threshold_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ServiceTemplate(Base):
    """Global service presets (volume + expiry) for one-click reseller create."""

    __tablename__ = "service_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    volume_gb: Mapped[float] = mapped_column(Float, nullable=False)
    expiry_days: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
