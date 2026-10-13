"""
Extrator de Dados Abertos do Senado Federal
Documentação oficial: https://legis.senado.leg.br/dadosabertos/
"""

import json
import logging
from typing import Any, Dict, List, Optional

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.extractors.camara_extractor import classificar_setor_por_texto
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json, write_json_if_valid

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SenadoExtractor")

BASE_SENADO_URL = "https://legis.senado.leg.br/dadosabertos"
FONTE_AUTORIA_SENADO = "API Dados Abertos do Senado (pesquisa de matérias)"

# Matérias estruturantes pesquisadas por (sigla, número, ano).
MATERIAS_BUSCA = [
    {"sigla": "PLP", "numero": 93, "ano": 2023, "titulo": "Novo Arcabouço Fiscal", "reforma": True},
    {"sigla": "PEC", "numero": 45, "ano": 2019, "titulo": "Reforma Tributária do Consumo", "reforma": True},
]


def _como_lista(valor: Any) -> List[Any]:
    """A API devolve objeto único ou lista; normaliza para lista."""
    if not valor:
        return []
    return valor if isinstance(valor, list) else [valor]


def classificar_voto_senado(sigla_voto: Optional[str]) -> str:
    """
    Mapeia SiglaVoto do Senado para VotoOpcaoEnum.
    Antes, qualquer valor diferente de Sim/Não (ausência, licença, P-NRV) virava ABSTENCAO,
    o que inflava abstenções com parlamentares que nem votaram.
    """
    raw = (sigla_voto or "").strip().upper()
    if raw in ("SIM", "S"):
        return "SIM"
    if raw in ("NÃO", "NAO", "N"):
        return "NAO"
    if raw.startswith("ABST"):
        return "ABSTENCAO"
    if raw.startswith("OBS"):
        return "OBSTRUCAO"
    # P-NRV, NCom, licenças, Presidente (art. 51) etc.: não houve voto registrado.
    return "AUSENTE"


def interpretar_resultado(descricao_resultado: Optional[str]) -> Optional[bool]:
    """Aprovada/rejeitada apenas quando o resultado oficial diz; caso contrário indeterminado (None)."""
    texto = (descricao_resultado or "").lower()
    if not texto:
        return None
    if "rejeit" in texto or "prejudic" in texto:
        return False
    if "aprovad" in texto:
        return True
    return None


def formatar_telefone_senado(identificacao: Dict[str, Any]) -> Optional[str]:
    """Primeiro telefone informado pela API (8 dígitos do ramal do Senado, DDD 61); None se ausente."""
    telefones = _como_lista((identificacao.get("Telefones") or {}).get("Telefone"))
    for tel in telefones:
        digitos = "".join(ch for ch in str(tel.get("NumeroTelefone") or "") if ch.isdigit())
        if len(digitos) == 8:
            return f"(61) {digitos[:4]}-{digitos[4:]}"
    return None


def extrair_mandato(parlamentar: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrai início/fim do mandato e legislaturas quando a API informa (`Mandato`/`MandatoAtual`).
    Campos ausentes retornam None — o loader decide o que fazer, sem inventar datas aqui.
    """
    mandato = parlamentar.get("Mandato") or parlamentar.get("MandatoAtual") or {}
    primeira = mandato.get("PrimeiraLegislaturaDoMandato") or {}
    segunda = mandato.get("SegundaLegislaturaDoMandato") or {}
    return {
        "mandato_inicio": primeira.get("DataInicio"),
        "mandato_fim": segunda.get("DataFim") or primeira.get("DataFim"),
        "legislatura_inicio": primeira.get("NumeroLegislatura"),
        "legislatura_fim": segunda.get("NumeroLegislatura") or primeira.get("NumeroLegislatura"),
        "condicao_mandato": mandato.get("DescricaoParticipacao"),
    }


class SenadoExtractor:
    """Consome a API de Dados Abertos do Senado Federal (Senadores em exercício e Votações Nominais)."""

    def __init__(self, raw_cache_dir=RAW_DATA_DIR, request_delay: float = 0.25, http: Optional[HttpClient] = None):
        self.raw_dir = raw_cache_dir
        self.delay = request_delay
        self.http = http or HttpClient(timeout=25.0, max_retries=3, min_interval=request_delay)

    def _get_json(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            return self.http.get_json(url)
        except HttpError as exc:
            logger.error("Falha ao consultar o Senado: %s", exc)
            return None

    def fetch_senadores_em_exercicio(self) -> List[Dict[str, Any]]:
        """Extrai os senadores em exercício. Lista vazia significa FALHA (quem chama não deve gravar)."""
        logger.info("Extraindo lista de Senadores em exercício no Senado Federal...")
        data = self._get_json(f"{BASE_SENADO_URL}/senador/lista/atual.json")

        try:
            senadores_raw = _como_lista(data["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"])
        except (TypeError, KeyError):
            logger.error("Resposta inesperada ao obter a lista de senadores do Senado Federal.")
            return []

        senadores: Dict[int, Dict[str, Any]] = {}
        for p in senadores_raw:
            ident = p.get("IdentificacaoParlamentar", {})
            codigo = ident.get("CodigoParlamentar")
            if not codigo:
                continue
            sid = int(codigo)
            foto_url = f"https://legis.senado.leg.br/senadores/fotos-oficiais/{sid}" if sid else ident.get("UrlFotoParlamentar")
            registro = {
                "senado_id": sid,
                "nome_civil": ident.get("NomeCompletoParlamentar") or ident.get("NomeParlamentar"),
                "nome_eleitoral": ident.get("NomeParlamentar"),
                "partido_sigla": ident.get("SiglaPartidoParlamentar") or "S.PART.",
                "uf": ident.get("UfParlamentar"),
                "foto_url": foto_url,
                "email": ident.get("EmailParlamentar"),
                "gabinete_telefone": formatar_telefone_senado(ident),
                "cargo": "SENADOR",
            }
            registro.update(extrair_mandato(p))
            senadores[sid] = registro

        logger.info(f"Total de {len(senadores)} senadores em exercício extraídos com sucesso.")
        return list(senadores.values())

    def fetch_votacoes_materias_estruturantes(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extrai as votações nominais no Senado de matérias estruturantes (PLP 93/2023, PEC 45/2019)."""
        logger.info("Extraindo votações nominais de matérias estruturantes no Senado Federal...")

        sessoes_senado: List[Dict[str, Any]] = []
        votos_senado: List[Dict[str, Any]] = []

        for mat in MATERIAS_BUSCA:
            url_pesquisa = f"{BASE_SENADO_URL}/materia/pesquisa/lista.json?sigla={mat['sigla']}&numero={mat['numero']}&ano={mat['ano']}"
            d_pesq = self._get_json(url_pesquisa)
            if not d_pesq or "PesquisaBasicaMateria" not in d_pesq:
                continue

            materias_obj = _como_lista(d_pesq["PesquisaBasicaMateria"].get("Materias", {}).get("Materia"))
            if not materias_obj:
                continue

            cod_materia = materias_obj[0]["Codigo"]
            d_vot = self._get_json(f"{BASE_SENADO_URL}/materia/votacoes/{cod_materia}.json")
            if not d_vot or "VotacaoMateria" not in d_vot:
                continue

            votacoes_lista = _como_lista(d_vot["VotacaoMateria"].get("Materia", {}).get("Votacoes", {}).get("Votacao"))

            for idx, vot in enumerate(votacoes_lista):
                cod_vot_raw = vot.get("CodigoSessaoVotacao") or vot.get("CodigoSessao") or f"{cod_materia}-{idx + 1}"
                cod_sessao = f"SEN-{cod_vot_raw}"
                sess_plen = vot.get("SessaoPlenaria", {})
                dt_vot = sess_plen.get("DataSessao") or vot.get("DataSessao")
                if not dt_vot:
                    logger.warning("Votação %s sem data na API — sessão ignorada (data não é presumida).", cod_sessao)
                    continue
                hr_vot = sess_plen.get("HoraInicioSessao") or "00:00:00"
                descricao = vot.get("DescricaoVotacao") or f"Votação nominal no Senado de {mat['titulo']}"

                votos_container = vot.get("Votos", {})
                parlamentares_votos = _como_lista(
                    votos_container.get("VotoParlamentar") or votos_container.get("Parlamentar")
                )
                if not parlamentares_votos:
                    continue

                totais = {"SIM": 0, "NAO": 0, "ABSTENCAO": 0, "OBSTRUCAO": 0, "AUSENTE": 0}
                for pv in parlamentares_votos:
                    ident = pv.get("IdentificacaoParlamentar", {})
                    cod_raw = ident.get("CodigoParlamentar")
                    if not cod_raw:
                        continue
                    opcao = classificar_voto_senado(pv.get("SiglaVoto"))
                    totais[opcao] += 1
                    votos_senado.append(
                        {
                            "sessao_externa_id": cod_sessao,
                            "materia_sigla": mat["sigla"],
                            "materia_numero": mat["numero"],
                            "materia_ano": mat["ano"],
                            "materia_titulo": mat["titulo"],
                            "senador_id": int(cod_raw),
                            "senador_nome": ident.get("NomeParlamentar"),
                            "partido_sigla": ident.get("SiglaPartidoParlamentar") or "S.PART.",
                            "uf": ident.get("UfParlamentar"),
                            "voto": opcao,
                        }
                    )

                resultado = vot.get("DescricaoResultado")
                sessoes_senado.append(
                    {
                        "sessao_externa_id": cod_sessao,
                        "materia_sigla": mat["sigla"],
                        "materia_numero": mat["numero"],
                        "materia_ano": mat["ano"],
                        "materia_titulo": mat["titulo"],
                        "data_hora": f"{dt_vot}T{hr_vot}",
                        "titulo_pauta": f"Senado Federal: Votação de {mat['titulo']}",
                        "descricao": descricao,
                        "resultado": resultado,
                        "aprovada": interpretar_resultado(resultado),
                        "total_sim": totais["SIM"],
                        "total_nao": totais["NAO"],
                        "total_abstencao": totais["ABSTENCAO"],
                        "total_obstrucao": totais["OBSTRUCAO"],
                        "total_votos": len(parlamentares_votos),
                    }
                )
                logger.info(
                    f"Sessão nominal no Senado {cod_sessao}: {len(parlamentares_votos)} registros ({totais['SIM']} Sim, {totais['NAO']} Não)."
                )

        return {"sessoes": sessoes_senado, "votos": votos_senado}

    def fetch_proposicoes_senado(self) -> List[Dict[str, Any]]:
        """Extrai proposições do Senado (1995-presente). Devolve LISTA, como o loader e a anotação esperam."""
        logger.info("Iniciando extração histórica de proposições do Senado Federal (1995 a 2026)...")
        proposicoes_senado: Dict[int, Dict[str, Any]] = {}
        siglas = ["PL", "PEC", "PLP"]

        checkpoint_senado_file = self.raw_dir / "checkpoint_senado_proposicoes.json"
        if checkpoint_senado_file.exists():
            try:
                with open(checkpoint_senado_file, "r", encoding="utf-8") as f:
                    cached_props = json.load(f)
                for cp in cached_props:
                    proposicoes_senado[cp["senado_id"]] = cp
                logger.info(f"Checkpoint do Senado restaurado: {len(cached_props)} proposições carregadas do disco.")
            except (OSError, ValueError, KeyError) as ex:
                logger.warning(f"Checkpoint do Senado ilegível, ignorando: {ex}")

        eras_senado = [
            ("Lula III (2023-2026)", [2023, 2024, 2025, 2026], 100),
            ("Jair Bolsonaro (2019-2022)", [2022, 2021, 2020, 2019], 30),
            ("Dilma / Temer (2011-2018)", [2018, 2016, 2015, 2014, 2012, 2011], 20),
            ("Lula I e II (2003-2010)", [2010, 2008, 2006, 2004, 2003], 20),
            ("Fernando Henrique Cardoso - FHC (1995-2002)", [2002, 2000, 1998, 1996, 1995], 20),
        ]

        for era_nome, anos_era, max_itens in eras_senado:
            logger.info(f"[Senado Histórico] Extraindo ciclo: {era_nome}...")
            for sigla in siglas:
                for ano in anos_era:
                    data = self._get_json(f"{BASE_SENADO_URL}/materia/pesquisa/lista.json?sigla={sigla}&ano={ano}")
                    if not data or "PesquisaBasicaMateria" not in data:
                        continue

                    materias = _como_lista(data["PesquisaBasicaMateria"].get("Materias", {}).get("Materia"))
                    for m in materias[:max_itens]:
                        cod = m.get("Codigo")
                        if not cod:
                            continue
                        cod_int = int(cod)
                        if cod_int in proposicoes_senado:
                            continue

                        ementa = m.get("Ementa") or ""
                        titulo = m.get("DescricaoIdentificacao") or f"{sigla} {m.get('Numero')}/{ano}"
                        setor = classificar_setor_por_texto(titulo, ementa, tema_padrao="Administração & Justiça")

                        try:
                            num_int = int(m.get("Numero") or 0)
                        except (ValueError, TypeError):
                            num_int = 0
                        try:
                            ano_int = int(m.get("Ano") or ano)
                        except (ValueError, TypeError):
                            ano_int = ano

                        url_oficial = (
                            m.get("UrlDetalheMateria")
                            or f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{cod_int}"
                        )
                        proposicoes_senado[cod_int] = {
                            "senado_id": cod_int,
                            "tipo": m.get("Sigla") or sigla,
                            "numero": num_int,
                            "ano": ano_int,
                            "titulo": titulo,
                            "ementa": ementa,
                            "area_tematica": setor,
                            "data_apresentacao": m.get("Data"),
                            "autor_nome": m.get("Autor") or None,
                            "autor_fonte": FONTE_AUTORIA_SENADO if m.get("Autor") else None,
                            "url_detalhe": url_oficial,
                            "url_oficial": url_oficial,
                        }

                    try:
                        atomic_write_json(checkpoint_senado_file, list(proposicoes_senado.values()), indent=None)
                    except OSError as ex:
                        logger.warning("Não foi possível gravar checkpoint do Senado: %s", ex)

        lista = list(proposicoes_senado.values())
        logger.info(f"Total de {len(lista)} proposições extraídas do Senado Federal.")
        return lista

    def run_full_extraction(self) -> Dict[str, Any]:
        """Executa extração completa; falhas (listas vazias) preservam os arquivos anteriores."""
        logger.info("=" * 70)
        logger.info("INICIANDO EXTRAÇÃO DE DADOS ABERTOS DO SENADO FEDERAL")
        logger.info("=" * 70)

        senadores = self.fetch_senadores_em_exercicio()
        write_json_if_valid(PROCESSED_DATA_DIR / "senadores_senado.json", senadores)

        resultado_vot = self.fetch_votacoes_materias_estruturantes()
        sessoes = resultado_vot["sessoes"]
        votos = resultado_vot["votos"]
        write_json_if_valid(PROCESSED_DATA_DIR / "sessoes_votacao_senado.json", sessoes)
        write_json_if_valid(PROCESSED_DATA_DIR / "votos_nominais_senado.json", votos)

        proposicoes_senado = self.fetch_proposicoes_senado()
        write_json_if_valid(PROCESSED_DATA_DIR / "proposicoes_senado.json", proposicoes_senado)

        logger.info("Dados do Senado Federal processados em etl/data/processed/!")
        return {
            "total_senadores": len(senadores),
            "total_sessoes_senado": len(sessoes),
            "total_votos_senado": len(votos),
            "total_proposicoes_senado": len(proposicoes_senado),
        }


if __name__ == "__main__":
    extractor = SenadoExtractor()
    res = extractor.run_full_extraction()
    print("Resultado da extração:", res)
