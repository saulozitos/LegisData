"""
Etapa 6 da carga do staging e histórico de votações: sessões e votos nominais da Câmara e do Senado (arquivos do plenário e
arquivos anuais `votacoes/{camara,senado}_AAAA.json.gz`) e os ex-parlamentares que votaram em legislaturas anteriores.

Idempotente: sessão por `external_id`, voto por (sessão, político) com `ON CONFLICT DO NOTHING` (`staging_votos`). Nada é
presumido: sessão sem proposição resolvível é descartada, e os votos dela contam como lidos e descartados. Um arquivo pulado
inteiro (ilegível, sem proveniência ou só com um dos lados) é contado em `arquivos_ignorados` e deixa a execução em
`COM_ALERTA`.
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from etl.extractors.camara_extractor import classificar_setor_por_texto, interpretar_aprovacao
from etl.extractors.senado_extractor import MATERIAS_BUSCA
from etl.extractors.votacoes_extractor import ler_json_gz, listar_arquivos_processados
from etl.pipelines import stg_tabela
from etl.pipelines.loader_helpers import (
    _to_datetime,
    classify_proposition_impact,
    legislatura_datas,
    resolve_party_id,
)
from etl.pipelines.staging_cadastro import garantir_partido
from etl.pipelines.staging_votos import ContagemDeVotos, LinhaDeVoto, gravar_votos
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json
from etl.utils.execucao import Contagem
from etl.utils.names import build_unique_name_map, normalize_name_tokens

ensure_backend_on_path()

from app.models.enums import StatusTramitacaoEnum, TipoProposicaoEnum, VotoOpcaoEnum  # noqa: E402

logger = logging.getLogger("StagingVotacoes")

ANO_NUMERACAO_UNICA = 2019  # a partir daí Câmara e Senado compartilham a numeração de PL/PLP/PEC/...
ARQUIVO_HISTORICOS = "parlamentares_legislaturas_anteriores.json"
CAMARA, SENADO = "CAMARA_DOS_DEPUTADOS", "SENADO_FEDERAL"
# Arquivos legados de votação do Senado não traziam o ano da matéria; as duas matérias coletadas são conhecidas.
MATERIA_ANO_CONHECIDA = {(m["sigla"], m["numero"]): m["ano"] for m in MATERIAS_BUSCA}
TIPOS_SUPORTADOS = {"PL", "PEC", "PLP", "MPV", "PDL", "DECRETO_PRES", "LEI_DELEGADA"}


# ---------------------------------------------------------------------------------------------- utilidades
def _date(valor: Any) -> Optional[date]:
    texto = str(valor or "").strip()[:10]
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def _datetime(valor: Any) -> Optional[datetime]:
    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def _status_mandato(fim: Optional[date]) -> str:
    return "CONCLUIDO" if fim and fim < date.today() else "TITULAR_ATIVO"


def _arquivo_confiavel(dados: Any, caminho: Path) -> bool:
    if not isinstance(dados, dict) or not dados.get("fonte") or dados.get("is_synthetic"):
        logger.warning("%s sem proveniência oficial (fonte/is_synthetic) — ignorado.", caminho.name)
        return False
    return True


def _opcao_voto(valor: Any) -> Optional[str]:
    """O nome da opção de voto no enum do banco, ou None quando a opção é desconhecida."""
    nome = str(valor or "AUSENTE").strip().upper()
    return nome if nome in VotoOpcaoEnum.__members__ else None


# ---------------------------------------------------------------------------------------------- plenário
def carregar_votacoes_plenario(
    cursor: Any,
    staging: stg_tabela.Staging,
    data_dir: Path,
    prop_map: Dict[int, Any],
    deputy_map: Dict[int, Any],
    senator_map: Dict[int, Any],
    party_map: Dict[str, Any],
) -> ContagemDeVotos:
    """
    Sessões e votos nominais (Câmara e Senado), idempotentes e sem associar sessão a proposição arbitrária. Devolve a
    contagem de votos para o registro da execução.
    """
    session_map: Dict[str, Any] = {}
    votos_inseridos = descartadas = votos_invalidos = 0
    contagem = ContagemDeVotos()
    sessoes_por_externo = {s.external_id: s for s in staging.sessoes if s.external_id is not None}

    por_chave: Dict[Tuple[str, int, int], List[Any]] = {}
    for p in staging.proposicoes:
        por_chave.setdefault((p.proposition_type, p.number, p.year), []).append(p)

    def proposicao_por_chave(sigla: Optional[str], numero: Any, ano: Any) -> Optional[Any]:
        """Proposição por (tipo, número, ano) exatos. Ambiguidade/ausência => None (a sessão é descartada)."""
        if not sigla or numero in (None, "") or ano in (None, ""):
            return None
        tipo = str(sigla).upper()
        if tipo not in TipoProposicaoEnum.__members__:
            return None
        candidatos = por_chave.get((tipo, int(numero), int(ano)), [])
        if len(candidatos) == 1:
            return candidatos[0].id
        com_camara = [c for c in candidatos if c.external_camara_id]
        return com_camara[0].id if len(com_camara) == 1 else None

    def totais_por_sessao(votos: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
        tot: Dict[str, Dict[str, int]] = {}
        for v in votos:
            t = tot.setdefault(str(v.get("sessao_externa_id")), {})
            op = str(v.get("voto") or "")
            t[op] = t.get(op, 0) + 1
        return tot

    def upsert_sessao(s: Dict[str, Any], casa: str, prop_id: Any, titulo_padrao: str, totais: Dict[str, int]):
        ext_id = str(s["sessao_externa_id"])
        dt_obj = _to_datetime(s.get("data_hora"))
        if dt_obj is None:
            logger.warning("Sessão %s sem data/hora — ignorada (data não é presumida).", ext_id)
            return None

        # Totais recalculados dos votos nominais quando existem (fonte única de verdade); senão, os do arquivo.
        sim = totais.get("SIM", 0) if totais else s.get("total_sim", 0)
        nao = totais.get("NAO", 0) if totais else s.get("total_nao", 0)
        abst = totais.get("ABSTENCAO", 0) if totais else s.get("total_abstencao", 0)
        obst = totais.get("OBSTRUCAO", 0) if totais else s.get("total_obstrucao", 0)

        obj = sessoes_por_externo.get(ext_id)
        if obj is not None and obj.legislative_house != casa:
            logger.warning("external_id %s já pertence a outra casa — sessão ignorada.", ext_id)
            return None
        if obj is None:
            obj = staging.sessoes.nova(
                external_id=ext_id,
                proposition_id=prop_id,
                legislative_house=casa,
                session_datetime=dt_obj,
                agenda_title=s.get("titulo_pauta") or titulo_padrao,
                detailed_description=s.get("descricao"),
                is_approved=bool(s.get("aprovada")),  # indeterminada (None) => False; campo é obrigatório
            )
            sessoes_por_externo[ext_id] = obj
        obj.votes_yes_count, obj.votes_no_count = sim or 0, nao or 0
        obj.votes_abstain_count, obj.votes_obstruction_count = abst or 0, obst or 0
        return obj

    def inserir_votos(votos: List[Dict[str, Any]], chave_politico: str, politician_map: Dict[int, Any]) -> None:
        nonlocal votos_inseridos, votos_invalidos, contagem
        linhas: List[LinhaDeVoto] = []
        for v in votos:
            sessao_id = session_map.get(str(v["sessao_externa_id"]))
            politico_id = politician_map.get(v.get(chave_politico))
            if not sessao_id or not politico_id:
                continue
            opcao = _opcao_voto(v.get("voto"))
            if opcao is None:
                votos_invalidos += 1  # antes: KeyError derrubava a carga inteira
                continue
            partido_id = resolve_party_id(party_map, v.get("partido_sigla")) if v.get("partido_sigla") else None
            linhas.append((sessao_id, politico_id, partido_id, opcao))
        staging.gravar(cursor)  # as sessões novas precisam estar na transação antes do COPY dos votos
        inseridos, existentes = gravar_votos(cursor, linhas)
        votos_inseridos += inseridos
        contagem += ContagemDeVotos(len(votos), inseridos + existentes, len(votos) - len(linhas))

    # A. Câmara dos Deputados
    sessoes_cam = load_json(data_dir / "sessoes_votacao_2023.json", None)
    votos_cam = load_json(data_dir / "votos_nominais_2023.json", None)
    if (sessoes_cam is None) != (votos_cam is None):
        contagem += _arquivo_de_votos_incompleto("sessoes_votacao_2023.json", "votos_nominais_2023.json")
    if sessoes_cam is not None and votos_cam is not None:
        totais = totais_por_sessao(votos_cam)
        for s in sessoes_cam:
            prop_id = prop_map.get(s.get("proposicao_camara_id"))
            if not prop_id:
                descartadas += 1
                continue
            obj = upsert_sessao(s, CAMARA, prop_id, "Votação em Plenário", totais.get(str(s["sessao_externa_id"]), {}))
            if obj is not None:
                session_map[str(s["sessao_externa_id"])] = obj.id
        inserir_votos(votos_cam, "deputado_camara_id", deputy_map)

    # B. Senado Federal — proposição por (tipo, número, ano) exatos; sem correspondência única => descarta
    sessoes_sen = load_json(data_dir / "sessoes_votacao_senado.json", None)
    votos_sen = load_json(data_dir / "votos_nominais_senado.json", None)
    if (sessoes_sen is None) != (votos_sen is None):
        contagem += _arquivo_de_votos_incompleto("sessoes_votacao_senado.json", "votos_nominais_senado.json")
    if sessoes_sen is not None and votos_sen is not None:
        totais = totais_por_sessao(votos_sen)
        for s in sessoes_sen:
            ano_materia = s.get("materia_ano") or MATERIA_ANO_CONHECIDA.get(
                (s.get("materia_sigla"), s.get("materia_numero"))
            )
            prop_id = proposicao_por_chave(s.get("materia_sigla"), s.get("materia_numero"), ano_materia)
            if not prop_id:
                descartadas += 1
                logger.warning(
                    "Sessão do Senado %s (%s %s/%s) sem proposição única correspondente — descartada.",
                    s.get("sessao_externa_id"),
                    s.get("materia_sigla"),
                    s.get("materia_numero"),
                    s.get("materia_ano"),
                )
                continue
            obj = upsert_sessao(
                s, SENADO, prop_id, "Votação no Senado Federal", totais.get(str(s["sessao_externa_id"]), {})
            )
            if obj is not None:
                session_map[str(s["sessao_externa_id"])] = obj.id
        inserir_votos(votos_sen, "senador_id", senator_map)

    logger.info(
        "-> %d sessões e %d votos nominais novos (%d sessões descartadas, %d votos com opção desconhecida).",
        len(session_map),
        votos_inseridos,
        descartadas,
        votos_invalidos,
    )
    return contagem


def _arquivo_de_votos_incompleto(sessoes: str, votos: str) -> ContagemDeVotos:
    """Só um dos dois arquivos (sessões e votos) existe: sem o par os votos não entram, e a execução avisa."""
    logger.warning("%s e %s precisam existir juntos: o par foi ignorado.", sessoes, votos)
    return ContagemDeVotos(arquivos_ignorados=1)


# ---------------------------------------------------------------------------------------------- histórico
class _Contexto:
    """Estado compartilhado da carga histórica (índices, caches e contadores)."""

    def __init__(
        self,
        cursor: Any,
        staging: stg_tabela.Staging,
        deputy_map: Dict[int, Any],
        senator_map: Dict[int, Any],
        party_map: Dict[str, Any],
    ):
        self.cursor = cursor
        self.staging = staging
        self.deputy_map = deputy_map
        self.senator_map = senator_map
        self.party_map = party_map
        # Votos lidos, gravados e descartados dos arquivos (inclusive os de sessão descartada) e arquivos pulados inteiros;
        # vai para `contadores` ao fim da carga, pelas chaves de `ContagemDeVotos.como_contadores`
        self.votos = ContagemDeVotos()
        self.contadores: Dict[str, int] = {
            "politicos_criados": 0,
            "politicos_vinculados": 0,
            "mandatos_criados": 0,
            "proposicoes_criadas": 0,
            "sessoes_novas": 0,
            "sessoes_atualizadas": 0,
            "sessoes_descartadas": 0,
            "votos_processados": 0,  # votos que viraram linha (sessão e político conhecidos, opção válida)
            "datas_aproximadas": 0,
        }
        self._mandatos = {(m.politician_id, m.office, m.election_year) for m in staging.mandatos}
        self._politicos_por_id = {p.id: p for p in staging.politicos}
        self._por_camara = {p.camara_id: p for p in staging.politicos if p.camara_id is not None}
        self._por_senado = {p.senado_id: p for p in staging.politicos if p.senado_id is not None}
        self._nomes_sem_camara = self._mapa_nomes([p for p in staging.politicos if p.camara_id is None])
        self._nomes_sem_senado = self._mapa_nomes([p for p in staging.politicos if p.senado_id is None])
        self._props: Dict[Tuple[str, Any], Any] = {}
        self._prop_camara = {p.external_camara_id: p for p in staging.proposicoes if p.external_camara_id}
        self._prop_senado = {p.external_senado_id: p for p in staging.proposicoes if p.external_senado_id}
        self._prop_por_chave: Dict[Tuple[str, int, int], List[Any]] = {}
        for p in staging.proposicoes:
            self._prop_por_chave.setdefault((p.proposition_type, p.number, p.year), []).append(p)
        self.sessoes_por_externo = {s.external_id: s for s in staging.sessoes if s.external_id is not None}

    @staticmethod
    def _mapa_nomes(politicos: List[Any]) -> Dict[str, Any]:
        return build_unique_name_map(
            [(p.id, p.electoral_name) for p in politicos if p.electoral_name]
            + [(p.id, p.civil_name) for p in politicos if p.civil_name]
        )

    # ------------------------------------------------------------------ partidos
    def party_id(self, sigla: Optional[str]) -> Optional[Any]:
        sigla = (sigla or "").strip()
        if not sigla:
            return None
        return resolve_party_id(self.party_map, sigla) or garantir_partido(self.cursor, self.party_map, sigla)

    # ------------------------------------------------------------------ políticos e mandatos
    def garantir_deputado(self, camara_id: int, info: Dict[str, Any]) -> Optional[Any]:
        pol_id = self.deputy_map.get(camara_id)
        if pol_id is None:
            nome = (info.get("nome") or info.get("nome_eleitoral") or "").strip()
            if not nome:
                return None
            existente = self._por_camara.get(camara_id)
            if existente is None:
                # Mesmo nome (único) sem id da Câmara: é a mesma pessoa vinda de outro cargo (ex.: senador).
                candidato = self._nomes_sem_camara.get(normalize_name_tokens(nome))
                if candidato:
                    existente = self._politicos_por_id.get(candidato)
                    if existente is not None and existente.camara_id is None:
                        existente.camara_id = camara_id
                        self.contadores["politicos_vinculados"] += 1
                    else:
                        existente = None
            if existente is None:
                existente = self.staging.politicos.nova(
                    civil_name=info.get("nome_civil") or nome,
                    electoral_name=nome,
                    camara_id=camara_id,
                    photo_url=info.get("foto_url"),
                    biography=f"Deputado Federal pela UF {info.get('uf') or 'não informada'} ({info.get('partido') or info.get('partido_sigla') or 'sem partido'}).",
                )
                self._politicos_por_id[existente.id] = existente
                self.contadores["politicos_criados"] += 1
            self._por_camara[camara_id] = existente
            self.deputy_map[camara_id] = pol_id = existente.id
        for leg in info.get("legislaturas") or []:
            self._garantir_mandato_deputado(
                pol_id, int(leg), info.get("uf"), info.get("partido") or info.get("partido_sigla")
            )
        return pol_id

    def _garantir_mandato_deputado(
        self, pol_id: Any, legislatura: int, uf: Optional[str], sigla: Optional[str]
    ) -> None:
        inicio, fim = legislatura_datas(legislatura)
        chave = (pol_id, "DEPUTADO_FEDERAL", inicio.year - 1)
        if chave in self._mandatos:
            return
        partido = self.party_id(sigla) or self.party_id("S.PART.")
        if partido is None:
            return
        self.staging.mandatos.nova(
            politician_id=pol_id,
            party_id=partido,
            office="DEPUTADO_FEDERAL",
            sphere="FEDERAL",
            jurisdiction_state=(uf or "DF")[:2],
            election_year=inicio.year - 1,
            term_number=1,
            start_date=inicio,
            end_date=fim,
            status=_status_mandato(fim),
        )
        self._mandatos.add(chave)
        self.contadores["mandatos_criados"] += 1

    def garantir_senador(self, senado_id: int, info: Dict[str, Any]) -> Optional[Any]:
        pol_id = self.senator_map.get(senado_id)
        if pol_id is None:
            nome = (info.get("nome") or info.get("nome_eleitoral") or "").strip()
            if not nome:
                return None
            existente = self._por_senado.get(senado_id)
            if existente is None:
                candidato = self._nomes_sem_senado.get(normalize_name_tokens(nome))
                if candidato:
                    existente = self._politicos_por_id.get(candidato)
                    if existente is not None and existente.senado_id is None:
                        existente.senado_id = senado_id
                        self.contadores["politicos_vinculados"] += 1
                    else:
                        existente = None
            if existente is None:
                existente = self.staging.politicos.nova(
                    civil_name=info.get("nome_civil") or nome,
                    electoral_name=nome,
                    senado_id=senado_id,
                    photo_url=info.get("foto_url"),
                    biography=f"Senador Federal pela UF {info.get('uf') or 'não informada'} ({info.get('partido') or info.get('partido_sigla') or 'sem partido'}).",
                )
                self._politicos_por_id[existente.id] = existente
                self.contadores["politicos_criados"] += 1
            self._por_senado[senado_id] = existente
            self.senator_map[senado_id] = pol_id = existente.id
        for m in info.get("mandatos") or []:
            self._garantir_mandato_senador(pol_id, m, info.get("partido_sigla") or info.get("partido"))
        return pol_id

    def _garantir_mandato_senador(self, pol_id: Any, m: Dict[str, Any], sigla: Optional[str]) -> None:
        inicio, fim = _date(m.get("inicio")), _date(m.get("fim"))
        if inicio is None:
            return
        chave = (pol_id, "SENADOR", inicio.year - 1)
        if chave in self._mandatos:
            return
        # Já existe um mandato de senador que cobre o início? (ex.: criado pela carga corrente com outra ano_eleicao)
        for pid, cargo, ano in self._mandatos:
            if pid == pol_id and cargo == "SENADOR" and abs(ano - (inicio.year - 1)) <= 4:
                return
        partido = self.party_id(sigla) or self.party_id("S.PART.")
        if partido is None:
            return
        suplente = "suplente" in str(m.get("participacao") or "").lower()
        self.staging.mandatos.nova(
            politician_id=pol_id,
            party_id=partido,
            office="SENADOR",
            sphere="FEDERAL",
            jurisdiction_state=(m.get("uf") or "DF")[:2],
            election_year=inicio.year - 1,
            term_number=1,
            start_date=inicio,
            end_date=fim,
            status="SUPLENTE_EM_EXERCICIO" if suplente else _status_mandato(fim),
        )
        self._mandatos.add(chave)
        self.contadores["mandatos_criados"] += 1

    # ------------------------------------------------------------------ proposições
    @staticmethod
    def _tipo(sigla: str) -> Optional[str]:
        nome = sigla.upper()
        return nome if nome in TIPOS_SUPORTADOS and nome in TipoProposicaoEnum.__members__ else None

    def proposicao(self, prop: Dict[str, Any], casa: str) -> Optional[Any]:
        chave_ext = prop.get("camara_id") if casa == "CAMARA" else prop.get("senado_id")
        chave_cache = (casa, chave_ext or (prop.get("tipo"), prop.get("numero"), prop.get("ano")))
        if chave_cache in self._props:
            return self._props[chave_cache]
        tipo = self._tipo(prop.get("tipo") or "")
        numero, ano = int(prop.get("numero") or 0), int(prop.get("ano") or 0)
        if tipo is None or not numero or not ano:
            return None

        indice = self._prop_camara if casa == "CAMARA" else self._prop_senado
        obj = indice.get(chave_ext) if chave_ext else None
        if obj is None and ano >= ANO_NUMERACAO_UNICA:
            candidatos = self._prop_por_chave.get((tipo, numero, ano), [])
            livres = [
                c
                for c in candidatos
                if (c.external_camara_id is None if casa == "CAMARA" else c.external_senado_id is None)
            ]
            if len(candidatos) == 1 and len(livres) == 1:
                obj = livres[0]
                if casa == "CAMARA":
                    obj.external_camara_id = chave_ext
                else:
                    obj.external_senado_id = chave_ext
                if chave_ext:
                    indice[chave_ext] = obj
        if obj is None:
            obj = self._criar_proposicao(prop, casa, tipo, numero, ano, chave_ext)
        self._props[chave_cache] = obj.id
        return obj.id

    def _criar_proposicao(
        self, prop: Dict[str, Any], casa: str, tipo: str, numero: int, ano: int, chave_ext: Any
    ) -> Any:
        titulo = prop.get("titulo") or f"{TipoProposicaoEnum[tipo].value} {numero}/{ano}"
        ementa = (prop.get("ementa") or "").strip()
        apresentacao = _date(prop.get("data_apresentacao"))
        if apresentacao is None:
            apresentacao = date(ano, 1, 1)  # coluna obrigatória; limite inferior, contabilizado (não é data real)
            self.contadores["datas_aproximadas"] += 1
        eixo, eixos = classify_proposition_impact(TipoProposicaoEnum[tipo].value, numero, ano, titulo, ementa)
        autor_cid = prop.get("autor_camara_id")
        autor_id = self.deputy_map.get(autor_cid) if autor_cid else None
        status = prop.get("status")
        obj = self.staging.proposicoes.nova(
            external_camara_id=chave_ext if casa == "CAMARA" else None,
            external_senado_id=chave_ext if casa != "CAMARA" else None,
            proposition_type=tipo,
            number=numero,
            year=ano,
            title=titulo[:255],
            summary=ementa or titulo,
            thematic_area=classificar_setor_por_texto(titulo, ementa),
            presentation_date=apresentacao,
            status=status if status in StatusTramitacaoEnum.__members__ else "EM_TRAMITACAO",
            full_text_url=prop.get("url_inteiro_teor"),
            author_name=prop.get("autor_nome"),
            author_politician_id=autor_id,
            impact_axis=eixo,
            impact_tags=eixos,
            official_url=(
                f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={chave_ext}"
                if casa == "CAMARA" and chave_ext
                else (
                    f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{chave_ext}" if chave_ext else None
                )
            ),
        )
        self._prop_por_chave.setdefault((tipo, numero, ano), []).append(obj)
        if chave_ext:
            (self._prop_camara if casa == "CAMARA" else self._prop_senado)[chave_ext] = obj
        self.contadores["proposicoes_criadas"] += 1
        return obj


def carregar_parlamentares_historicos(
    cursor: Any,
    staging: stg_tabela.Staging,
    data_dir: Path,
    deputy_map: Dict[int, Any],
    senator_map: Dict[int, Any],
    party_map: Dict[str, Any],
    contexto: Optional[_Contexto] = None,
) -> Tuple[Dict[str, int], Contagem]:
    """
    Cria deputados da 56ª legislatura e senadores (titulares) de legislaturas anteriores com seus mandatos. Devolve os
    contadores de criação e a contagem de registros: suplente de senador que nunca votou é rejeitado (`SUPLENTE_SEM_VOTO`).
    """
    contagem = Contagem()
    dados = load_json(Path(data_dir) / ARQUIVO_HISTORICOS, None)
    if not isinstance(dados, dict) or not dados.get("fonte") or dados.get("is_synthetic"):
        logger.warning("%s ausente ou sem proveniência — ex-parlamentares não carregados.", ARQUIVO_HISTORICOS)
        return {}, contagem
    ctx = contexto or _Contexto(cursor, staging, deputy_map, senator_map, party_map)
    base = dict(ctx.contadores)

    for d in dados.get("deputados") or []:
        contagem.ler()
        if not d.get("camara_id"):
            contagem.rejeitar("SEM_ID")
            continue
        ctx.garantir_deputado(int(d["camara_id"]), d)
        contagem.gravar()

    # Suplentes só entram se votaram (o arquivo lista também suplentes que podem nunca ter exercido o mandato).
    votantes_senado = _senadores_votantes(data_dir)
    for s in dados.get("senadores") or []:
        contagem.ler()
        sid = s.get("senado_id")
        if not sid:
            contagem.rejeitar("SEM_ID")
            continue
        titular = any("suplente" not in str(m.get("participacao") or "").lower() for m in s.get("mandatos") or [])
        if not titular and sid not in votantes_senado:
            contagem.rejeitar("SUPLENTE_SEM_VOTO")
            continue
        info = dict(s)
        info["mandatos"] = [
            m
            for m in s.get("mandatos") or []
            if "suplente" not in str(m.get("participacao") or "").lower() or sid in votantes_senado
        ]
        ctx.garantir_senador(int(sid), info)
        contagem.gravar()

    resultado = {
        k: ctx.contadores[k] - base[k] for k in ("politicos_criados", "politicos_vinculados", "mandatos_criados")
    }
    logger.info(
        "-> Ex-parlamentares: %d políticos criados, %d vinculados a registro existente, %d mandatos criados.",
        resultado["politicos_criados"],
        resultado["politicos_vinculados"],
        resultado["mandatos_criados"],
    )
    return resultado, contagem


def _senadores_votantes(data_dir: Path) -> set:
    votantes: set = set()
    for caminho in listar_arquivos_processados(Path(data_dir), "senado"):
        try:
            dados = ler_json_gz(caminho)
        except (OSError, ValueError):
            continue
        votantes.update(int(k) for k in (dados.get("parlamentares") or {}))
    return votantes


def carregar_votacoes(
    cursor: Any,
    staging: stg_tabela.Staging,
    data_dir: Path,
    deputy_map: Dict[int, Any],
    senator_map: Dict[int, Any],
    party_map: Dict[str, Any],
) -> Dict[str, int]:
    """Os arquivos anuais de votações nominais. Devolve os contadores (inclui as chaves de `ContagemDeVotos`)."""
    ctx = _Contexto(cursor, staging, deputy_map, senator_map, party_map)
    votos_total = 0
    for casa, prefixo in (("CAMARA", "camara"), ("SENADO", "senado")):
        for caminho in listar_arquivos_processados(Path(data_dir), prefixo):
            try:
                dados = ler_json_gz(caminho)
            except (OSError, ValueError) as exc:
                logger.error("Falha ao ler %s: %s", caminho.name, exc)
                ctx.votos += ContagemDeVotos(arquivos_ignorados=1)
                continue
            if not _arquivo_confiavel(dados, caminho):
                ctx.votos += ContagemDeVotos(arquivos_ignorados=1)
                continue
            votos_total += _carregar_arquivo(ctx, dados, casa)
    ctx.contadores["votos_inseridos"] = votos_total
    ctx.contadores.update(ctx.votos.como_contadores())
    c = ctx.contadores
    logger.info(
        "-> Votações históricas: %d sessões novas, %d atualizadas, %d descartadas; %d votos inseridos "
        "(%d políticos criados, %d proposições criadas, %d mandatos criados).",
        c["sessoes_novas"],
        c["sessoes_atualizadas"],
        c["sessoes_descartadas"],
        votos_total,
        c["politicos_criados"],
        c["proposicoes_criadas"],
        c["mandatos_criados"],
    )
    if c["datas_aproximadas"]:
        logger.warning(
            "-> %d proposições novas sem data de apresentação na fonte (usado 1º de janeiro do ano).",
            c["datas_aproximadas"],
        )
    return dict(ctx.contadores)


def _descartar_votos(ctx: _Contexto, sessao: Dict[str, Any]) -> None:
    """Os votos de uma sessão descartada contam como lidos e descartados: não somem sem deixar rastro na execução."""
    votos = len(sessao.get("votos") or [])
    ctx.votos += ContagemDeVotos(lidas=votos, rejeitadas=votos)


def _carregar_arquivo(ctx: _Contexto, dados: Dict[str, Any], casa: str) -> int:
    staging = ctx.staging
    casa_enum = CAMARA if casa == "CAMARA" else SENADO
    mapa_politicos = ctx.deputy_map if casa == "CAMARA" else ctx.senator_map
    garantir = ctx.garantir_deputado if casa == "CAMARA" else ctx.garantir_senador

    # Parlamentares do arquivo (cria os que ainda não existem)
    for pid, info in (dados.get("parlamentares") or {}).items():
        garantir(int(pid), info)

    partidos = [ctx.party_id(s) for s in dados.get("partidos") or []]
    linhas: List[LinhaDeVoto] = []

    for s in dados.get("sessoes") or []:
        dt = _datetime(s.get("data_hora"))
        prop_id = ctx.proposicao(s.get("proposicao") or {}, casa)
        if dt is None or prop_id is None:
            ctx.contadores["sessoes_descartadas"] += 1
            _descartar_votos(ctx, s)
            continue

        aprovada = s.get("aprovada")
        if aprovada is None and casa == "CAMARA":
            aprovada = interpretar_aprovacao({"descricao": s.get("descricao")})
        t = s.get("totais") or {}
        ext_id = str(s["id"])
        obj = ctx.sessoes_por_externo.get(ext_id)
        if obj is not None and obj.legislative_house != casa_enum:
            ctx.contadores["sessoes_descartadas"] += 1
            _descartar_votos(ctx, s)
            continue
        titulo = (s.get("proposicao") or {}).get("titulo") or "matéria"
        if obj is None:
            obj = staging.sessoes.nova(
                external_id=ext_id,
                proposition_id=prop_id,
                legislative_house=casa_enum,
                session_datetime=dt,
                agenda_title=f"Votação sobre {titulo}"[:255],
                detailed_description=s.get("descricao"),
                is_secret_vote=bool(s.get("secreta")),
                is_approved=bool(aprovada),
            )
            ctx.sessoes_por_externo[ext_id] = obj
            ctx.contadores["sessoes_novas"] += 1
        else:
            ctx.contadores["sessoes_atualizadas"] += 1
        obj.votes_yes_count = int(t.get("SIM", 0))
        obj.votes_no_count = int(t.get("NAO", 0))
        obj.votes_abstain_count = int(t.get("ABSTENCAO", 0))
        obj.votes_obstruction_count = int(t.get("OBSTRUCAO", 0))
        obj.government_orientation = s.get("orientacao_governo")
        obj.party_orientations = json.dumps(s["orientacoes"], ensure_ascii=False) if s.get("orientacoes") else None

        antes = len(linhas)
        votos = s.get("votos") or []
        for pol_ext, opcao, idx_partido in votos:
            pol_id = mapa_politicos.get(int(pol_ext))
            if pol_id is None or opcao not in VotoOpcaoEnum.__members__:
                continue
            partido = partidos[idx_partido] if 0 <= idx_partido < len(partidos) else None
            linhas.append((obj.id, pol_id, partido, opcao))
        aceitos = len(linhas) - antes
        ctx.contadores["votos_processados"] += aceitos
        ctx.votos += ContagemDeVotos(lidas=len(votos), rejeitadas=len(votos) - aceitos)
    # Um COPY por arquivo (e não por sessão): milhares de sessões por arquivo, todas gravadas antes dos votos
    staging.gravar(ctx.cursor)
    inseridos, existentes = gravar_votos(ctx.cursor, linhas)
    ctx.votos += ContagemDeVotos(gravadas=inseridos + existentes)
    return inseridos
