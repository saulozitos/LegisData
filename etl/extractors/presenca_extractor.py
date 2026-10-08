"""
Extrator de PRESENÇA (Câmara) e PARTICIPAÇÃO EM VOTAÇÕES NOMINAIS (Senado).

Somente fontes oficiais, sem nenhum valor presumido ou sorteado.

Câmara dos Deputados — presença diária em plenário, com justificativa:
  1. Dias com sessão deliberativa no plenário:
     GET https://dadosabertos.camara.leg.br/api/v2/eventos?dataInicio&dataFim&codTipoEvento=110
     (codTipoEvento=110 = "Sessão Deliberativa"; filtramos órgão PLEN e situação "Encerrada").
  2. Para cada dia: WS legado
     GET https://www.camara.leg.br/SitCamaraWS/sessoesreunioes.asmx/ListarPresencasDia
         ?data=DD/MM/AAAA&numMatriculaParlamentar=&siglaPartido=&siglaUF=
  3. Mapa carteira -> ideCadastro (= id da API v2 = Politico.camaraId):
     GET https://www.camara.leg.br/SitCamaraWS/Deputados.asmx/ObterDeputados
     Verificado em 08/10/2026 (dia 10/06/2025): ``carteiraParlamentar`` do
     ListarPresencasDia é igual a ``matricula`` do ObterDeputados (464 de 464
     deputados casados também por nome+UF concordaram). ObterDeputados só lista
     deputados em exercício: quem saiu fica sem ``camara_id`` aqui e o loader
     tenta nome parlamentar + UF.

Senado Federal — NÃO existe lista de presença por sessão na API. A métrica é
"participação em votações nominais" (e licenças oficiais), nunca "presença":
  GET https://legis.senado.leg.br/dadosabertos/votacao?dataInicio=AAAA-MM-DD&dataFim=AAAA-MM-DD
      (intervalo máximo de 1 ano por requisição)
  GET https://legis.senado.leg.br/dadosabertos/senador/{codigo}/licencas.json?dataInicio=AAAAMMDD
  Siglas de comparecimento: /dadosabertos/plenario/lista/tiposComparecimento

Uso:
  PYTHONPATH=. python etl/extractors/presenca_extractor.py --inicio 2025-02-01 --fim 2025-12-31
  (opções: --somente camara|senado, --licencas, --saida DIR)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR  # noqa: E402
from etl.http_oficial import CachedHttpClient  # noqa: E402
from etl.vinculos import normalizar  # noqa: E402

logger = logging.getLogger("PresencaExtractor")

CAMARA_EVENTOS_URL = "https://dadosabertos.camara.leg.br/api/v2/eventos"
CAMARA_PRESENCAS_DIA_URL = "https://www.camara.leg.br/SitCamaraWS/sessoesreunioes.asmx/ListarPresencasDia"
CAMARA_DEPUTADOS_WS_URL = "https://www.camara.leg.br/SitCamaraWS/Deputados.asmx/ObterDeputados"
SENADO_VOTACAO_URL = "https://legis.senado.leg.br/dadosabertos/votacao"
SENADO_LICENCAS_URL = "https://legis.senado.leg.br/dadosabertos/senador/{codigo}/licencas.json"

FONTE_CAMARA = "Câmara dos Deputados - SitCamaraWS ListarPresencasDia"
FONTE_SENADO = "Senado Federal - Dados Abertos /votacao (votações nominais)"

# Valores de TipoPresencaEnum (mantidos como string para não depender do backend)
PRESENTE = "PRESENTE"
AUSENCIA_JUSTIFICADA = "AUSENCIA_JUSTIFICADA"
AUSENCIA_NAO_JUSTIFICADA = "AUSENCIA_NAO_JUSTIFICADA"
LICENCA_MEDICA = "LICENCA_MEDICA"
MISSAO_OFICIAL = "MISSAO_OFICIAL"
PARTICIPOU_VOTACAO = "PARTICIPOU_VOTACAO"
PRESENTE_SEM_VOTO = "PRESENTE_SEM_VOTO"


# ---------------------------------------------------------------------------
# Câmara
# ---------------------------------------------------------------------------

def mapear_status_camara(descricao_frequencia: str, justificativa: Optional[str]) -> Optional[str]:
    """Converte descricaoFrequenciaDia (+ justificativa) do WS em TipoPresencaEnum.

    Rótulos observados de fato em 10/06/2025: "Presença", "Ausência",
    "Ausência justificada" com justificativas "Missão Autorizada",
    "Licença para Tratamento de Saúde" e "Decisão da Mesa".
    Retorna None para rótulos desconhecidos (o registro é descartado e contado).
    """
    freq = normalizar(descricao_frequencia)
    just = normalizar(justificativa)
    if freq == "PRESENCA":
        return PRESENTE
    if freq == "AUSENCIA":
        return AUSENCIA_NAO_JUSTIFICADA
    if freq.startswith("AUSENCIA JUSTIFICADA"):
        if "TRATAMENTO DE SAUDE" in just or just.startswith("LICENCA SAUDE"):
            return LICENCA_MEDICA
        if "MISSAO" in just:
            return MISSAO_OFICIAL
        return AUSENCIA_JUSTIFICADA
    return None


def parse_presencas_dia_xml(conteudo: bytes) -> Tuple[Optional[str], List[dict]]:
    """Lê o XML de ListarPresencasDia. Retorna (legislatura, lista de parlamentares)."""
    raiz = ET.fromstring(conteudo)
    legislatura = (raiz.findtext("legislatura") or "").strip() or None
    registros = []
    for p in raiz.iter("parlamentar"):
        nome_completo = (p.findtext("nomeParlamentar") or "").strip()
        # "Fulano de Tal-PL/MT": o nome vem antes do último hífen
        nome = nome_completo.rsplit("-", 1)[0].strip() if "-" in nome_completo else nome_completo
        justificativa = (p.findtext("justificativa") or "").strip() or None
        sessoes = [
            {
                "inicio": (s.findtext("inicio") or "").strip() or None,
                "descricao": (s.findtext("descricao") or "").strip() or None,
                "frequencia": (s.findtext("frequencia") or "").strip() or None,
            }
            for s in p.iter("sessaoDia")
        ]
        registros.append({
            "carteira": (p.findtext("carteiraParlamentar") or "").strip() or None,
            "nome_parlamentar": nome,
            "sigla_partido": (p.findtext("siglaPartido") or "").strip() or None,
            "uf": (p.findtext("siglaUF") or "").strip() or None,
            "descricao_frequencia": (p.findtext("descricaoFrequenciaDia") or "").strip(),
            "justificativa": justificativa,
            "sessoes": sessoes,
        })
    return legislatura, registros


def parse_obter_deputados_xml(conteudo: bytes) -> Dict[str, dict]:
    """matricula -> {camara_id, nome_parlamentar, uf} a partir de ObterDeputados."""
    raiz = ET.fromstring(conteudo)
    mapa = {}
    for d in raiz.iter("deputado"):
        matricula = (d.findtext("matricula") or "").strip()
        ide = (d.findtext("ideCadastro") or "").strip()
        if matricula and ide.isdigit():
            mapa[matricula] = {
                "camara_id": int(ide),
                "nome_parlamentar": (d.findtext("nomeParlamentar") or "").strip(),
                "uf": (d.findtext("uf") or "").strip(),
            }
    return mapa


def dias_com_sessao_deliberativa(eventos: Iterable[dict]) -> List[date]:
    """Filtra eventos da API v2 (codTipoEvento=110) para dias de sessão no PLEN."""
    dias = set()
    for ev in eventos:
        siglas = {o.get("sigla") for o in ev.get("orgaos") or []}
        if "PLEN" not in siglas:
            continue
        if "Cancelad" in (ev.get("situacao") or ""):
            continue
        inicio = ev.get("dataHoraInicio") or ""
        try:
            dias.add(datetime.strptime(inicio[:10], "%Y-%m-%d").date())
        except ValueError:
            continue
    return sorted(dias)


# ---------------------------------------------------------------------------
# Senado
# ---------------------------------------------------------------------------

# Siglas de /plenario/lista/tiposComparecimento e valores vistos em /votacao.
_SENADO_VOTOU = {"SIM", "NAO", "ABSTENCAO", "VOTOU", "VO"}
_SENADO_PRESENTE_SEM_VOTO = {"P-NRV", "P-OD", "OB", "PR", "PS", "PRESIDENTE (ART. 51 RISF)", "PSF", "SF", "MER"}
_SENADO_MISSAO = {"MIS", "L1", "L4", "L6", "REP"}
_SENADO_SAUDE = {"LS", "L2", "LSP"}
_SENADO_JUSTIFICADA = {"AP", "AUS", "LP", "L3", "LPA", "LAF", "LA", "LAP", "LG", "LGA", "LN", "LC", "L5", "LEG", "GR", "NA", "L7"}
_SENADO_NAO_JUSTIFICADA = {"NCOM"}
# Fora de exercício / sem votação / ambíguo: não entram no indicador.
_SENADO_IGNORAR = {"AFO", "CAS", "DIS", "DJ", "EP", "EPR", "FAL", "IMP", "PER", "REN", "RET", "TER",
                   "NH", "SI", "VS", "LCS", "LL", "IL", "RR", "NR"}


def mapear_voto_senado(sigla: Optional[str]) -> Optional[str]:
    """Classifica um voto individual (siglaVotoParlamentar) do Senado.

    Retorna PARTICIPOU_VOTACAO, PRESENTE_SEM_VOTO, um tipo de ausência, ou None
    quando a sigla não deve compor o indicador (fora de exercício, ambígua, etc.).
    """
    s = normalizar(sigla)
    if not s:
        return None
    if s in _SENADO_VOTOU:
        return PARTICIPOU_VOTACAO
    if s in _SENADO_PRESENTE_SEM_VOTO or s.startswith("PRESIDENTE"):
        return PRESENTE_SEM_VOTO
    if s in _SENADO_MISSAO:
        return MISSAO_OFICIAL
    if s in _SENADO_SAUDE:
        return LICENCA_MEDICA
    if s in _SENADO_JUSTIFICADA:
        return AUSENCIA_JUSTIFICADA
    if s in _SENADO_NAO_JUSTIFICADA:
        return AUSENCIA_NAO_JUSTIFICADA
    return None


_PRIORIDADE_SESSAO = [PARTICIPOU_VOTACAO, PRESENTE_SEM_VOTO]


def agregar_votacoes_senado(votacoes: Iterable[dict]) -> Tuple[List[dict], Counter]:
    """Uma linha por (senador, sessão) com votação nominal.

    - Votou em ao menos uma votação nominal da sessão -> PARTICIPOU_VOTACAO.
    - Senão, registrado presente sem voto -> PRESENTE_SEM_VOTO.
    - Senão, o tipo de ausência mais frequente nas votações da sessão, com o
      texto oficial (descricaoVotoParlamentar) em ``justificativa``.
    Siglas fora do indicador são contadas em ``descartes``.
    """
    por_chave: Dict[Tuple[int, int], dict] = {}
    descartes: Counter = Counter()
    for v in votacoes:
        cod_sessao = v.get("codigoSessao")
        data_sessao = v.get("dataSessao")
        if cod_sessao is None or not data_sessao:
            continue
        for voto in v.get("votos") or []:
            cod = voto.get("codigoParlamentar")
            sigla = voto.get("siglaVotoParlamentar")
            status = mapear_voto_senado(sigla)
            if cod is None:
                continue
            if status is None:
                descartes[sigla or "<vazio>"] += 1
                continue
            item = por_chave.setdefault((int(cod), int(cod_sessao)), {
                "senado_id": int(cod),
                "nome_parlamentar": voto.get("nomeParlamentar"),
                "uf": voto.get("siglaUFParlamentar"),
                "data": data_sessao[:10],
                "codigo_sessao": int(cod_sessao),
                "status_por_votacao": Counter(),
                "descricoes": Counter(),
                "votacoes_nominais": 0,
            })
            item["votacoes_nominais"] += 1
            item["status_por_votacao"][status] += 1
            if status not in _PRIORIDADE_SESSAO:
                desc = voto.get("descricaoVotoParlamentar") or sigla
                item["descricoes"][f"{desc} ({sigla})"] += 1

    saida = []
    for item in por_chave.values():
        contagem: Counter = item.pop("status_por_votacao")
        descricoes: Counter = item.pop("descricoes")
        status = next((s for s in _PRIORIDADE_SESSAO if contagem.get(s)), None)
        justificativa = None
        if status is None:
            status = contagem.most_common(1)[0][0]
            justificativa = descricoes.most_common(1)[0][0] if descricoes else None
        item["status"] = status
        item["justificativa"] = justificativa
        item["votos_registrados"] = contagem.get(PARTICIPOU_VOTACAO, 0)
        saida.append(item)
    saida.sort(key=lambda r: (r["data"], r["senado_id"]))
    return saida, descartes


def lista(valor) -> list:
    """Os JSON 'XML-like' do Senado trocam lista de 1 item por objeto."""
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def parse_licencas_senado(payload: dict) -> List[dict]:
    parl = (payload.get("LicencaParlamentar") or {}).get("Parlamentar") or {}
    saida = []
    for lic in lista((parl.get("Licencas") or {}).get("Licenca")):
        saida.append({
            "senado_id": int(parl["Codigo"]) if str(parl.get("Codigo", "")).isdigit() else None,
            "data_inicio": lic.get("DataInicio"),
            "data_fim": lic.get("DataFim"),
            "sigla_tipo": lic.get("SiglaTipoAfastamento"),
            "descricao_tipo": lic.get("DescricaoTipoAfastamento"),
        })
    return saida


# ---------------------------------------------------------------------------
# Orquestração (rede)
# ---------------------------------------------------------------------------

class PresencaExtractor:
    def __init__(self, raw_dir: Path = RAW_DATA_DIR / "presenca", out_dir: Path = PROCESSED_DATA_DIR,
                 min_interval_s: float = 1.1):
        self.http = CachedHttpClient(raw_dir, min_interval_s=min_interval_s, timeout_s=120)
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    # Câmara ---------------------------------------------------------------
    def _eventos_deliberativos(self, inicio: date, fim: date) -> List[dict]:
        eventos: List[dict] = []
        pagina = 1
        while True:
            corpo = self.http.get_bytes(CAMARA_EVENTOS_URL, {
                "dataInicio": inicio.isoformat(), "dataFim": fim.isoformat(),
                "codTipoEvento": 110, "itens": 100, "pagina": pagina,
                "ordem": "ASC", "ordenarPor": "dataHoraInicio",
            }, accept="application/json", suffix=".json")
            dados = json.loads(corpo.decode("utf-8"))
            eventos.extend(dados.get("dados") or [])
            if not any(l.get("rel") == "next" for l in dados.get("links") or []):
                return eventos
            pagina += 1

    def extrair_camara(self, inicio: date, fim: date) -> dict:
        # A API v2 limita o intervalo de datas; consultamos mês a mês.
        eventos: List[dict] = []
        cursor = inicio
        while cursor <= fim:
            prox = (cursor.replace(day=1) + timedelta(days=32)).replace(day=1)
            eventos.extend(self._eventos_deliberativos(cursor, min(fim, prox - timedelta(days=1))))
            cursor = prox
        dias = dias_com_sessao_deliberativa(eventos)
        logger.info("Câmara: %d dias com sessão deliberativa no plenário", len(dias))

        mapa = parse_obter_deputados_xml(
            self.http.get_bytes(CAMARA_DEPUTADOS_WS_URL, accept="text/xml", suffix=".xml")
        )

        registros, descartados = [], Counter()
        for dia in dias:
            corpo = self.http.get_bytes(CAMARA_PRESENCAS_DIA_URL, {
                "data": dia.strftime("%d/%m/%Y"), "numMatriculaParlamentar": "",
                "siglaPartido": "", "siglaUF": "",
            }, accept="text/xml", suffix=".xml")
            _, parlamentares = parse_presencas_dia_xml(corpo)
            for p in parlamentares:
                status = mapear_status_camara(p["descricao_frequencia"], p["justificativa"])
                if status is None:
                    descartados[p["descricao_frequencia"] or "<vazio>"] += 1
                    continue
                ref = mapa.get(p["carteira"] or "")
                # Checagem de sanidade do vínculo carteira->matrícula: a UF precisa bater.
                camara_id = ref["camara_id"] if ref and ref["uf"] == p["uf"] else None
                registros.append({
                    "data": dia.isoformat(),
                    "carteira": p["carteira"],
                    "camara_id": camara_id,
                    "nome_parlamentar": p["nome_parlamentar"],
                    "uf": p["uf"],
                    "descricao_frequencia": p["descricao_frequencia"],
                    "justificativa": p["justificativa"],
                    "status": status,
                    "sessoes": p["sessoes"],
                })
        resultado = {
            "fonte": FONTE_CAMARA,
            "fonte_urls": [CAMARA_EVENTOS_URL, CAMARA_PRESENCAS_DIA_URL, CAMARA_DEPUTADOS_WS_URL],
            "metodologia": "PRESENCA_PLENARIO_CAMARA",
            "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
            "coletado_em": datetime.now().isoformat(timespec="seconds"),
            "dias_com_sessao": [d.isoformat() for d in dias],
            "descartados_por_rotulo": dict(descartados),
            "registros": registros,
        }
        self._salvar("presenca_camara.json", resultado)
        logger.info("Câmara: %d registros (%d sem camara_id pela matrícula); descartes %s",
                    len(registros), sum(1 for r in registros if r["camara_id"] is None), dict(descartados))
        return resultado

    # Senado ---------------------------------------------------------------
    def extrair_senado(self, inicio: date, fim: date, licencas: bool = False,
                       codigos_senadores: Optional[List[int]] = None) -> dict:
        votacoes: List[dict] = []
        cursor = inicio
        while cursor <= fim:  # endpoint aceita no máximo 1 ano por consulta
            fim_janela = min(fim, date(cursor.year, 12, 31))
            corpo = self.http.get_bytes(SENADO_VOTACAO_URL, {
                "dataInicio": cursor.isoformat(), "dataFim": fim_janela.isoformat(),
            }, accept="application/json", suffix=".json")
            votacoes.extend(json.loads(corpo.decode("utf-8")) or [])
            cursor = fim_janela + timedelta(days=1)
        registros, descartes = agregar_votacoes_senado(votacoes)

        lic: List[dict] = []
        if licencas:
            codigos = codigos_senadores or sorted({r["senado_id"] for r in registros})
            for cod in codigos:
                corpo = self.http.get_bytes(SENADO_LICENCAS_URL.format(codigo=cod),
                                            {"dataInicio": inicio.strftime("%Y%m%d")},
                                            accept="application/json", suffix=".json")
                lic.extend(parse_licencas_senado(json.loads(corpo.decode("utf-8"))))

        resultado = {
            "fonte": FONTE_SENADO,
            "fonte_urls": [SENADO_VOTACAO_URL, SENADO_LICENCAS_URL],
            "metodologia": "PARTICIPACAO_VOTACOES_NOMINAIS_SENADO",
            "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
            "coletado_em": datetime.now().isoformat(timespec="seconds"),
            "votacoes_nominais": len(votacoes),
            "siglas_descartadas": dict(descartes),
            "registros": registros,
            "licencas": lic,
        }
        self._salvar("presenca_senado.json", resultado)
        logger.info("Senado: %d votações, %d registros senador×sessão, %d licenças; descartes %s",
                    len(votacoes), len(registros), len(lic), dict(descartes))
        return resultado

    def _salvar(self, nome: str, conteudo: dict) -> None:
        with open(self.out_dir / nome, "w", encoding="utf-8") as f:
            json.dump(conteudo, f, ensure_ascii=False, indent=1)


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(
        description="Extrai presença (Câmara) e participação em votações nominais (Senado)."
    )
    ap.add_argument("--inicio", required=True, type=date.fromisoformat)
    ap.add_argument("--fim", required=True, type=date.fromisoformat)
    ap.add_argument("--somente", choices=["camara", "senado"])
    ap.add_argument("--licencas", action="store_true", help="Também baixa licenças (1 req por senador)")
    ap.add_argument("--senadores", type=lambda s: [int(x) for x in s.split(",")],
                    help="Restringe as licenças a estes códigos (separados por vírgula)")
    ap.add_argument("--saida", type=Path, default=PROCESSED_DATA_DIR)
    ap.add_argument("--cache", type=Path, default=RAW_DATA_DIR / "presenca")
    args = ap.parse_args(argv)

    ext = PresencaExtractor(raw_dir=args.cache, out_dir=args.saida)
    if args.somente in (None, "camara"):
        ext.extrair_camara(args.inicio, args.fim)
    if args.somente in (None, "senado"):
        ext.extrair_senado(args.inicio, args.fim, licencas=args.licencas, codigos_senadores=args.senadores)
    logger.info("Requisições HTTP feitas nesta execução: %d", ext.http.requests_made)


if __name__ == "__main__":
    main()
