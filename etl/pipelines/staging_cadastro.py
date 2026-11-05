"""
Etapas 2 a 4 da carga do staging: políticos (presidentes, deputados, senadores), filiações partidárias e mandatos (com o
gabinete presidencial). As regras são as do carregador relacional anterior, só que sobre `etl.pipelines.stg_tabela`: as
linhas do staging ficam na memória, as consultas por chave natural são dicionários e a gravação é uma só, por `COPY`.

Identificação: o político vem pelo id oficial (Câmara ou Senado); o nome só serve quando é único na base. Contato só é
gravado quando a fonte o informa (os valores sintéticos de versões antigas são limpos). Data desconhecida é limite inferior
declarado, nunca apresentada como real.
"""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from etl.pipelines import stg_tabela
from etl.pipelines.dados_partidos import PARTY_SPECTRUM_MAP, nome_do_partido
from etl.pipelines.loader_helpers import (
    LEGISLATURA_ATUAL,
    LEGISLATURA_ATUAL_INICIO,
    SEM_PARTIDO,
    _to_date,
    legislatura_datas,
    limpar_contatos_inventados,
    resolve_party_id,
)
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_deputados, load_json, load_senadores
from etl.utils.execucao import Contagem
from etl.utils.names import build_unique_name_map, normalize_name_tokens
from etl.utils.provenance import is_synthetic

ensure_backend_on_path()

from app.models.enums import MotivoDesfiliacaoEnum  # noqa: E402

logger = logging.getLogger("StagingCadastro")


def garantir_partido(cursor: Any, party_map: Dict[str, Any], sigla: str) -> Any:
    """
    Id do partido da sigla, criando-o se ainda não existe (partidos extintos citados só em filiações viravam "Sem Partido").
    Sem curadoria do nome, o nome é genérico e o espectro fica vazio (nunca inventado).
    """
    existente = resolve_party_id(party_map, sigla)
    if existente:
        return existente
    cursor.execute(
        'SELECT id FROM stg.partidos_politicos WHERE upper(sigla) = upper(%s) ORDER BY "created_at" LIMIT 1', (sigla,)
    )
    achado = cursor.fetchone()
    if achado:
        identificador = achado[0]
    else:
        cursor.execute(
            'INSERT INTO stg.partidos_politicos (id, sigla, "nomeCompleto", "espectroPolitico") '
            "VALUES (gen_random_uuid(), %s, %s, %s) RETURNING id",
            (sigla, nome_do_partido(sigla), PARTY_SPECTRUM_MAP.get(sigla.upper())),
        )
        identificador = cursor.fetchone()[0]
    party_map[sigla] = identificador
    party_map.setdefault(sigla.upper(), identificador)
    return identificador


@dataclass
class Cadastro:
    """O que as etapas do cadastro compartilham: o cursor, a pasta de dados, as regras de proveniência e as linhas."""

    cursor: Any
    data_dir: Path
    staging: stg_tabela.Staging
    allow_synthetic: bool = False
    allow_unverified: bool = False

    @property
    def politicos(self) -> stg_tabela.Tabela:
        return self.staging.politicos

    @property
    def filiacoes(self) -> stg_tabela.Tabela:
        return self.staging.filiacoes

    @property
    def mandatos(self) -> stg_tabela.Tabela:
        return self.staging.mandatos

    @property
    def gabinete(self) -> stg_tabela.Tabela:
        return self.staging.gabinete


# ---------------------------------------------------------------------------------------------- políticos
def carregar_politicos(c: Cadastro) -> Tuple[Dict[str, Any], Dict[int, Any], Dict[int, Any], Contagem]:
    """
    Presidentes, deputados e senadores. Devolve `(presidentes, deputados, senadores, contagem)`, cada mapa `{id oficial: id
    do político}`. Todo registro da fonte vira (ou encontra) um político: `lidas == gravadas`.
    """
    contagem = Contagem()
    president_map: Dict[str, Any] = {}
    deputy_map: Dict[int, Any] = {}
    senator_map: Dict[int, Any] = {}
    contatos_limpos = 0
    por_camara = {p.camara_id: p for p in c.politicos if p.camara_id is not None}
    por_senado = {p.senado_id: p for p in c.politicos if p.senado_id is not None}

    for p in load_json(c.data_dir / "presidentes_historico.json", []) or []:
        ref_id = p["id_referencia"]
        nome_eleitoral = p["nome_eleitoral"]
        pol = next(
            (x for x in c.politicos if x.civil_name == p["nome_civil"] or x.electoral_name == nome_eleitoral), None
        )
        if not pol:
            pol = c.politicos.nova(
                civil_name=p["nome_civil"],
                electoral_name=nome_eleitoral,
                birth_date=_to_date(p.get("data_nascimento")),
                death_date=_to_date(p.get("data_falecimento")),
                gender=p.get("genero"),
                birthplace_city=p.get("naturalidade_municipio"),
                birthplace_state=p.get("naturalidade_uf"),
                photo_url=p.get("foto_url"),
                biography=f"Presidente da República. Eleição: {p.get('ano_eleicao')}. Status: {p.get('status_mandato')}.",
            )
        president_map[ref_id] = pol.id
        contagem.ler()
        contagem.gravar()

    for d in load_deputados(c.data_dir):  # deduplicado por camara_id
        cid = d["camara_id"]
        pol = por_camara.get(cid)
        legislatura = d.get("id_legislatura")
        bio = f"Deputado Federal pela UF {d.get('uf')} ({d.get('partido_sigla')})."
        if legislatura:
            bio = f"Deputado Federal pela UF {d.get('uf')} ({d.get('partido_sigla')}). Legislatura {legislatura}."
        if not pol:
            pol = c.politicos.nova(
                civil_name=d.get("nome_civil") or d.get("nome_eleitoral"),
                electoral_name=d.get("nome_eleitoral"),
                camara_id=cid,
                photo_url=d.get("foto_url"),
                birth_date=_to_date(d.get("data_nascimento")),
                gender=d.get("sexo"),
                # A UF do deputado é a ELEITORAL; naturalidade só vem do endpoint de detalhe.
                birthplace_state=d.get("uf_nascimento"),
                birthplace_city=d.get("municipio_nascimento"),
                email=d.get("email"),
                cabinet_room=d.get("gabinete_sala"),
                cabinet_phone=d.get("gabinete_telefone"),
                biography=bio,
            )
            por_camara[cid] = pol
        else:
            contatos_limpos += int(limpar_contatos_inventados(pol))
            # Preenche apenas com dado real da fonte; nunca com valor derivado do id.
            for attr, chave in (
                ("email", "email"),
                ("cabinet_room", "gabinete_sala"),
                ("cabinet_phone", "gabinete_telefone"),
                ("birthplace_state", "uf_nascimento"),
                ("birthplace_city", "municipio_nascimento"),
                ("gender", "sexo"),
            ):
                if not getattr(pol, attr) and d.get(chave):
                    setattr(pol, attr, d[chave])
            if not pol.birth_date and d.get("data_nascimento"):
                pol.birth_date = _to_date(d["data_nascimento"])
        deputy_map[cid] = pol.id
        contagem.ler()
        contagem.gravar()

    for s in load_senadores(c.data_dir):  # deduplicado por senado_id
        sid = s["senado_id"]
        pol = por_senado.get(sid)
        if not pol:
            pol = c.politicos.nova(
                civil_name=s.get("nome_civil") or s.get("nome_eleitoral"),
                electoral_name=s.get("nome_eleitoral"),
                senado_id=sid,
                photo_url=s.get("foto_url"),
                email=s.get("email"),
                cabinet_room=s.get("gabinete_sala"),
                cabinet_phone=s.get("gabinete_telefone"),
                biography=f"Senador Federal pela UF {s.get('uf')} ({s.get('partido_sigla')}).",
            )
            por_senado[sid] = pol
        else:
            contatos_limpos += int(limpar_contatos_inventados(pol))
            if not pol.email and s.get("email"):
                pol.email = s["email"]
        senator_map[sid] = pol.id
        contagem.ler()
        contagem.gravar()

    if contatos_limpos:
        logger.info("-> %d políticos tiveram contatos sintéticos legados removidos.", contatos_limpos)
    logger.info(
        "-> Políticos carregados: %d mandatos presidenciais, %d deputados e %d senadores.",
        len(president_map),
        len(deputy_map),
        len(senator_map),
    )
    return president_map, deputy_map, senator_map, contagem


# ---------------------------------------------------------------------------------------------- filiações
def carregar_filiacoes(
    c: Cadastro, deputy_map: Dict[int, Any], senator_map: Dict[int, Any], party_map: Dict[str, Any]
) -> Contagem:
    """
    Histórico de filiações. Identifica o político por id oficial; nome só se for único. `gravadas` conta as inseridas e as que
    já estavam; as rejeitadas têm motivo (`SINTETICO`, `SEM_PROVENIENCIA`, `NAO_CADASTRADO`, `SEM_PARTIDO`).
    """
    contagem = Contagem()
    filiacoes = load_json(c.data_dir / "filiacoes_partidarias.json", None)
    if filiacoes is None:
        logger.warning("Arquivo filiacoes_partidarias.json não encontrado. Pulando carga.")
        return contagem

    name_to_pol_id = build_unique_name_map([(p.id, p.electoral_name) for p in c.politicos if p.electoral_name])
    existentes = {(f.politician_id, f.party_id, f.start_date) for f in c.filiacoes}

    inseridas = sem_politico = data_estimada = sem_proveniencia = 0
    for item in filiacoes:
        contagem.ler()
        if is_synthetic(item) and not c.allow_synthetic:
            contagem.rejeitar("SINTETICO")
            continue
        if not item.get("fonte") and not c.allow_unverified:
            sem_proveniencia += 1  # legado: origens/datas de filiação eram sorteadas por `idx % N`
            contagem.rejeitar("SEM_PROVENIENCIA")
            continue
        cid, sid = item.get("camara_id"), item.get("senado_id")
        if cid and cid in deputy_map:
            pol_id = deputy_map[cid]
        elif sid and sid in senator_map:
            pol_id = senator_map[sid]
        else:
            pol_id = name_to_pol_id.get(normalize_name_tokens(item.get("politico_nome")))
        if not pol_id:
            sem_politico += 1
            contagem.rejeitar("NAO_CADASTRADO")
            continue

        sigla = item.get("partido_sigla")
        party_id = garantir_partido(c.cursor, party_map, sigla) if sigla else party_map.get(SEM_PARTIDO)
        if not party_id:
            contagem.rejeitar("SEM_PARTIDO")
            continue

        dt_fil = _to_date(item.get("data_filiacao"))
        if dt_fil is None:
            # A data de filiação é desconhecida. A filiação ATUAL é um fato (vem das APIs); só a data não.
            # Usa o início da legislatura como LIMITE INFERIOR de observação (campo é obrigatório).
            dt_fil = LEGISLATURA_ATUAL_INICIO
            data_estimada += 1
        dt_desfil = _to_date(item.get("data_desfiliacao"))
        if (pol_id, party_id, dt_fil) in existentes:
            contagem.gravar()  # já estava: a carga é idempotente
            continue

        motivo = None
        motivo_raw = item.get("motivo_desfiliacao")
        if motivo_raw and not pd.isna(motivo_raw) and str(motivo_raw).lower() != "none":
            motivo = (
                MotivoDesfiliacaoEnum[str(motivo_raw)].name
                if str(motivo_raw) in MotivoDesfiliacaoEnum.__members__
                else MotivoDesfiliacaoEnum.MUDANCA_VOLUNTARIA.name
            )
        c.filiacoes.nova(
            politician_id=pol_id,
            party_id=party_id,
            start_date=dt_fil,
            end_date=dt_desfil,
            is_current=bool(item.get("is_atual", dt_desfil is None)),
            disaffiliation_reason=motivo,
            state=item.get("uf"),
        )
        existentes.add((pol_id, party_id, dt_fil))
        inseridas += 1
        contagem.gravar()

    if sem_proveniencia:
        logger.warning(
            "-> %d filiações ignoradas por falta de proveniência (arquivo legado com origens sorteadas). "
            "Reexecute `--tse` ou use --allow-unverified.",
            sem_proveniencia,
        )
    logger.info(
        "-> %d filiações inseridas (%d com data desconhecida usando o início da legislatura como limite inferior; "
        "%d sem político identificável).",
        inseridas,
        data_estimada,
        sem_politico,
    )
    return contagem


# ---------------------------------------------------------------------------------------------- mandatos
def _datas_mandato_senador(s: Dict[str, Any]) -> Tuple[Optional[date], Optional[date], Optional[int]]:
    inicio = _to_date(s.get("mandato_inicio"))
    fim = _to_date(s.get("mandato_fim"))
    if inicio is None and s.get("legislatura_inicio"):
        inicio, _ = legislatura_datas(int(s["legislatura_inicio"]))
    if fim is None and s.get("legislatura_fim"):
        _, fim = legislatura_datas(int(s["legislatura_fim"]))
    if inicio is None:
        return None, None, None
    return inicio, fim, inicio.year - 1


def carregar_mandatos(
    c: Cadastro,
    president_map: Dict[str, Any],
    deputy_map: Dict[int, Any],
    senator_map: Dict[int, Any],
    party_map: Dict[str, Any],
) -> Tuple[Dict[str, Any], Contagem]:
    """
    Mandatos presidenciais, ministros da Fazenda e mandatos de deputados e senadores. Devolve `(mandatos presidenciais,
    contagem)`; a contagem tem um mandato por presidente, deputado e senador da fonte (`NAO_CADASTRADO` quando o político não
    existe) e `gravadas` inclui os que já estavam.
    """
    contagem = Contagem()
    mandate_map: Dict[str, Any] = {}
    por_politico: Dict[Any, List[Any]] = {}
    for m in c.mandatos:
        por_politico.setdefault(m.politician_id, []).append(m)
    membros = {(g.mandate_id, g.occupant_name, g.inauguration_date) for g in c.gabinete}

    def criar(**atributos: Any) -> Any:
        mandato = c.mandatos.nova(**atributos)
        por_politico.setdefault(mandato.politician_id, []).append(mandato)
        return mandato

    for p in load_json(c.data_dir / "presidentes_historico.json", []) or []:
        ref_id = p["id_referencia"]
        pol_id = president_map.get(ref_id)
        partido_id = resolve_party_id(party_map, p.get("partido_sigla")) or resolve_party_id(party_map, "MDB")
        dt_inicio, dt_fim = _to_date(p["data_inicio"]), _to_date(p.get("data_fim"))
        st_str = p.get("status_mandato", "CONCLUIDO")
        status = st_str if st_str in ("IMPEACHMENT", "TITULAR_ATIVO") else "CONCLUIDO"

        mandato = next(
            (
                m
                for m in por_politico.get(pol_id, [])
                if m.election_year == p["ano_eleicao"] and m.term_number == p["mandato_numero"]
            ),
            None,
        )
        if not mandato:
            mandato = criar(
                politician_id=pol_id,
                party_id=partido_id,
                office="PRESIDENTE",
                sphere="FEDERAL",
                jurisdiction_state="BR",
                election_year=p["ano_eleicao"],
                term_number=p["mandato_numero"],
                start_date=dt_inicio,
                end_date=dt_fim,
                status=status,
                # `coalition_name` não é o vice-presidente (campo usado errado antes); fica vazio.
                coalition_name=None,
            )
        mandate_map[ref_id] = mandato.id
        contagem.ler()
        contagem.gravar()

        for min_faz in p.get("ministros_fazenda_chave", []):
            dt_posse, dt_exon = _to_date(min_faz["inicio"]), _to_date(min_faz.get("fim"))
            if (mandato.id, min_faz["nome"], dt_posse) not in membros:
                c.gabinete.nova(
                    mandate_id=mandato.id,
                    occupant_name=min_faz["nome"],
                    ministry_name="Ministério da Fazenda",
                    inauguration_date=dt_posse,
                    departure_date=dt_exon,
                    is_economy_minister=True,
                )
                membros.add((mandato.id, min_faz["nome"], dt_posse))

    # Deputados: o mandato segue a legislatura informada pela API (57ª => eleição 2022, 2023-02-01 a 2027-01-31).
    criados_dep = 0
    for d in load_deputados(c.data_dir):
        contagem.ler()
        pol_id = deputy_map.get(d["camara_id"])
        if not pol_id:
            contagem.rejeitar("NAO_CADASTRADO")
            continue
        contagem.gravar()
        legislatura = int(d.get("id_legislatura") or LEGISLATURA_ATUAL)
        inicio, fim = legislatura_datas(legislatura)
        ano_eleicao = inicio.year - 1
        partido_id = resolve_party_id(party_map, d.get("partido_sigla")) or party_map.get(SEM_PARTIDO)
        existe = any(
            m.election_year == ano_eleicao and m.office == "DEPUTADO_FEDERAL" for m in por_politico.get(pol_id, [])
        )
        if not existe:
            criar(
                politician_id=pol_id,
                party_id=partido_id,
                office="DEPUTADO_FEDERAL",
                sphere="FEDERAL",
                jurisdiction_state=d.get("uf") or "DF",
                election_year=ano_eleicao,
                term_number=1,
                start_date=inicio,
                end_date=fim,
                status="TITULAR_ATIVO",
            )
            criados_dep += 1

    # Senadores: datas do mandato vêm da API (legislaturas do mandato); o mandato dura 8 anos (2 legislaturas).
    criados_sen = sem_dados_sen = 0
    for s in load_senadores(c.data_dir):
        contagem.ler()
        pol_id = senator_map.get(s["senado_id"])
        if not pol_id:
            contagem.rejeitar("NAO_CADASTRADO")
            continue
        contagem.gravar()
        partido_id = resolve_party_id(party_map, s.get("partido_sigla")) or party_map.get(SEM_PARTIDO)
        inicio, fim, ano_eleicao = _datas_mandato_senador(s)
        if inicio is None:
            # Fonte sem datas (arquivo gerado antes da extração de `Mandato`): usa o início da legislatura atual, SEM
            # data de término — e SEM afirmar que foi eleito em 2022 (metade do Senado foi em 2018).
            sem_dados_sen += 1
            inicio, fim, ano_eleicao = LEGISLATURA_ATUAL_INICIO, None, LEGISLATURA_ATUAL_INICIO.year - 1

        do_senador = sorted(
            (m for m in por_politico.get(pol_id, []) if m.office == "SENADOR"),
            key=lambda m: m.start_date,
            reverse=True,
        )
        mandato = do_senador[0] if do_senador else None
        if not mandato:
            criar(
                politician_id=pol_id,
                party_id=partido_id,
                office="SENADOR",
                sphere="FEDERAL",
                jurisdiction_state=s.get("uf") or "DF",
                election_year=ano_eleicao,
                term_number=1,
                start_date=inicio,
                end_date=fim,
                status="TITULAR_ATIVO",
            )
            criados_sen += 1
        elif s.get("mandato_inicio") or s.get("legislatura_inicio"):
            # Só corrige datas quando a fonte as informa de fato
            mandato.start_date, mandato.end_date, mandato.election_year = inicio, fim, ano_eleicao

    if sem_dados_sen:
        logger.warning(
            "-> %d senadores sem datas de mandato na fonte: usado o início da legislatura atual sem data de término. "
            "Reexecute a extração do Senado para obter as datas reais.",
            sem_dados_sen,
        )
    logger.info(
        "-> Mandatos: %d de deputados e %d de senadores criados; presidenciais sincronizados.", criados_dep, criados_sen
    )
    return mandate_map, contagem
