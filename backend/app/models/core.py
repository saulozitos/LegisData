"""Mapeamento ORM do schema `core` (identidade e vida política) e do `ref`. As tabelas são criadas pelas migrações."""

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import DATERANGE, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import MigratedBase


class Midia(MigratedBase):
    __tablename__ = "midia"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(Text)
    url_origem: Mapped[str] = mapped_column(Text)


class Partido(MigratedBase):
    __tablename__ = "partido"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sigla: Mapped[str] = mapped_column(Text)
    sigla_normalizada: Mapped[str] = mapped_column(Text)
    nome: Mapped[str] = mapped_column(Text)
    numero_eleitoral: Mapped[Optional[int]] = mapped_column(Integer)
    cor_hex: Mapped[Optional[str]] = mapped_column(String(7))
    logo_midia_id: Mapped[Optional[int]] = mapped_column(ForeignKey("core.midia.id"))
    catalogo: Mapped[bool] = mapped_column(Boolean)
    linhagem_id: Mapped[Optional[int]] = mapped_column(ForeignKey("core.partido.id"))

    logo: Mapped[Optional[Midia]] = relationship(lazy="joined")


class Pessoa(MigratedBase):
    __tablename__ = "pessoa"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    nome_exibicao: Mapped[str] = mapped_column(Text)
    data_nascimento: Mapped[Optional[date]] = mapped_column(Date)
    foto_midia_id: Mapped[Optional[int]] = mapped_column(ForeignKey("core.midia.id"))
    redes_sociais: Mapped[Optional[dict]] = mapped_column(JSONB)

    foto: Mapped[Optional[Midia]] = relationship(lazy="joined")

    @property
    def foto_url(self) -> Optional[str]:
        return self.foto.url_origem if self.foto else None


class Entidade(MigratedBase):
    __tablename__ = "entidade"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(primary_key=True)
    categoria: Mapped[str] = mapped_column(Text)
    nome: Mapped[str] = mapped_column(Text)


class Mandato(MigratedBase):
    __tablename__ = "mandato"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    pessoa_id: Mapped[int] = mapped_column(ForeignKey("core.pessoa.id"))
    cargo_id: Mapped[int] = mapped_column(SmallInteger)
    circunscricao_id: Mapped[int] = mapped_column(SmallInteger)
    partido_id: Mapped[Optional[int]] = mapped_column(ForeignKey("core.partido.id"))
    condicao: Mapped[str] = mapped_column(Text)
    inicio: Mapped[date] = mapped_column(Date)
    fim: Mapped[Optional[date]] = mapped_column(Date)
    motivo_encerramento: Mapped[Optional[str]] = mapped_column(Text)

    pessoa: Mapped[Pessoa] = relationship()
    partido: Mapped[Optional[Partido]] = relationship()


class PessoaNome(MigratedBase):
    __tablename__ = "pessoa_nome"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(primary_key=True)
    pessoa_id: Mapped[int] = mapped_column(ForeignKey("core.pessoa.id"))
    tipo: Mapped[str] = mapped_column(Text)
    nome: Mapped[str] = mapped_column(Text)
