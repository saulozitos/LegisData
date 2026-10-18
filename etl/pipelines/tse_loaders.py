"""
Cargas relacionais dos dados oficiais do TSE (doações de campanha, situação de registro e eleições por UF).

Mantidas fora de `db_loader.py` para isolar a lógica. Todas são idempotentes:
- doações: para cada (político, ano) presente no arquivo, o conjunto de linhas é substituído;
- certidões: chave natural (político, órgão, tipo de certidão), atualizada se já existir;
- eleições: chave natural (ano, UF, turno).
Só registros com proveniência oficial (`fonte` e `is_synthetic == False`) são carregados.
"""

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from app.models import (  # noqa: E402
    CertidaoJudicial,
    DoacaoCampanha,
    Politician,
    StatePresidentialElectionResult,
)

from etl.pipelines.loader_helpers import _dec  # noqa: E402
from etl.utils.datafiles import load_json  # noqa: E402
from etl.utils.names import build_unique_name_map, normalize_name_tokens  # noqa: E402
from etl.utils.provenance import is_trusted  # noqa: E402
from etl.utils.rotulos import DOADOR_NAO_IDENTIFICADO  # noqa: E402

logger = logging.getLogger("TSELoaders")

DOACOES_ARQUIVO = "tse_doacoes_campanha.json"
CERTIDOES_ARQUIVO = "certidoes_tse.json"
ELEICOES_ARQUIVO = "eleicoes_presidenciais_uf_tse.csv"


class PoliticoResolver:
    """Resolve o político do banco por id oficial (Câmara/Senado) e, na falta, por nome único."""

    def __init__(self, session: Session):
        politicos = session.query(Politician).all()
        self.por_camara = {p.camara_id: p.id for p in politicos if p.camara_id}
        self.por_senado = {p.senado_id: p.id for p in politicos if p.senado_id}
        self.por_nome = build_unique_name_map(
            [(p.id, p.civil_name) for p in politicos if p.civil_name]
            + [(p.id, p.electoral_name) for p in politicos if p.electoral_name]
        )

    def resolver(self, item: Dict[str, Any]) -> Optional[Any]:
        camara, senado = item.get("camara_id"), item.get("senado_id")
        if camara and camara in self.por_camara:
            return self.por_camara[camara]
        if senado and senado in self.por_senado:
            return self.por_senado[senado]
        for campo in ("nome_civil", "nome_eleitoral"):
            achado = self.por_nome.get(normalize_name_tokens(item.get(campo)))
            if achado:
                return achado
        return None


def carregar_doacoes(session: Session, data_dir: Path) -> Dict[str, int]:
    """Substitui as receitas de campanha de cada (político, ano) do arquivo; devolve contagens."""
    prestacoes = load_json(Path(data_dir) / DOACOES_ARQUIVO, None)
    if prestacoes is None:
        logger.warning("%s não encontrado. Pulando carga de doações de campanha.", DOACOES_ARQUIVO)
        return {"linhas": 0, "prestacoes": 0, "sem_politico": 0, "ignoradas": 0}

    resolver = PoliticoResolver(session)
    visto: Dict[Any, List[Dict[str, Any]]] = {}
    sem_politico = ignoradas = 0
    for item in prestacoes:
        if not is_trusted(item):
            ignoradas += 1
            continue
        pol_id = resolver.resolver(item)
        if pol_id is None:
            sem_politico += 1
            continue
        visto[(pol_id, int(item["ano_eleicao"]))] = item["doadores"]

    linhas = 0
    for (pol_id, ano), doadores in visto.items():
        session.query(DoacaoCampanha).filter(
            DoacaoCampanha.politician_id == pol_id, DoacaoCampanha.election_year == ano
        ).delete(synchronize_session=False)
        for d in doadores:
            valor = _dec(d.get("valor_doado"))
            if valor is None:
                continue
            session.add(
                DoacaoCampanha(
                    politician_id=pol_id,
                    election_year=ano,
                    donor_name=str(d.get("nome_doador") or DOADOR_NAO_IDENTIFICADO)[:255],
                    donor_cpf_cnpj=(d.get("cpf_cnpj_doador") or None),
                    amount_donated=valor,
                    donation_type=(d.get("tipo_receita") or None),
                )
            )
            linhas += 1
    session.flush()
    logger.info(
        "-> Doações: %d linhas para %d prestações (%d sem político, %d sem proveniência).",
        linhas,
        len(visto),
        sem_politico,
        ignoradas,
    )
    return {"linhas": linhas, "prestacoes": len(visto), "sem_politico": sem_politico, "ignoradas": ignoradas}


def carregar_certidoes_tse(session: Session, data_dir: Path) -> Dict[str, int]:
    """Ocorrências adversas de registro de candidatura publicadas pelo TSE (chave: político + órgão + tipo)."""
    ocorrencias = load_json(Path(data_dir) / CERTIDOES_ARQUIVO, None)
    if ocorrencias is None:
        logger.warning("%s não encontrado. Pulando situação de registro do TSE.", CERTIDOES_ARQUIVO)
        return {"inseridas": 0, "atualizadas": 0, "sem_politico": 0, "ignoradas": 0}

    resolver = PoliticoResolver(session)
    existentes = {
        (c.politician_id, c.court_agency, c.certificate_type): c
        for c in session.query(CertidaoJudicial).filter(CertidaoJudicial.court_agency == "TSE").all()
    }
    inseridas = atualizadas = sem_politico = ignoradas = 0
    for item in ocorrencias:
        if not is_trusted(item):
            ignoradas += 1
            continue
        pol_id = resolver.resolver(item)
        if pol_id is None:
            sem_politico += 1
            continue
        chave = (pol_id, item["orgao"], item["tipo_certidao"][:50])
        valores = dict(
            status=item["status_ficha"][:50],
            details=item.get("detalhes"),
            process_number=(item.get("numero_processo") or None),
        )
        atual = existentes.get(chave)
        if atual is None:
            registro = CertidaoJudicial(
                politician_id=pol_id, court_agency=item["orgao"], certificate_type=item["tipo_certidao"][:50], **valores
            )
            session.add(registro)
            existentes[chave] = registro
            inseridas += 1
        else:
            for atributo, valor in valores.items():
                setattr(atual, atributo, valor)
            atualizadas += 1
    session.flush()
    logger.info(
        "-> Situação de registro (TSE): %d inseridas, %d atualizadas, %d sem político.",
        inseridas,
        atualizadas,
        sem_politico,
    )
    return {"inseridas": inseridas, "atualizadas": atualizadas, "sem_politico": sem_politico, "ignoradas": ignoradas}


def carregar_eleicoes_tse(session: Session, data_dir: Path) -> int:
    """Resultados presidenciais por UF do TSE. Devolve quantas linhas foram processadas (0 se não há arquivo)."""
    arquivo = Path(data_dir) / ELEICOES_ARQUIVO
    if not arquivo.exists():
        return 0
    existentes = {
        (r.election_year, r.uf, r.round_number): r for r in session.query(StatePresidentialElectionResult).all()
    }
    processadas = 0
    with open(arquivo, "r", encoding="utf-8", newline="") as fh:
        for linha in csv.DictReader(fh):
            if (
                str(linha.get("verificado", "")).lower() != "true"
                or str(linha.get("is_synthetic", "")).lower() == "true"
            ):
                continue
            ano, uf, turno = int(linha["ano_eleicao"]), linha["uf"], int(linha["turno"])
            valores = dict(
                mandate_ref_id=linha["mandato_id_ref"],
                state_name=linha["estado_nome"],
                region=linha["regiao"],
                winner_candidate_name=linha["candidato_vencedor_nome"],
                winner_party_acronym=linha["partido_vencedor_sigla"],
                winner_votes_pct=_dec(linha["votos_vencedor_pct"]),
                runner_up_candidate_name=linha["candidato_segundo_nome"],
                runner_up_party_acronym=linha["partido_segundo_sigla"],
                runner_up_votes_pct=_dec(linha["votos_segundo_pct"]),
                total_valid_votes=int(linha["total_votos_validos"]) if linha.get("total_votos_validos") else None,
            )
            atual = existentes.get((ano, uf, turno))
            if atual is None:
                novo = StatePresidentialElectionResult(election_year=ano, uf=uf, round_number=turno, **valores)
                session.add(novo)
                existentes[(ano, uf, turno)] = novo
            else:
                for atributo, valor in valores.items():
                    setattr(atual, atributo, valor)
            processadas += 1
    session.flush()
    logger.info("-> Eleições presidenciais por UF (TSE): %d resultados.", processadas)
    return processadas
