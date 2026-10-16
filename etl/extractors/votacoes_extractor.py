"""
Extrator do histórico COMPLETO de votações nominais em plenário (Câmara e Senado) com a orientação do governo.

Fontes oficiais:
- Câmara: arquivos anuais de dados abertos (`votacoes`, `votacoesVotos`, `votacoesProposicoes`,
  `votacoesObjetos`, `votacoesOrientacoes`) em https://dadosabertos.camara.leg.br/arquivos/
- Senado: https://legis.senado.leg.br/dadosabertos/votacao?ano=AAAA (votos nominais) e
  .../plenario/votacao/orientacaoBancada/AAAAMMDD/AAAAMMDD (orientações de liderança, inclusive "Governo").

Saída (um arquivo por casa/ano, JSON compactado): `etl/data/processed/votacoes/{camara,senado}_AAAA.json.gz`.
Os arquivos brutos ficam em `etl/data/raw/votacoes/` (fora do git). Nada é inventado: sessão sem proposição de tipo
suportado, voto de tipo desconhecido e voto secreto são descartados/contados, nunca presumidos.
"""

import csv
import gzip
import json
import logging
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.extractors.camara_extractor import classificar_voto
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_bytes, atomic_write_json

logger = logging.getLogger("VotacoesExtractor")

CAMARA_BULK_URL = "https://dadosabertos.camara.leg.br/arquivos/{nome}/csv/{nome}-{ano}.csv"
CAMARA_API_URL = "https://dadosabertos.camara.leg.br/api/v2"
SENADO_API_URL = "https://legis.senado.leg.br/dadosabertos"

FONTE_CAMARA = "Câmara dos Deputados — Dados Abertos (arquivos anuais de votações, votos e orientações)"
FONTE_SENADO = "Senado Federal — Dados Abertos (/votacao e /plenario/votacao/orientacaoBancada)"

ANO_INICIAL_PADRAO = 2019
# Só proposições dos tipos que o modelo (TipoProposicaoEnum) representa. Requerimentos, destaques e
# mensagens (autoridades) ficam de fora: não são "matérias" do dossiê.
TIPOS_SUPORTADOS = frozenset({"PEC", "PL", "PLP", "MPV", "PDL"})
PASTA_PROCESSADA = "votacoes"
TTL_ANO_CORRENTE_SEGUNDOS = 24 * 3600

CODIGOS_VOTO_VALIDOS = frozenset({"SIM", "NAO", "ABSTENCAO", "OBSTRUCAO", "ARTIGO_17", "AUSENTE"})


# ---------------------------------------------------------------------------------------------- utilitários
def sem_acento(texto: Any) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto or "")) if not unicodedata.combining(c))


def normalizar_orientacao(valor: Any) -> Optional[str]:
    """Orientação (Câmara: Sim/Não/Liberado...; Senado: SIM/NÃO/LIVRE/OBSTRUÇÃO) -> código canônico ou None."""
    bruto = sem_acento(valor).strip().upper()
    if not bruto:
        return None
    if bruto in ("SIM", "NAO", "ABSTENCAO", "OBSTRUCAO"):
        return bruto
    if bruto in ("LIBERADO", "LIVRE"):
        return "LIBERADO"
    if bruto.startswith("ART") and "17" in bruto:
        return "ARTIGO_17"
    return None


_ROTULOS_GOVERNO = frozenset({"GOVERNO", "GOV"})


def orientacao_do_governo(orientacoes: Dict[str, Any]) -> Optional[str]:
    """
    Orientação da bancada do Governo. A Câmara a registra como "Governo" e como "GOV." (grafias que coexistem no
    mesmo arquivo). Se as duas aparecem com orientações diferentes, a votação fica sem orientação de governo.
    """
    encontradas = {
        normalizar_orientacao(valor)
        for rotulo, valor in orientacoes.items()
        if sem_acento(rotulo).upper().replace(".", "").strip() in _ROTULOS_GOVERNO
    }
    encontradas.discard(None)
    return encontradas.pop() if len(encontradas) == 1 else None


def classificar_voto_senado(sigla: Optional[str]) -> Optional[str]:
    """
    Voto nominal do Senado -> VotoOpcaoEnum. `None` = sem informação de voto (voto secreto "Votou" ou valor
    desconhecido): o voto NÃO é presumido. Códigos de não comparecimento (licenças, missão, P-NRV...) viram AUSENTE.
    """
    bruto = sem_acento(sigla).strip().upper()
    if not bruto or bruto == "VOTOU":
        return None
    if bruto == "SIM":
        return "SIM"
    if bruto == "NAO":
        return "NAO"
    if bruto.startswith("ABST"):
        return "ABSTENCAO"
    if bruto.startswith("OBSTR"):
        return "OBSTRUCAO"
    if bruto.startswith("PRESIDENTE"):
        return None  # art. 51 do RISF: o presidente só vota em desempate; não é voto nominal ordinário
    if bruto in {"AP", "LS", "MIS", "LP", "LAP", "NCOM", "NA", "P-NRV", "PNRV", "P-OD", "LC", "LG", "SUP"}:
        return "AUSENTE"
    return None


def _inteiro(valor: Any) -> Optional[int]:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _data_hora(valor: Any, data: Any = None) -> Optional[str]:
    """ISO 8601 (sem fuso) a partir da data/hora da fonte; só `data` => meia-noite daquela data."""
    texto = str(valor or "").strip()
    if texto:
        return texto
    d = str(data or "").strip()
    return f"{d}T00:00:00" if d else None


def gravar_json_gz(caminho: Path, obj: Any) -> Path:
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return atomic_write_bytes(caminho, gzip.compress(payload, compresslevel=6))


def ler_json_gz(caminho: Path) -> Any:
    with gzip.open(caminho, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def listar_arquivos_processados(data_dir: Path, casa: str) -> List[Path]:
    """Arquivos `{casa}_AAAA.json.gz` do diretório de dados processados, em ordem de ano."""
    pasta = Path(data_dir) / PASTA_PROCESSADA
    if not pasta.is_dir():
        return []
    return sorted(pasta.glob(f"{casa}_*.json.gz"))


def _ler_csv(caminho: Path) -> Iterator[Dict[str, str]]:
    with open(caminho, "r", encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh, delimiter=";")


def _status_da_situacao(situacao: Optional[str]) -> str:
    """Situação da proposição (texto da Câmara) -> StatusTramitacaoEnum. Desconhecido = em tramitação."""
    s = sem_acento(situacao).lower()
    if "transformad" in s and "norma" in s:
        return "APROVADA_E_SANCIONADA"
    if "arquivad" in s:
        return "ARQUIVADA"
    if "vetad" in s:
        return "VETADA_TOTAL"
    return "EM_TRAMITACAO"


# ---------------------------------------------------------------------------------------------- Câmara
class VotacoesCamaraExtractor:
    def __init__(
        self,
        raw_dir: Path = RAW_DATA_DIR / "votacoes",
        processed_dir: Path = PROCESSED_DATA_DIR,
        http: Optional[HttpClient] = None,
    ):
        self.raw_dir = Path(raw_dir)
        self.processed_dir = Path(processed_dir)
        self.http = http or HttpClient(timeout=300.0, max_retries=4, min_interval=0.2)

    # ------------------------------------------------------------------ download com cache
    def baixar_csv(self, nome: str, ano: int, force: bool = False) -> Optional[Path]:
        """Baixa `{nome}-{ano}.csv`. Anos encerrados são cacheados; o ano corrente expira em 24h. None = indisponível."""
        destino = self.raw_dir / "camara" / f"{nome}-{ano}.csv"
        if destino.exists() and not force:
            corrente = ano >= date.today().year
            if not corrente or (time.time() - destino.stat().st_mtime) < TTL_ANO_CORRENTE_SEGUNDOS:
                return destino
        url = CAMARA_BULK_URL.format(nome=nome, ano=ano)
        try:
            dados = self.http.get_bytes(url)
        except HttpError as exc:
            if exc.status == 404:
                logger.warning("%s-%s indisponível na fonte (404).", nome, ano)
                return destino if destino.exists() else None
            logger.error("Falha ao baixar %s: %s", url, exc)
            return destino if destino.exists() else None
        if not dados.lstrip(b"\xef\xbb\xbf").startswith(b'"'):
            logger.error("Conteúdo inesperado em %s (não é CSV) — ignorado.", url)
            return destino if destino.exists() else None
        atomic_write_bytes(destino, dados)
        logger.info("Baixado %s (%.1f MB)", destino.name, len(dados) / 1e6)
        return destino

    # ------------------------------------------------------------------ extração de um ano
    def extrair_ano(self, ano: int, force: bool = False, incluir_comissoes: bool = False) -> Optional[Dict[str, Any]]:
        arq_votacoes = self.baixar_csv("votacoes", ano, force)
        arq_votos = self.baixar_csv("votacoesVotos", ano, force)
        if not arq_votacoes or not arq_votos:
            return None
        arq_props = self.baixar_csv("votacoesProposicoes", ano, force)
        arq_objetos = self.baixar_csv("votacoesObjetos", ano, force)
        arq_orient = self.baixar_csv("votacoesOrientacoes", ano, force)

        # 1. Votações de plenário e opcionalmente comissões
        votacoes: Dict[str, Dict[str, str]] = {}
        for row in _ler_csv(arq_votacoes):
            sigla = (row.get("siglaOrgao") or "").strip().upper()
            if row.get("id") and (sigla == "PLEN" or (incluir_comissoes and sigla)):
                votacoes[row["id"]] = row

        # 2. Votos nominais (somente das votações de plenário)
        partidos: Dict[str, int] = {}
        votos: Dict[str, List[List[Any]]] = defaultdict(list)
        parlamentares: Dict[int, Dict[str, Any]] = {}
        desconhecidos: Counter = Counter()
        for row in _ler_csv(arq_votos):
            vid = row.get("idVotacao")
            if vid not in votacoes:
                continue
            opcao = classificar_voto(row.get("voto"))
            dep_id = _inteiro(row.get("deputado_id"))
            if dep_id is None:
                continue
            if opcao is None:
                desconhecidos[row.get("voto")] += 1
                continue
            sigla = (row.get("deputado_siglaPartido") or "").strip()
            idx_partido = partidos.setdefault(sigla, len(partidos)) if sigla else -1
            votos[vid].append([dep_id, opcao, idx_partido])
            reg = parlamentares.setdefault(
                dep_id,
                {
                    "nome": row.get("deputado_nome"),
                    "partido": sigla or None,
                    "uf": row.get("deputado_siglaUf") or None,
                    "foto_url": row.get("deputado_urlFoto") or None,
                    "legislaturas": [],
                },
            )
            leg = _inteiro(row.get("deputado_idLegislatura"))
            if leg and leg not in reg["legislaturas"]:
                reg["legislaturas"].append(leg)
        if desconhecidos:
            logger.warning("Câmara %s: votos com tipo desconhecido descartados: %s", ano, dict(desconhecidos))

        com_votos = {vid for vid, lista in votos.items() if lista}

        # 3. Proposição de cada votação (apenas tipos suportados)
        props_por_votacao = self._proposicoes_por_votacao(arq_props, arq_objetos, com_votos, votacoes)

        # 4. Orientações de bancada
        orientacoes = self._orientacoes(arq_orient, com_votos)

        sessoes: List[Dict[str, Any]] = []
        sem_proposicao = ambiguas = 0
        for vid in sorted(com_votos):
            escolhida, ambigua = props_por_votacao.get(vid, (None, False))
            if not escolhida:
                sem_proposicao += 1
                continue
            ambiguas += int(ambigua)
            v = votacoes[vid]
            totais = Counter(item[1] for item in votos[vid])
            ori = orientacoes.get(vid, {})
            aprov = (v.get("aprovacao") or "").strip()
            orgao = (v.get("siglaOrgao") or "PLEN").strip().upper()
            desc_prefix = f"[{orgao}] " if orgao != "PLEN" else ""
            sessoes.append(
                {
                    "id": vid,
                    "orgao": orgao,
                    "is_comissao": orgao != "PLEN",
                    "data_hora": _data_hora(v.get("dataHoraRegistro"), v.get("data")),
                    "descricao": desc_prefix + (v.get("descricao") or "")[:2000],
                    "aprovada": {"1": True, "0": False}.get(aprov),
                    "proposicao": escolhida,
                    "orientacao_governo": orientacao_do_governo(ori),
                    "orientacoes": {k: n for k, o in ori.items() if (n := normalizar_orientacao(o))},
                    "totais": {k: totais.get(k, 0) for k in ("SIM", "NAO", "ABSTENCAO", "OBSTRUCAO", "ARTIGO_17")},
                    "votos": votos[vid],
                }
            )

        logger.info(
            "Câmara %s: %d votações em plenário com voto nominal, %d sessões mantidas "
            "(%d sem proposição de tipo suportado, %d com vínculo ambíguo), %d votos.",
            ano,
            len(com_votos),
            len(sessoes),
            sem_proposicao,
            ambiguas,
            sum(len(s["votos"]) for s in sessoes),
        )
        usados = {item[0] for s in sessoes for item in s["votos"]}
        return {
            "casa": "CAMARA",
            "ano": ano,
            "fonte": FONTE_CAMARA,
            "is_synthetic": False,
            "extraido_em": datetime.now().isoformat(timespec="seconds"),
            "partidos": [p for p, _ in sorted(partidos.items(), key=lambda kv: kv[1])],
            "parlamentares": {str(k): v for k, v in parlamentares.items() if k in usados},
            "sessoes": sessoes,
            "descartes": {
                "sem_proposicao_suportada": sem_proposicao,
                "vinculo_ambiguo": ambiguas,
                "votos_tipo_desconhecido": sum(desconhecidos.values()),
            },
        }

    @staticmethod
    def _proposicoes_por_votacao(
        arq_props: Optional[Path],
        arq_objetos: Optional[Path],
        ids: Set[str],
        votacoes: Dict[str, Dict[str, str]],
    ) -> Dict[str, Tuple[Optional[Dict[str, Any]], bool]]:
        """
        Escolhe UMA proposição de tipo suportado por votação. Prioridade: (1) objeto direto da votação;
        (2) a última proposição apresentada na votação; (3) a primeira listada. `ambigua` marca múltiplos candidatos
        distintos (a escolha é determinística, mas vale auditar).
        """

        def registro(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
            tipo = (row.get("proposicao_siglaTipo") or "").upper()
            if tipo not in TIPOS_SUPORTADOS:
                return None
            numero, ano_p = _inteiro(row.get("proposicao_numero")), _inteiro(row.get("proposicao_ano"))
            cid = _inteiro(row.get("proposicao_id"))
            if not (numero and ano_p and cid):
                return None
            return {
                "camara_id": cid,
                "tipo": tipo,
                "numero": numero,
                "ano": ano_p,
                "titulo": f"{tipo} {numero}/{ano_p}",
                "ementa": (row.get("proposicao_ementa") or "").strip(),
            }

        candidatos: Dict[str, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
        for prioridade, arquivo in ((0, arq_objetos), (1, arq_props)):
            if not arquivo:
                continue
            for row in _ler_csv(arquivo):
                vid = row.get("idVotacao")
                if vid not in ids:
                    continue
                reg = registro(row)
                if reg:
                    candidatos[vid].append((prioridade, reg))

        resultado: Dict[str, Tuple[Optional[Dict[str, Any]], bool]] = {}
        for vid, lista in candidatos.items():
            ultima = _inteiro(votacoes[vid].get("ultimaApresentacaoProposicao_idProposicao"))
            distintos = {r["camara_id"] for _, r in lista}
            ordenados = sorted(lista, key=lambda pr: (pr[0], pr[1]["camara_id"] != ultima))
            resultado[vid] = (ordenados[0][1], len(distintos) > 1)
        return resultado

    @staticmethod
    def _orientacoes(arq: Optional[Path], ids: Set[str]) -> Dict[str, Dict[str, str]]:
        resultado: Dict[str, Dict[str, str]] = defaultdict(dict)
        if not arq:
            return resultado
        for row in _ler_csv(arq):
            vid = row.get("idVotacao")
            if vid in ids and row.get("siglaBancada"):
                resultado[vid].setdefault(row["siglaBancada"].strip(), row.get("orientacao") or "")
        return resultado

    # ------------------------------------------------------------------ detalhes das proposições (data, situação, autor)
    def enriquecer_proposicoes(self, ids: Iterable[int], max_workers: int = 6) -> Dict[int, Dict[str, Any]]:
        """`/proposicoes/{id}` e `/autores` com cache por id em raw/votacoes/proposicoes. Falha => campos ausentes."""
        pasta = self.raw_dir / "proposicoes"
        saida: Dict[int, Dict[str, Any]] = {}

        def um(pid: int) -> Tuple[int, Optional[Dict[str, Any]]]:
            cache = pasta / f"{pid}.json"
            if cache.exists():
                try:
                    return pid, json.loads(cache.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
            try:
                det = self.http.get_json(f"{CAMARA_API_URL}/proposicoes/{pid}", timeout=30.0)
                aut = self.http.get_json(f"{CAMARA_API_URL}/proposicoes/{pid}/autores", timeout=30.0)
            except HttpError as exc:
                logger.warning("Proposição %s sem detalhes (%s).", pid, exc)
                return pid, None
            dados = (det or {}).get("dados") or {}
            autores = (aut or {}).get("dados") or []
            primeiro = autores[0] if autores else {}
            uri = primeiro.get("uri") or ""
            autor_cid = _inteiro(uri.split("/deputados/")[-1]) if "/deputados/" in uri else None
            reg = {
                "data_apresentacao": (dados.get("dataApresentacao") or "")[:10] or None,
                "ementa": dados.get("ementa"),
                "url_inteiro_teor": dados.get("urlInteiroTeor"),
                "status": _status_da_situacao((dados.get("statusProposicao") or {}).get("descricaoSituacao")),
                "autor_nome": primeiro.get("nome"),
                "autor_camara_id": autor_cid,
                "autor_partido": primeiro.get("siglaPartido"),
                "total_autores": len(autores),
            }
            if dados:  # só cacheia resposta válida
                atomic_write_json(cache, reg, indent=None)
            return pid, reg

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for pid, reg in ex.map(um, sorted(set(ids))):
                if reg:
                    saida[pid] = reg
        return saida

    # ------------------------------------------------------------------ orquestração
    def run(self, anos: Optional[List[int]] = None, force: bool = False) -> Dict[str, Any]:
        anos = anos or list(range(ANO_INICIAL_PADRAO, date.today().year + 1))
        resumo: Dict[str, Any] = {"anos": {}, "falhas": []}
        for ano in anos:
            dados = self.extrair_ano(ano, force)
            if not dados or not dados["sessoes"]:
                logger.warning("Câmara %s: nada extraído — arquivo existente preservado.", ano)
                resumo["falhas"].append(ano)
                continue
            props = {s["proposicao"]["camara_id"] for s in dados["sessoes"]}
            detalhes = self.enriquecer_proposicoes(props)
            for s in dados["sessoes"]:
                s["proposicao"].update({k: v for k, v in (detalhes.get(s["proposicao"]["camara_id"]) or {}).items()})
            gravar_json_gz(self.processed_dir / PASTA_PROCESSADA / f"camara_{ano}.json.gz", dados)
            resumo["anos"][ano] = {
                "sessoes": len(dados["sessoes"]),
                "votos": sum(len(s["votos"]) for s in dados["sessoes"]),
                "com_orientacao_governo": sum(1 for s in dados["sessoes"] if s["orientacao_governo"]),
            }
        return resumo


# ---------------------------------------------------------------------------------------------- Senado
class VotacoesSenadoExtractor:
    def __init__(
        self,
        raw_dir: Path = RAW_DATA_DIR / "votacoes",
        processed_dir: Path = PROCESSED_DATA_DIR,
        http: Optional[HttpClient] = None,
        hoje: Optional[date] = None,
    ):
        self.raw_dir = Path(raw_dir)
        self.processed_dir = Path(processed_dir)
        self.http = http or HttpClient(timeout=120.0, max_retries=4, min_interval=0.3)
        self._hoje = hoje

    @property
    def hoje(self) -> date:
        return self._hoje or date.today()

    def _ano_em_andamento(self, ano: int) -> bool:
        """Ano cujo cache expira: o corrente e, até 1º de março, o anterior (a lista do Senado fecha com atraso)."""
        hoje = self.hoje
        return ano >= hoje.year or (ano == hoje.year - 1 and hoje < date(hoje.year, 3, 1))

    def _json_com_cache(self, url: str, nome: str, ano: int, force: bool) -> Optional[Any]:
        destino = self.raw_dir / "senado" / f"{nome}-{ano}.json"
        if destino.exists() and not force:
            corrente = self._ano_em_andamento(ano)
            if not corrente or (time.time() - destino.stat().st_mtime) < TTL_ANO_CORRENTE_SEGUNDOS:
                try:
                    return json.loads(destino.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
        try:
            dados = self.http.get_json(url)
        except HttpError as exc:
            logger.error("Falha ao consultar %s: %s", url, exc)
            return None
        if dados:
            atomic_write_json(destino, dados, indent=None)
        return dados

    def _sessoes_plenario(
        self, ano: int, force: bool, partidos: Dict[str, int], parlamentares: Dict[int, Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Votações nominais do ano pela API de plenário (janelas mensais), no formato das sessões do extrator.

        Devolve também os meses cuja consulta falhou ("AAAA-MM"): mês vazio e mês com falha são coisas diferentes.
        """
        sessoes: List[Dict[str, Any]] = []
        falhas: List[str] = []
        hoje = self.hoje
        for mes in range(1, 13):
            ini = date(ano, mes, 1)
            if ini > hoje:
                break
            fim = (date(ano + (mes == 12), mes % 12 + 1, 1) - timedelta(days=1)) if mes < 12 else date(ano, 12, 31)
            url = f"{SENADO_API_URL}/plenario/lista/votacao/{ini:%Y%m%d}/{min(fim, hoje):%Y%m%d}"
            payload = self._json_com_cache(url, f"plenario_lista_{mes:02d}", ano, force)
            if payload is None:
                falhas.append(f"{ano}-{mes:02d}")
                continue
            bloco = ((payload or {}).get("ListaVotacoes") or {}).get("Votacoes") or {}
            itens = bloco.get("Votacao") or []
            for r in itens if isinstance(itens, list) else [itens]:
                tipo = (r.get("SiglaMateria") or "").upper()
                numero, ano_materia = _inteiro(r.get("NumeroMateria")), _inteiro(r.get("AnoMateria"))
                if tipo not in TIPOS_SUPORTADOS or not numero or not ano_materia:
                    continue
                if not r.get("CodigoSessaoVotacao"):
                    logger.warning(
                        "Votação do plenário sem CodigoSessaoVotacao descartada: %s", r.get("DescricaoVotacao")
                    )
                    continue
                secreta = (r.get("Secreta") or "N").upper() == "S"
                votos: List[List[Any]] = []
                if not secreta:
                    brutos = (r.get("Votos") or {}).get("VotoParlamentar") or []
                    for v in brutos if isinstance(brutos, list) else [brutos]:
                        codigo, opcao = _inteiro(v.get("CodigoParlamentar")), classificar_voto_senado(v.get("Voto"))
                        if codigo is None or opcao is None:
                            continue
                        sigla = (v.get("SiglaPartido") or "").strip()
                        idx = partidos.setdefault(sigla, len(partidos)) if sigla else -1
                        votos.append([codigo, opcao, idx])
                        parlamentares.setdefault(
                            codigo,
                            {
                                "nome": v.get("NomeParlamentar"),
                                "partido": sigla or None,
                                "uf": v.get("SiglaUF") or None,
                            },
                        )
                if not votos and not secreta:
                    continue
                totais = Counter(item[1] for item in votos)
                if secreta:  # sem voto individual: usa os totais publicados pela fonte
                    totais = Counter(
                        {
                            "SIM": _inteiro(r.get("TotalVotosSim")) or 0,
                            "NAO": _inteiro(r.get("TotalVotosNao")) or 0,
                            "ABSTENCAO": _inteiro(r.get("TotalVotosAbstencao")) or 0,
                        }
                    )
                hora = (r.get("HoraInicio") or "00:00")[:5]
                sessoes.append(
                    {
                        "id": f"SEN-{r.get('CodigoSessaoVotacao')}",
                        "data_hora": _data_hora(f"{r.get('DataSessao')}T{hora}:00", r.get("DataSessao")),
                        "descricao": (r.get("DescricaoVotacao") or "")[:2000],
                        "aprovada": {"A": True, "R": False}.get((r.get("Resultado") or "").upper()),
                        "secreta": secreta,
                        "proposicao": {
                            "senado_id": _inteiro(r.get("CodigoMateria")),
                            "tipo": tipo,
                            "numero": numero,
                            "ano": ano_materia,
                            "titulo": f"{tipo} {numero}/{ano_materia}",
                            "ementa": "",
                            "data_apresentacao": None,
                        },
                        "orientacao_governo": None,
                        "orientacoes": {},
                        "totais": {k2: totais.get(k2, 0) for k2 in ("SIM", "NAO", "ABSTENCAO", "OBSTRUCAO")},
                        "votos": votos,
                    }
                )
        return sessoes, falhas

    def extrair_ano(self, ano: int, force: bool = False) -> Optional[Dict[str, Any]]:
        lista = self._json_com_cache(f"{SENADO_API_URL}/votacao?ano={ano}", "votacao", ano, force)
        if not isinstance(lista, list):
            return None
        orient_raw = self._json_com_cache(
            f"{SENADO_API_URL}/plenario/votacao/orientacaoBancada/{ano}0101/{ano}1231", "orientacoes", ano, force
        )
        orient_por_seq: Dict[int, Dict[str, Any]] = {}
        for item in (orient_raw or {}).get("votacoes", []) if isinstance(orient_raw, dict) else []:
            seq = _inteiro(item.get("sequencialVotacao"))
            if seq is not None:
                orient_por_seq[seq] = item

        partidos: Dict[str, int] = {}
        parlamentares: Dict[int, Dict[str, Any]] = {}
        sessoes: List[Dict[str, Any]] = []
        fora_tipo = nao_senado = sem_voto = 0
        for r in lista:
            tipo = (r.get("sigla") or "").upper()
            if (r.get("casaSessao") or "SF") != "SF":
                nao_senado += 1
                continue
            numero, ano_materia = _inteiro(r.get("numero")), _inteiro(r.get("ano"))
            if tipo not in TIPOS_SUPORTADOS or not numero or not ano_materia:
                fora_tipo += 1
                continue
            secreta = (r.get("votacaoSecreta") or "N").upper() == "S"
            votos: List[List[Any]] = []
            if not secreta:
                for v in r.get("votos") or []:
                    codigo, opcao = _inteiro(v.get("codigoParlamentar")), classificar_voto_senado(
                        v.get("siglaVotoParlamentar")
                    )
                    if codigo is None or opcao is None:
                        continue
                    sigla = (v.get("siglaPartidoParlamentar") or "").strip()
                    idx = partidos.setdefault(sigla, len(partidos)) if sigla else -1
                    votos.append([codigo, opcao, idx])
                    parlamentares.setdefault(
                        codigo,
                        {
                            "nome": v.get("nomeParlamentar"),
                            "partido": sigla or None,
                            "uf": v.get("siglaUFParlamentar") or None,
                        },
                    )
            if not votos and not secreta:
                sem_voto += 1
                continue

            seq = _inteiro(r.get("sequencialVotacao"))
            ori_item = orient_por_seq.get(seq) if seq is not None else None
            ori: Dict[str, str] = {}
            for o in (ori_item or {}).get("orientacoesLideranca") or []:
                n = normalizar_orientacao(o.get("voto"))
                if o.get("partido") and n:
                    ori.setdefault(str(o["partido"]).strip(), n)
            totais = Counter(item[1] for item in votos)
            if secreta:  # sem voto individual: usa os totais publicados pela fonte
                totais = Counter(
                    {
                        "SIM": r.get("totalVotosSim") or 0,
                        "NAO": r.get("totalVotosNao") or 0,
                        "ABSTENCAO": r.get("totalVotosAbstencao") or 0,
                    }
                )
            resultado = (r.get("resultadoVotacao") or "").upper()
            sessoes.append(
                {
                    "id": f"SEN-{r.get('codigoSessaoVotacao')}",
                    "data_hora": _data_hora((ori_item or {}).get("dataInicioVotacao"), r.get("dataSessao")),
                    "descricao": (r.get("descricaoVotacao") or "")[:2000],
                    "aprovada": {"A": True, "R": False}.get(resultado),
                    "secreta": secreta,
                    "proposicao": {
                        "senado_id": _inteiro(r.get("codigoMateria")),
                        "tipo": tipo,
                        "numero": numero,
                        "ano": ano_materia,
                        "titulo": f"{tipo} {numero}/{ano_materia}",
                        "ementa": (r.get("ementa") or "").strip(),
                        "data_apresentacao": (r.get("dataApresentacao") or "")[:10] or None,
                    },
                    "orientacao_governo": orientacao_do_governo(ori),
                    "orientacoes": ori,
                    "totais": {k: totais.get(k, 0) for k in ("SIM", "NAO", "ABSTENCAO", "OBSTRUCAO")},
                    "votos": votos,
                }
            )

        # A lista anual (`/votacao?ano=`) costuma ficar semanas atrasada. As votações nominais do plenário por data
        # (`/plenario/lista/votacao`) são atuais, então completam o que a lista anual ainda não trouxe.
        conhecidas = {s["id"] for s in sessoes}
        do_plenario, falhas_meses = self._sessoes_plenario(ano, force, partidos, parlamentares)
        for sessao in do_plenario:
            if sessao["id"] not in conhecidas:
                sessoes.append(sessao)
                conhecidas.add(sessao["id"])
        logger.info(
            "Senado %s: %d votações de %d registros (%d tipo não suportado, %d outra casa, %d sem voto nominal).",
            ano,
            len(sessoes),
            len(lista),
            fora_tipo,
            nao_senado,
            sem_voto,
        )
        return {
            "casa": "SENADO",
            "ano": ano,
            "fonte": FONTE_SENADO,
            "is_synthetic": False,
            "extraido_em": datetime.now().isoformat(timespec="seconds"),
            "partidos": [p for p, _ in sorted(partidos.items(), key=lambda kv: kv[1])],
            "parlamentares": {str(k): v for k, v in parlamentares.items()},
            "sessoes": sessoes,
            "descartes": {"tipo_nao_suportado": fora_tipo, "sem_voto_nominal": sem_voto},
            "falhas_meses": falhas_meses,
        }

    def run(self, anos: Optional[List[int]] = None, force: bool = False) -> Dict[str, Any]:
        """`falhas` lista o ano inteiro sem dados (int) e o mês do plenário que falhou ("AAAA-MM").

        Com mês falho o arquivo do ano não é regravado: regravar sem as sessões daquele mês as apagaria.
        """
        anos = anos or list(range(ANO_INICIAL_PADRAO, self.hoje.year + 1))
        resumo: Dict[str, Any] = {"anos": {}, "falhas": []}
        for ano in anos:
            dados = self.extrair_ano(ano, force)
            if not dados or not dados["sessoes"]:
                logger.warning("Senado %s: nada extraído — arquivo existente preservado.", ano)
                resumo["falhas"].append(ano)
                continue
            if dados.get("falhas_meses"):
                logger.warning(
                    "Senado %s: consulta do plenário falhou em %s — arquivo existente preservado.",
                    ano,
                    ", ".join(dados["falhas_meses"]),
                )
                resumo["falhas"].extend(dados["falhas_meses"])
                continue
            gravar_json_gz(self.processed_dir / PASTA_PROCESSADA / f"senado_{ano}.json.gz", dados)
            resumo["anos"][ano] = {
                "sessoes": len(dados["sessoes"]),
                "votos": sum(len(s["votos"]) for s in dados["sessoes"]),
                "com_orientacao_governo": sum(1 for s in dados["sessoes"] if s["orientacao_governo"]),
            }
        return resumo


# ---------------------------------------------------------------------------------------------- parlamentares de legislaturas anteriores
def _como_lista(valor: Any) -> List[Any]:
    if not valor:
        return []
    return valor if isinstance(valor, list) else [valor]


def extrair_parlamentares_historicos(
    legislaturas_deputados: Tuple[int, ...] = (55, 56),
    legislaturas_senadores: Tuple[int, ...] = (55, 56, 57),
    http: Optional[HttpClient] = None,
    processed_dir: Path = PROCESSED_DATA_DIR,
) -> Dict[str, Any]:
    """
    Deputados e senadores de legislaturas anteriores (ex-parlamentares autores de emendas/CEAP e votos).
    Dado oficial da lista por legislatura; nada derivado de ids. Não sobrescreve arquivo bom com resultado vazio.
    """
    from etl.extractors.camara_extractor import CamaraExtractor

    http = http or HttpClient(timeout=60.0, max_retries=4, min_interval=0.2)
    cam = CamaraExtractor(http=http)
    deputados: Dict[int, Dict[str, Any]] = {}
    for leg in legislaturas_deputados:
        for d in cam.fetch_deputados(legislatura=leg):
            reg = deputados.setdefault(d["camara_id"], {**d, "legislaturas": []})
            if leg not in reg["legislaturas"]:
                reg["legislaturas"].append(leg)

    senadores: Dict[int, Dict[str, Any]] = {}
    for leg in legislaturas_senadores:
        try:
            dados = http.get_json(f"{SENADO_API_URL}/senador/lista/legislatura/{leg}")
        except HttpError as exc:
            logger.error("Senadores da legislatura %s indisponíveis: %s", leg, exc)
            continue
        try:
            lista = _como_lista(dados["ListaParlamentarLegislatura"]["Parlamentares"]["Parlamentar"])
        except (TypeError, KeyError):
            logger.error("Resposta inesperada da lista de senadores da legislatura %s.", leg)
            continue
        for p in lista:
            ident = p.get("IdentificacaoParlamentar") or {}
            codigo = _inteiro(ident.get("CodigoParlamentar"))
            if codigo is None:
                continue
            foto_url = (
                f"https://legis.senado.leg.br/senadores/fotos-oficiais/{codigo}"
                if codigo
                else ident.get("UrlFotoParlamentar")
            )
            reg = senadores.setdefault(
                codigo,
                {
                    "senado_id": codigo,
                    "nome_eleitoral": ident.get("NomeParlamentar"),
                    "nome_civil": ident.get("NomeCompletoParlamentar") or ident.get("NomeParlamentar"),
                    "partido_sigla": ident.get("SiglaPartidoParlamentar"),
                    "foto_url": foto_url,
                    "mandatos": [],
                },
            )
            for m in _como_lista((p.get("Mandatos") or {}).get("Mandato")):
                pri, seg = m.get("PrimeiraLegislaturaDoMandato") or {}, m.get("SegundaLegislaturaDoMandato") or {}
                item = {
                    "uf": m.get("UfParlamentar"),
                    "inicio": pri.get("DataInicio"),
                    "fim": seg.get("DataFim") or pri.get("DataFim"),
                    "participacao": m.get("DescricaoParticipacao"),
                }
                if item["inicio"] and item not in reg["mandatos"]:
                    reg["mandatos"].append(item)

    if not deputados and not senadores:
        logger.error("Nenhum parlamentar histórico extraído — arquivo existente preservado.")
        return {"deputados": 0, "senadores": 0}
    atomic_write_json(
        Path(processed_dir) / "parlamentares_legislaturas_anteriores.json",
        {
            "fonte": "Câmara (/deputados?idLegislatura) e Senado (/senador/lista/legislatura) — Dados Abertos",
            "is_synthetic": False,
            "extraido_em": datetime.now().isoformat(timespec="seconds"),
            "deputados": list(deputados.values()),
            "senadores": list(senadores.values()),
        },
        indent=None,
    )
    logger.info("Parlamentares históricos: %d deputados e %d senadores.", len(deputados), len(senadores))
    return {"deputados": len(deputados), "senadores": len(senadores)}


def run_votacoes(
    anos: Optional[List[int]] = None, force: bool = False, processed_dir: Path = PROCESSED_DATA_DIR
) -> Dict[str, Any]:
    """Pipeline completo da etapa `--votacoes`. Levanta RuntimeError se nenhuma casa produziu dados."""
    resumo = {
        "camara": VotacoesCamaraExtractor(processed_dir=processed_dir).run(anos, force),
        "senado": VotacoesSenadoExtractor(processed_dir=processed_dir).run(anos, force),
        "parlamentares_historicos": extrair_parlamentares_historicos(processed_dir=processed_dir),
    }
    if not resumo["camara"]["anos"] and not resumo["senado"]["anos"]:
        raise RuntimeError("Nenhuma votação extraída (Câmara e Senado falharam).")
    return resumo


__all__ = [
    "VotacoesCamaraExtractor",
    "VotacoesSenadoExtractor",
    "classificar_voto_senado",
    "extrair_parlamentares_historicos",
    "gravar_json_gz",
    "ler_json_gz",
    "listar_arquivos_processados",
    "normalizar_orientacao",
    "orientacao_do_governo",
    "run_votacoes",
]
