import uuid
from datetime import date
from sqlalchemy import String, Date, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimeStampedModel


class PresidentialMandate(TimeStampedModel):
    __tablename__ = "presidential_mandates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fim: Mapped[date] = mapped_column(Date, nullable=True)
    partido: Mapped[str] = mapped_column(String(50), nullable=False)
    foto_url: Mapped[str] = mapped_column(String(500), nullable=True)

    indicadores = relationship("MandateIndicator", back_populates="mandate", cascade="all, delete-orphan")


class MandateIndicator(TimeStampedModel):
    __tablename__ = "mandate_indicators"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("presidential_mandates.id", ondelete="CASCADE"), nullable=False)
    chave_indicador: Mapped[str] = mapped_column(String(100), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    data_medicao: Mapped[date] = mapped_column(Date, nullable=False)

    mandate = relationship("PresidentialMandate", back_populates="indicadores")
