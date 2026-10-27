"""
Cargas relacionais dos dados oficiais do TSE (doações de campanha, situação de registro e eleições por UF).

Mantidas fora de `db_loader.py` para isolar a lógica. Todas são idempotentes:
- doações: para cada (político, ano) presente no arquivo, o conjunto de linhas é substituído;
- certidões: chave natural (político, órgão, tipo de certidão), atualizada se já existir;
- eleições: chave natural (ano, UF, turno).
Só registros com proveniência oficial (`fonte` e `is_synthetic == False`) são carregados.

ESCRITA LEGADA: doações e certidões daqui vão para tabelas do `public` que a API não lê mais (o dossiê lê `fin`, carregado
por `financas_loader.carregar_doacoes` e `carregar_certidoes`, de mesmo nome por serem a mesma fonte). Ficam só até a
limpeza das tabelas legadas (Fase 9 do plano de refatoração do banco); não corrija regra de negócio aqui esperando que
ela chegue ao dossiê. As eleições por UF seguem valendo.
"""

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
)

from etl.pipelines.loader_helpers import _dec, documento_do_doador, nome_sem_cpf, texto_sem_cpf  # noqa: E402
from etl.utils.datafiles import load_json  # noqa: E402
from etl.utils.names import build_unique_name_map, normalize_name_tokens  # noqa: E402
from etl.utils.provenance import is_trusted  # noqa: E402
from etl.utils.rotulos import DOADOR_NAO_IDENTIFICADO  # noqa: E402

logger = logging.getLogger("TSELoaders")

DOACOES_ARQUIVO = "tse_doacoes_campanha.json"
CERTIDOES_ARQUIVO = "certidoes_tse.json"


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
                    donor_name=(nome_sem_cpf(d.get("nome_doador")) or DOADOR_NAO_IDENTIFICADO)[:255],
                    donor_cpf_cnpj=documento_do_doador(d.get("cpf_cnpj_doador")),
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
            details=texto_sem_cpf(item.get("detalhes")),
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
