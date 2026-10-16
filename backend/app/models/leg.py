"""Mapeamento ORM do schema `leg` (legislativo). As tabelas são criadas pelas migrações; este módulo só lê/escreve."""

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import MigratedBase
from .core import Entidade, Partido, Pessoa


class Casa(MigratedBase):
    __tablename__ = "casa_legislativa"
    __table_args__ = {"schema": "ref"}

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text)
    nome: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text)


class Proposicao(MigratedBase):
    __tablename__ = "proposicao"
    __table_args__ = {"schema": "leg"}

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    id_camara: Mapped[Optional[int]] = mapped_column(Integer)
    id_senado: Mapped[Optional[int]] = mapped_column(Integer)
    tipo_codigo: Mapped[str] = mapped_column(Text)
    numero: Mapped[int] = mapped_column(Integer)
    ano: Mapped[int] = mapped_column(SmallInteger)
    titulo: Mapped[str] = mapped_column(Text)
    ementa: Mapped[Optional[str]] = mapped_column(Text)
    explicacao_ementa: Mapped[Optional[str]] = mapped_column(Text)
    area_tematica: Mapped[Optional[str]] = mapped_column(Text)
    data_apresentacao: Mapped[date] = mapped_column(Date)
    data_sancao_promulgacao: Mapped[Optional[date]] = mapped_column(Date)
    status_codigo: Mapped[str] = mapped_column(Text)
    url_texto_original: Mapped[Optional[str]] = mapped_column(Text)
    url_oficial: Mapped[Optional[str]] = mapped_column(Text)
    reforma_estrutural: Mapped[bool] = mapped_column(Boolean)
    iniciativa_executivo: Mapped[bool] = mapped_column(Boolean)
    autor_pessoa_id: Mapped[Optional[int]] = mapped_column(ForeignKey("core.pessoa.id"))
    autor_nome: Mapped[Optional[str]] = mapped_column(Text)
    eixo_impacto: Mapped[Optional[str]] = mapped_column(Text)
    eixos_impacto: Mapped[Optional[str]] = mapped_column(Text)

    autoria: Mapped[List["Autoria"]] = relationship(back_populates="proposicao", order_by="Autoria.ordem")
    votacoes: Mapped[List["Votacao"]] = relationship(back_populates="proposicao")


class Autoria(MigratedBase):
    __tablename__ = "autoria"
    __table_args__ = {"schema": "leg"}

    id: Mapped[int] = mapped_column(primary_key=True)
    proposicao_id: Mapped[int] = mapped_column(ForeignKey("leg.proposicao.id"))
    pessoa_id: Mapped[Optional[int]] = mapped_column(ForeignKey("core.pessoa.id"))
    entidade_id: Mapped[Optional[int]] = mapped_column(ForeignKey("core.entidade.id"))
    partido_id: Mapped[Optional[int]] = mapped_column(ForeignKey("core.partido.id"))
    nome_autor: Mapped[str] = mapped_column(Text)
    tipo_codigo: Mapped[str] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer)

    proposicao: Mapped[Proposicao] = relationship(back_populates="autoria")
    pessoa: Mapped[Optional[Pessoa]] = relationship()
    entidade: Mapped[Optional[Entidade]] = relationship()
    partido: Mapped[Optional[Partido]] = relationship()


class Votacao(MigratedBase):
    __tablename__ = "votacao"
    __table_args__ = {"schema": "leg"}

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    id_externo: Mapped[Optional[str]] = mapped_column(Text)
    proposicao_id: Mapped[int] = mapped_column(ForeignKey("leg.proposicao.id"))
    casa_id: Mapped[Optional[int]] = mapped_column(SmallInteger, ForeignKey("ref.casa_legislativa.id"))
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    titulo_pauta: Mapped[Optional[str]] = mapped_column(Text)
    descricao: Mapped[Optional[str]] = mapped_column(Text)
    tipo_deliberacao: Mapped[str] = mapped_column(Text)
    secreta: Mapped[bool] = mapped_column(Boolean)
    aprovada: Mapped[bool] = mapped_column(Boolean)
    local_deliberacao: Mapped[Optional[str]] = mapped_column(Text)
    nome_comissao: Mapped[Optional[str]] = mapped_column(Text)
    link_ata: Mapped[Optional[str]] = mapped_column(Text)
    relator_nome: Mapped[Optional[str]] = mapped_column(Text)
    parecer_numero: Mapped[Optional[str]] = mapped_column(Text)
    parecer_texto: Mapped[Optional[str]] = mapped_column(Text)
    link_parecer: Mapped[Optional[str]] = mapped_column(Text)
    resumo_decisao: Mapped[Optional[str]] = mapped_column(Text)
    orientacao_governo: Mapped[Optional[str]] = mapped_column(Text)
    total_sim_fonte: Mapped[Optional[int]] = mapped_column(Integer)
    total_nao_fonte: Mapped[Optional[int]] = mapped_column(Integer)
    total_abstencao_fonte: Mapped[Optional[int]] = mapped_column(Integer)
    total_obstrucao_fonte: Mapped[Optional[int]] = mapped_column(Integer)

    proposicao: Mapped[Proposicao] = relationship(back_populates="votacoes")
    casa: Mapped[Optional[Casa]] = relationship(lazy="joined")
    votos: Mapped[List["Voto"]] = relationship(back_populates="votacao")
    orientacoes: Mapped[List["Orientacao"]] = relationship(back_populates="votacao")


class Voto(MigratedBase):
    __tablename__ = "voto"
    __table_args__ = {"schema": "leg"}

    votacao_id: Mapped[int] = mapped_column(ForeignKey("leg.votacao.id"), primary_key=True)
    pessoa_id: Mapped[int] = mapped_column(ForeignKey("core.pessoa.id"), primary_key=True)
    partido_id: Mapped[Optional[int]] = mapped_column(ForeignKey("core.partido.id"))
    opcao_codigo: Mapped[str] = mapped_column(Text)

    votacao: Mapped[Votacao] = relationship(back_populates="votos")
    pessoa: Mapped[Pessoa] = relationship()
    partido: Mapped[Optional[Partido]] = relationship()


class Orientacao(MigratedBase):
    __tablename__ = "orientacao"
    __table_args__ = {"schema": "leg"}

    votacao_id: Mapped[int] = mapped_column(ForeignKey("leg.votacao.id"), primary_key=True)
    bancada: Mapped[str] = mapped_column(Text, primary_key=True)
    partido_id: Mapped[Optional[int]] = mapped_column(ForeignKey("core.partido.id"))
    orientacao: Mapped[str] = mapped_column(Text)

    votacao: Mapped[Votacao] = relationship(back_populates="orientacoes")
