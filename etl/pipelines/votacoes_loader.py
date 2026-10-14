"""
Carga do histórico completo de votações nominais (Câmara e Senado) no PostgreSQL.

Idempotente: sessões por `external_id`, votos por (sessão, político) com `ON CONFLICT DO NOTHING`. Cria
ex-parlamentares (e seus mandatos) que votaram ou assinaram emendas/CEAP em legislaturas anteriores, para que os
registros deixem de ficar sem vínculo. Nada é presumido: sessão sem proposição resolvível é descartada.
"""

import json
import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from etl.extractors.camara_extractor import classificar_setor_por_texto, interpretar_aprovacao
from etl.extractors.votacoes_extractor import ler_json_gz, listar_arquivos_processados
from etl.pipelines.loader_helpers import (
    classify_proposition_impact,
    legislatura_datas,
    resolve_party_id,
)
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json
from etl.utils.names import build_unique_name_map, normalize_name_tokens

ensure_backend_on_path()

from app.models import (  # noqa: E402
    CargoPoliticoEnum,
    CasaLegislativaEnum,
    Mandate,
    ParliamentaryVote,
    Politician,
    Proposition,
    StatusMandatoEnum,
    StatusTramitacaoEnum,
    TipoEsferaEnum,
    TipoProposicaoEnum,
    VotingSession,
    VotoOpcaoEnum,
)

logger = logging.getLogger("VotacoesLoader")

ANO_NUMERACAO_UNICA = 2019  # a partir daí Câmara e Senado compartilham a numeração de PL/PLP/PEC/...
LOTE_VOTOS = 2000
ARQUIVO_HISTORICOS = "parlamentares_legislaturas_anteriores.json"

EnsureParty = Callable[[Session, Dict[str, Any], str], Any]


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


def _status_mandato(fim: Optional[date]) -> StatusMandatoEnum:
    return StatusMandatoEnum.CONCLUIDO if fim and fim < date.today() else StatusMandatoEnum.TITULAR_ATIVO


def _insert_ignorando_conflito(session: Session):
    """`INSERT ... ON CONFLICT DO NOTHING` do dialeto em uso (PostgreSQL em produção, SQLite nos testes)."""
    nome = session.get_bind().dialect.name
    if nome == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(ParliamentaryVote.__table__).on_conflict_do_nothing(index_elements=["sessaoVotacaoId", "politicoId"])


def _arquivo_confiavel(dados: Any, caminho: Path) -> bool:
    if not isinstance(dados, dict) or not dados.get("fonte") or dados.get("is_synthetic"):
        logger.warning("%s sem proveniência oficial (fonte/is_synthetic) — ignorado.", caminho.name)
        return False
    return True


class _Contexto:
    """Estado compartilhado da carga (mapas, caches e contadores)."""

    def __init__(
        self,
        session: Session,
        deputy_map: Dict[int, Any],
        senator_map: Dict[int, Any],
        party_map: Dict[str, Any],
        ensure_party: EnsureParty,
    ):
        self.session = session
        self.deputy_map = deputy_map
        self.senator_map = senator_map
        self.party_map = party_map
        self.ensure_party = ensure_party
        self.contadores: Dict[str, int] = {
            "politicos_criados": 0,
            "politicos_vinculados": 0,
            "mandatos_criados": 0,
            "proposicoes_criadas": 0,
            "sessoes_novas": 0,
            "sessoes_atualizadas": 0,
            "sessoes_descartadas": 0,
            "votos_processados": 0,
            "datas_aproximadas": 0,
        }
        self._mandatos = {
            (m.politician_id, m.office, m.election_year)
            for m in session.query(Mandate.politician_id, Mandate.office, Mandate.election_year).all()
        }
        sem_camara = session.query(Politician).filter(Politician.camara_id.is_(None)).all()
        sem_senado = session.query(Politician).filter(Politician.senado_id.is_(None)).all()
        self._nomes_sem_camara = self._mapa_nomes(sem_camara)
        self._nomes_sem_senado = self._mapa_nomes(sem_senado)
        self._props: Dict[Tuple[str, Any], Any] = {}

    @staticmethod
    def _mapa_nomes(politicos: List[Politician]) -> Dict[str, Any]:
        return build_unique_name_map(
            [(p.id, p.electoral_name) for p in politicos if p.electoral_name]
            + [(p.id, p.civil_name) for p in politicos if p.civil_name]
        )

    # ------------------------------------------------------------------ partidos
    def party_id(self, sigla: Optional[str]) -> Optional[Any]:
        sigla = (sigla or "").strip()
        if not sigla:
            return None
        return resolve_party_id(self.party_map, sigla) or self.ensure_party(self.session, self.party_map, sigla)

    # ------------------------------------------------------------------ políticos e mandatos
    def garantir_deputado(self, camara_id: int, info: Dict[str, Any]) -> Optional[Any]:
        pol_id = self.deputy_map.get(camara_id)
        if pol_id is None:
            nome = (info.get("nome") or info.get("nome_eleitoral") or "").strip()
            if not nome:
                return None
            existente = self.session.query(Politician).filter_by(camara_id=camara_id).first()
            if existente is None:
                # Mesmo nome (único) sem id da Câmara: é a mesma pessoa vinda de outro cargo (ex.: senador).
                candidato = self._nomes_sem_camara.get(normalize_name_tokens(nome))
                if candidato:
                    existente = self.session.get(Politician, candidato)
                    if existente is not None and existente.camara_id is None:
                        existente.camara_id = camara_id
                        self.contadores["politicos_vinculados"] += 1
                    else:
                        existente = None
            if existente is None:
                existente = Politician(
                    civil_name=info.get("nome_civil") or nome,
                    electoral_name=nome,
                    camara_id=camara_id,
                    photo_url=info.get("foto_url"),
                    biography=f"Deputado Federal pela UF {info.get('uf') or 'não informada'} ({info.get('partido') or info.get('partido_sigla') or 'sem partido'}).",
                )
                self.session.add(existente)
                self.session.flush()
                self.contadores["politicos_criados"] += 1
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
        chave = (pol_id, CargoPoliticoEnum.DEPUTADO_FEDERAL, inicio.year - 1)
        if chave in self._mandatos:
            return
        partido = self.party_id(sigla) or self.party_id("S.PART.")
        if partido is None:
            return
        self.session.add(
            Mandate(
                politician_id=pol_id,
                party_id=partido,
                office=CargoPoliticoEnum.DEPUTADO_FEDERAL,
                sphere=TipoEsferaEnum.FEDERAL,
                jurisdiction_state=(uf or "DF")[:2],
                election_year=inicio.year - 1,
                term_number=1,
                start_date=inicio,
                end_date=fim,
                status=_status_mandato(fim),
            )
        )
        self._mandatos.add(chave)
        self.contadores["mandatos_criados"] += 1

    def garantir_senador(self, senado_id: int, info: Dict[str, Any]) -> Optional[Any]:
        pol_id = self.senator_map.get(senado_id)
        if pol_id is None:
            nome = (info.get("nome") or info.get("nome_eleitoral") or "").strip()
            if not nome:
                return None
            existente = self.session.query(Politician).filter_by(senado_id=senado_id).first()
            if existente is None:
                candidato = self._nomes_sem_senado.get(normalize_name_tokens(nome))
                if candidato:
                    existente = self.session.get(Politician, candidato)
                    if existente is not None and existente.senado_id is None:
                        existente.senado_id = senado_id
                        self.contadores["politicos_vinculados"] += 1
                    else:
                        existente = None
            if existente is None:
                existente = Politician(
                    civil_name=info.get("nome_civil") or nome,
                    electoral_name=nome,
                    senado_id=senado_id,
                    photo_url=info.get("foto_url"),
                    biography=f"Senador Federal pela UF {info.get('uf') or 'não informada'} ({info.get('partido') or info.get('partido_sigla') or 'sem partido'}).",
                )
                self.session.add(existente)
                self.session.flush()
                self.contadores["politicos_criados"] += 1
            self.senator_map[senado_id] = pol_id = existente.id
        for m in info.get("mandatos") or []:
            self._garantir_mandato_senador(pol_id, m, info.get("partido_sigla") or info.get("partido"))
        return pol_id

    def _garantir_mandato_senador(self, pol_id: Any, m: Dict[str, Any], sigla: Optional[str]) -> None:
        inicio, fim = _date(m.get("inicio")), _date(m.get("fim"))
        if inicio is None:
            return
        chave = (pol_id, CargoPoliticoEnum.SENADOR, inicio.year - 1)
        if chave in self._mandatos:
            return
        # Já existe um mandato de senador que cobre o início? (ex.: criado pela carga corrente com outra ano_eleicao)
        for pid, cargo, ano in self._mandatos:
            if pid == pol_id and cargo == CargoPoliticoEnum.SENADOR and abs(ano - (inicio.year - 1)) <= 4:
                return
        partido = self.party_id(sigla) or self.party_id("S.PART.")
        if partido is None:
            return
        suplente = "suplente" in str(m.get("participacao") or "").lower()
        self.session.add(
            Mandate(
                politician_id=pol_id,
                party_id=partido,
                office=CargoPoliticoEnum.SENADOR,
                sphere=TipoEsferaEnum.FEDERAL,
                jurisdiction_state=(m.get("uf") or "DF")[:2],
                election_year=inicio.year - 1,
                term_number=1,
                start_date=inicio,
                end_date=fim,
                status=StatusMandatoEnum.SUPLENTE_EM_EXERCICIO if suplente else _status_mandato(fim),
            )
        )
        self._mandatos.add(chave)
        self.contadores["mandatos_criados"] += 1

    # ------------------------------------------------------------------ proposições
    TIPOS_SUPORTADOS = {
        TipoProposicaoEnum.PL,
        TipoProposicaoEnum.PEC,
        TipoProposicaoEnum.PLP,
        TipoProposicaoEnum.MPV,
        TipoProposicaoEnum.PDL,
        TipoProposicaoEnum.DECRETO_PRES,
        TipoProposicaoEnum.LEI_DELEGADA,
    }

    @classmethod
    def _tipo(cls, sigla: str) -> Optional[TipoProposicaoEnum]:
        try:
            t = TipoProposicaoEnum[sigla.upper()]
            return t if t in cls.TIPOS_SUPORTADOS else None
        except KeyError:
            return None

    def proposicao(self, prop: Dict[str, Any], casa: str) -> Optional[Any]:
        chave_ext = prop.get("camara_id") if casa == "CAMARA" else prop.get("senado_id")
        chave_cache = (casa, chave_ext or (prop.get("tipo"), prop.get("numero"), prop.get("ano")))
        if chave_cache in self._props:
            return self._props[chave_cache]
        tipo = self._tipo(prop.get("tipo") or "")
        numero, ano = int(prop.get("numero") or 0), int(prop.get("ano") or 0)
        if tipo is None or not numero or not ano:
            return None

        campo_ext = Proposition.external_camara_id if casa == "CAMARA" else Proposition.external_senado_id
        obj = self.session.query(Proposition).filter(campo_ext == chave_ext).first() if chave_ext else None
        if obj is None and ano >= ANO_NUMERACAO_UNICA:
            candidatos = (
                self.session.query(Proposition)
                .filter(Proposition.proposition_type == tipo, Proposition.number == numero, Proposition.year == ano)
                .all()
            )
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
        if obj is None:
            obj = self._criar_proposicao(prop, casa, tipo, numero, ano, chave_ext)
        self._props[chave_cache] = obj.id
        return obj.id

    def _criar_proposicao(
        self, prop: Dict[str, Any], casa: str, tipo: TipoProposicaoEnum, numero: int, ano: int, chave_ext: Any
    ) -> Any:
        titulo = prop.get("titulo") or f"{tipo.value} {numero}/{ano}"
        ementa = (prop.get("ementa") or "").strip()
        apresentacao = _date(prop.get("data_apresentacao"))
        if apresentacao is None:
            apresentacao = date(ano, 1, 1)  # coluna obrigatória; limite inferior, contabilizado (não é data real)
            self.contadores["datas_aproximadas"] += 1
        eixo, eixos = classify_proposition_impact(tipo.value, numero, ano, titulo, ementa)
        autor_cid = prop.get("autor_camara_id")
        autor_id = self.deputy_map.get(autor_cid) if autor_cid else None
        status = prop.get("status")
        obj = Proposition(
            external_camara_id=chave_ext if casa == "CAMARA" else None,
            external_senado_id=chave_ext if casa != "CAMARA" else None,
            proposition_type=tipo,
            number=numero,
            year=ano,
            title=titulo[:255],
            summary=ementa or titulo,
            thematic_area=classificar_setor_por_texto(titulo, ementa),
            presentation_date=apresentacao,
            status=(
                StatusTramitacaoEnum[status]
                if status in StatusTramitacaoEnum.__members__
                else StatusTramitacaoEnum.EM_TRAMITACAO
            ),
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
        self.session.add(obj)
        self.session.flush()
        self.contadores["proposicoes_criadas"] += 1
        return obj


# ---------------------------------------------------------------------------------------------- ex-parlamentares
def carregar_parlamentares_historicos(
    session: Session,
    data_dir: Path,
    deputy_map: Dict[int, Any],
    senator_map: Dict[int, Any],
    party_map: Dict[str, Any],
    ensure_party: EnsureParty,
    contexto: Optional[_Contexto] = None,
) -> Dict[str, int]:
    """Cria deputados da 56ª legislatura e senadores (titulares) de legislaturas anteriores com seus mandatos."""
    dados = load_json(Path(data_dir) / ARQUIVO_HISTORICOS, None)
    if not isinstance(dados, dict) or not dados.get("fonte") or dados.get("is_synthetic"):
        logger.warning("%s ausente ou sem proveniência — ex-parlamentares não carregados.", ARQUIVO_HISTORICOS)
        return {}
    ctx = contexto or _Contexto(session, deputy_map, senator_map, party_map, ensure_party)
    base = dict(ctx.contadores)

    for d in dados.get("deputados") or []:
        if d.get("camara_id"):
            ctx.garantir_deputado(int(d["camara_id"]), d)

    # Suplentes só entram se votaram (o arquivo lista também suplentes que podem nunca ter exercido o mandato).
    votantes_senado = _senadores_votantes(data_dir)
    for s in dados.get("senadores") or []:
        sid = s.get("senado_id")
        if not sid:
            continue
        titular = any("suplente" not in str(m.get("participacao") or "").lower() for m in s.get("mandatos") or [])
        if not titular and sid not in votantes_senado:
            continue
        info = dict(s)
        info["mandatos"] = [
            m
            for m in s.get("mandatos") or []
            if "suplente" not in str(m.get("participacao") or "").lower() or sid in votantes_senado
        ]
        ctx.garantir_senador(int(sid), info)

    session.flush()
    resultado = {
        k: ctx.contadores[k] - base[k] for k in ("politicos_criados", "politicos_vinculados", "mandatos_criados")
    }
    logger.info(
        "-> Ex-parlamentares: %d políticos criados, %d vinculados a registro existente, %d mandatos criados.",
        resultado["politicos_criados"],
        resultado["politicos_vinculados"],
        resultado["mandatos_criados"],
    )
    return resultado


def _senadores_votantes(data_dir: Path) -> set:
    votantes: set = set()
    for caminho in listar_arquivos_processados(Path(data_dir), "senado"):
        try:
            dados = ler_json_gz(caminho)
        except (OSError, ValueError):
            continue
        votantes.update(int(k) for k in (dados.get("parlamentares") or {}))
    return votantes


# ---------------------------------------------------------------------------------------------- votações
def carregar_votacoes(
    session: Session,
    data_dir: Path,
    deputy_map: Dict[int, Any],
    senator_map: Dict[int, Any],
    party_map: Dict[str, Any],
    ensure_party: EnsureParty,
) -> Dict[str, int]:
    ctx = _Contexto(session, deputy_map, senator_map, party_map, ensure_party)
    votos_total = 0
    for casa, prefixo in (("CAMARA", "camara"), ("SENADO", "senado")):
        for caminho in listar_arquivos_processados(Path(data_dir), prefixo):
            try:
                dados = ler_json_gz(caminho)
            except (OSError, ValueError) as exc:
                logger.error("Falha ao ler %s: %s", caminho.name, exc)
                continue
            if not _arquivo_confiavel(dados, caminho):
                continue
            votos_total += _carregar_arquivo(ctx, dados, casa)
            session.flush()
    ctx.contadores["votos_inseridos"] = votos_total
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


def _carregar_arquivo(ctx: _Contexto, dados: Dict[str, Any], casa: str) -> int:
    session = ctx.session
    casa_enum = CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS if casa == "CAMARA" else CasaLegislativaEnum.SENADO_FEDERAL
    mapa_politicos = ctx.deputy_map if casa == "CAMARA" else ctx.senator_map
    garantir = ctx.garantir_deputado if casa == "CAMARA" else ctx.garantir_senador

    # Parlamentares do arquivo (cria os que ainda não existem)
    for pid, info in (dados.get("parlamentares") or {}).items():
        garantir(int(pid), info)

    partidos = [ctx.party_id(s) for s in dados.get("partidos") or []]
    inseridos = 0
    stmt = _insert_ignorando_conflito(session)
    agora = datetime.utcnow()

    for s in dados.get("sessoes") or []:
        dt = _datetime(s.get("data_hora"))
        prop_id = ctx.proposicao(s.get("proposicao") or {}, casa)
        if dt is None or prop_id is None:
            ctx.contadores["sessoes_descartadas"] += 1
            continue

        aprovada = s.get("aprovada")
        if aprovada is None and casa == "CAMARA":
            aprovada = interpretar_aprovacao({"descricao": s.get("descricao")})
        t = s.get("totais") or {}
        ext_id = str(s["id"])
        obj = session.query(VotingSession).filter_by(external_id=ext_id).first()
        if obj is not None and obj.legislative_house != casa_enum:
            ctx.contadores["sessoes_descartadas"] += 1
            continue
        titulo = (s.get("proposicao") or {}).get("titulo") or "matéria"
        if obj is None:
            obj = VotingSession(
                external_id=ext_id,
                proposition_id=prop_id,
                legislative_house=casa_enum,
                session_datetime=dt,
                agenda_title=f"Votação sobre {titulo}"[:255],
                detailed_description=s.get("descricao"),
                is_secret_vote=bool(s.get("secreta")),
                is_approved=bool(aprovada),
            )
            session.add(obj)
            ctx.contadores["sessoes_novas"] += 1
        else:
            ctx.contadores["sessoes_atualizadas"] += 1
        obj.votes_yes_count = int(t.get("SIM", 0))
        obj.votes_no_count = int(t.get("NAO", 0))
        obj.votes_abstain_count = int(t.get("ABSTENCAO", 0))
        obj.votes_obstruction_count = int(t.get("OBSTRUCAO", 0))
        obj.government_orientation = s.get("orientacao_governo")
        obj.party_orientations = json.dumps(s["orientacoes"], ensure_ascii=False) if s.get("orientacoes") else None
        session.flush()

        linhas: List[Dict[str, Any]] = []
        for pol_ext, opcao, idx_partido in s.get("votos") or []:
            pol_id = mapa_politicos.get(int(pol_ext))
            if pol_id is None or opcao not in VotoOpcaoEnum.__members__:
                continue
            linhas.append(
                {
                    "id": uuid.uuid4(),
                    "created_at": agora,
                    "sessaoVotacaoId": obj.id,
                    "politicoId": pol_id,
                    "partidoId": partidos[idx_partido] if 0 <= idx_partido < len(partidos) else None,
                    "voto": VotoOpcaoEnum[opcao],
                }
            )
        ctx.contadores["votos_processados"] += len(linhas)
        for i in range(0, len(linhas), LOTE_VOTOS):
            resultado = session.execute(stmt, linhas[i : i + LOTE_VOTOS])
            if resultado.rowcount and resultado.rowcount > 0:
                inseridos += resultado.rowcount
    return inseridos
