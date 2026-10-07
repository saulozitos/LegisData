"""
Extrator de Dados Abertos do Senado Federal
Documentação oficial: https://legis.senado.leg.br/dadosabertos/
"""

import time
import json
import logging
from typing import List, Dict, Any, Optional
import urllib.request
import urllib.error

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SenadoExtractor")

BASE_SENADO_URL = "https://legis.senado.leg.br/dadosabertos"


class SenadoExtractor:
    """Consome a API de Dados Abertos do Senado Federal (Senadores em exercício e Votações Nominais)."""

    def __init__(self, raw_cache_dir=RAW_DATA_DIR, request_delay: float = 0.25):
        self.raw_dir = raw_cache_dir
        self.delay = request_delay
        self.headers = {
            "User-Agent": "LegisDataBot/1.0 (Transparência Pública; contato@legisdata.org)",
            "Accept": "application/json"
        }

    def _get_json(self, url: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """Faz requisição HTTP GET com headers amigáveis e tratamento de retentativas."""
        for attempt in range(max_retries):
            try:
                time.sleep(self.delay)
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=25) as resp:
                    if resp.status == 200:
                        return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as he:
                if he.code == 429:
                    wait_time = (2 ** attempt) * 1.5
                    logger.warning(f"Rate limit atingido no Senado (429). Aguardando {wait_time:.1f}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Erro HTTP {he.code} em {url}: {he.reason}")
                    return None
            except Exception as ex:
                logger.error(f"Erro na requisição ao Senado {url}: {ex}")
                time.sleep(1.0)
        return None

    def fetch_senadores_em_exercicio(self) -> List[Dict[str, Any]]:
        """Extrai os 81 senadores federais em exercício no Brasil."""
        logger.info("Extraindo lista de Senadores em exercício no Senado Federal...")
        url = f"{BASE_SENADO_URL}/senador/lista/atual.json"
        data = self._get_json(url)

        if not data or "ListaParlamentarEmExercicio" not in data:
            logger.error("Falha ao obter lista de senadores do Senado Federal.")
            return []

        senadores_raw = data["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
        senadores = []

        for p in senadores_raw:
            ident = p.get("IdentificacaoParlamentar", {})
            senadores.append({
                "senado_id": int(ident.get("CodigoParlamentar")),
                "nome_civil": ident.get("NomeCompletoParlamentar") or ident.get("NomeParlamentar"),
                "nome_eleitoral": ident.get("NomeParlamentar"),
                "partido_sigla": ident.get("SiglaPartidoParlamentar") or "S.PART.",
                "uf": ident.get("UfParlamentar"),
                "foto_url": ident.get("UrlFotoParlamentar"),
                "email": ident.get("EmailParlamentar"),
                "cargo": "SENADOR"
            })

        logger.info(f"Total de {len(senadores)} senadores em exercício extraídos com sucesso.")
        return senadores

    def fetch_votacoes_materias_estruturantes(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extrai as votações nominais no Senado de grandes matérias estruturantes de 2023:
        1. PLP 93/2023 - Novo Arcabouço Fiscal (Código no Senado: 157309 ou via busca)
        2. PEC 45/2019 - Reforma Tributária sobre o Consumo
        """
        logger.info("Extraindo votações nominais de matérias estruturantes no Senado Federal...")

        materias_busca = [
            {"sigla": "PLP", "numero": 93, "ano": 2023, "titulo": "Novo Arcabouço Fiscal", "reforma": True},
            {"sigla": "PEC", "numero": 45, "ano": 2019, "titulo": "Reforma Tributária do Consumo", "reforma": True}
        ]

        sessoes_senado = []
        votos_senado = []

        for mat in materias_busca:
            url_pesquisa = f"{BASE_SENADO_URL}/materia/pesquisa/lista.json?sigla={mat['sigla']}&numero={mat['numero']}&ano={mat['ano']}"
            d_pesq = self._get_json(url_pesquisa)

            if not d_pesq or "PesquisaBasicaMateria" not in d_pesq:
                continue

            materias_obj = d_pesq["PesquisaBasicaMateria"].get("Materias", {}).get("Materia")
            if not materias_obj:
                continue

            materia_selecionada = materias_obj[0] if isinstance(materias_obj, list) else materias_obj
            cod_materia = materia_selecionada["Codigo"]

            # Buscar votações nominais da matéria
            url_votacoes = f"{BASE_SENADO_URL}/materia/votacoes/{cod_materia}.json"
            d_vot = self._get_json(url_votacoes)

            if not d_vot or "VotacaoMateria" not in d_vot:
                continue

            votacoes_lista = d_vot["VotacaoMateria"].get("Materia", {}).get("Votacoes", {}).get("Votacao", [])
            if not isinstance(votacoes_lista, list):
                votacoes_lista = [votacoes_lista] if votacoes_lista else []

            for idx, vot in enumerate(votacoes_lista):
                cod_vot_raw = vot.get("CodigoSessaoVotacao") or vot.get("CodigoSessao") or f"{cod_materia}-{idx+1}"
                cod_sessao = f"SEN-{cod_vot_raw}"
                sess_plen = vot.get("SessaoPlenaria", {})
                dt_vot = sess_plen.get("DataSessao") or vot.get("DataSessao") or "2023-08-22"
                hr_vot = sess_plen.get("HoraInicioSessao") or "16:00:00"
                descricao = vot.get("DescricaoVotacao") or f"Votação nominal no Senado de {mat['titulo']}"

                # Extrair votos parlamentares (chave pode ser VotoParlamentar ou Parlamentar)
                votos_container = vot.get("Votos", {})
                parlamentares_votos = (
                    votos_container.get("VotoParlamentar") or
                    votos_container.get("Parlamentar") or
                    []
                )
                if not isinstance(parlamentares_votos, list):
                    parlamentares_votos = [parlamentares_votos] if parlamentares_votos else []

                if not parlamentares_votos:
                    continue

                total_sim = 0
                total_nao = 0
                total_abst = 0

                for pv in parlamentares_votos:
                    ident = pv.get("IdentificacaoParlamentar", {})
                    cod_senador = int(ident.get("CodigoParlamentar", 0))
                    voto_raw = (pv.get("SiglaVoto") or "").strip().upper()

                    if voto_raw in ("SIM", "S"):
                        opcao = "SIM"
                        total_sim += 1
                    elif voto_raw in ("NÃO", "NAO", "N"):
                        opcao = "NAO"
                        total_nao += 1
                    else:
                        opcao = "ABSTENCAO"
                        total_abst += 1

                    votos_senado.append({
                        "sessao_externa_id": cod_sessao,
                        "materia_sigla": mat["sigla"],
                        "materia_numero": mat["numero"],
                        "materia_titulo": mat["titulo"],
                        "senador_id": cod_senador,
                        "senador_nome": ident.get("NomeParlamentar"),
                        "partido_sigla": ident.get("SiglaPartidoParlamentar") or "S.PART.",
                        "uf": ident.get("UfParlamentar"),
                        "voto": opcao
                    })

                sessoes_senado.append({
                    "sessao_externa_id": cod_sessao,
                    "materia_sigla": mat["sigla"],
                    "materia_numero": mat["numero"],
                    "materia_titulo": mat["titulo"],
                    "data_hora": f"{dt_vot}T{hr_vot}",
                    "titulo_pauta": f"Senado Federal: Votação de {mat['titulo']}",
                    "descricao": descricao,
                    "resultado": vot.get("DescricaoResultado", "Aprovado"),
                    "aprovada": "aprovad" in str(vot.get("DescricaoResultado", "")).lower() or total_sim > total_nao,
                    "total_sim": total_sim,
                    "total_nao": total_nao,
                    "total_abstencao": total_abst,
                    "total_votos": len(parlamentares_votos)
                })

                logger.info(f"Sessão nominal no Senado {cod_sessao} coletada: {len(parlamentares_votos)} senadores votaram ({total_sim} Sim, {total_nao} Não).")

        return {
            "sessoes": sessoes_senado,
            "votos": votos_senado
        }

    def fetch_proposicoes_senado(self) -> List[Dict[str, Any]]:
        """Extrai proposições legislativas do Senado Federal com cobertura histórica pós-1995 (FHC ao presente)."""
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
            except Exception as ex:
                logger.warning(f"Aviso ao ler checkpoint do Senado: {ex}")

        eras_senado = [
            ("Lula III (2023-2026)", [2023, 2024, 2025, 2026], 100),
            ("Jair Bolsonaro (2019-2022)", [2022, 2021, 2020, 2019], 30),
            ("Dilma / Temer (2011-2018)", [2018, 2016, 2015, 2014, 2012, 2011], 20),
            ("Lula I e II (2003-2010)", [2010, 2008, 2006, 2004, 2003], 20),
            ("Fernando Henrique Cardoso - FHC (1995-2002)", [2002, 2000, 1998, 1996, 1995], 20),
        ]

        for era_nome, anos_era, max_itens in eras_senado:
            logger.info(f"[Senado Histórico Pós-1995] Extraindo ciclo: {era_nome} (anos {min(anos_era)} a {max(anos_era)})...")
            for sigla in siglas:
                for ano in anos_era:
                    url = f"{BASE_SENADO_URL}/materia/pesquisa/lista.json?sigla={sigla}&ano={ano}"
                    data = self._get_json(url)
                    if not data or "PesquisaBasicaMateria" not in data:
                        continue

                    materias = data["PesquisaBasicaMateria"].get("Materias", {}).get("Materia", [])
                    if not isinstance(materias, list):
                        materias = [materias] if materias else []

                    for m in materias[:max_itens]:
                        cod = m.get("Codigo")
                        if not cod:
                            continue
                        cod_int = int(cod)
                        if cod_int in proposicoes_senado:
                            continue

                        autor_raw = m.get("Autor") or ""
                        ementa = m.get("Ementa") or ""
                        titulo = m.get("DescricaoIdentificacao") or f"{sigla} {m.get('Numero')}/{ano}"

                        # Classificar setor
                        t = f"{titulo} {ementa}".lower()
                        if any(k in t for k in ["homenagem", "comemorativ", "dia nacional", "patrono"]):
                            setor = "Homenagens & Datas Comemorativas"
                        elif any(k in t for k in ["saúde", "sus", "hospital", "médic", "medicamento", "enferm", "vacina"]):
                            setor = "Saúde"
                        elif any(k in t for k in ["escola", "educa", "ensino", "professor", "estudante", "universidade"]):
                            setor = "Educação"
                        elif any(k in t for k in ["segurança", "polícia", "crime", "penal", "porte de arma", "tráfico", "pena"]):
                            setor = "Segurança Pública"
                        elif any(k in t for k in ["imposto", "tribut", "fiscal", "orçamento", "banco", "crédito", "reforma tributária"]):
                            setor = "Economia & Finanças"
                        elif any(k in t for k in ["trabalho", "clt", "salário", "emprego", "previdência", "inss"]):
                            setor = "Trabalho & Previdência"
                        elif any(k in t for k in ["meio ambiente", "clima", "floresta", "carbono", "desmatamento", "fauna"]):
                            setor = "Meio Ambiente & Clima"
                        elif any(k in t for k in ["indígena", "mulher", "direitos humanos", "discrimina", "racial", "lgbt"]):
                            setor = "Direitos Humanos & Minorias"
                        elif any(k in t for k in ["internet", "tecnologia", "inteligência artificial", "software", "digital"]):
                            setor = "Tecnologia & Inovação"
                        elif any(k in t for k in ["rodovia", "transporte", "trânsito", "ferrovia", "porto", "obras"]):
                            setor = "Infraestrutura & Cidades"
                        elif any(k in t for k in ["agricultura", "pecuária", "safra", "agro", "rural", "pesca"]):
                            setor = "Agricultura & Agropecuária"
                        else:
                            setor = "Administração & Justiça"

                        try:
                            num_int = int(m.get("Numero") or 0)
                        except (ValueError, TypeError):
                            num_int = 0

                        try:
                            ano_int = int(m.get("Ano") or ano)
                        except (ValueError, TypeError):
                            ano_int = ano

                        url_oficial = m.get("UrlDetalheMateria") or f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{cod_int}"

                        proposicoes_senado[cod_int] = {
                            "senado_id": cod_int,
                            "tipo": m.get("Sigla") or sigla,
                            "numero": num_int,
                            "ano": ano_int,
                            "titulo": titulo,
                            "ementa": ementa,
                            "area_tematica": setor,
                            "data_apresentacao": m.get("Data"),
                            "autor_nome": autor_raw,
                            "url_detalhe": url_oficial,
                            "url_oficial": url_oficial
                        }

                    # Salvar checkpoint seguro
                    try:
                        with open(checkpoint_senado_file, "w", encoding="utf-8") as f:
                            json.dump(list(proposicoes_senado.values()), f, ensure_ascii=False)
                    except Exception:
                        pass

        logger.info(f"Total de {len(proposicoes_senado)} proposições extraídas do Senado Federal.")
        return proposicoes_senado

    def run_full_extraction(self) -> Dict[str, Any]:
        """Executa extração completa e persiste arquivos JSON."""
        logger.info("=" * 70)
        logger.info("INICIANDO EXTRAÇÃO DE DADOS ABERTOS DO SENADO FEDERAL")
        logger.info("=" * 70)

        senadores = self.fetch_senadores_em_exercicio()
        sen_file = PROCESSED_DATA_DIR / "senadores_senado.json"
        with open(sen_file, "w", encoding="utf-8") as f:
            json.dump(senadores, f, ensure_ascii=False, indent=2)

        resultado_vot = self.fetch_votacoes_materias_estruturantes()
        sessoes = resultado_vot["sessoes"]
        votos = resultado_vot["votos"]

        sess_file = PROCESSED_DATA_DIR / "sessoes_votacao_senado.json"
        with open(sess_file, "w", encoding="utf-8") as f:
            json.dump(sessoes, f, ensure_ascii=False, indent=2)

        votos_file = PROCESSED_DATA_DIR / "votos_nominais_senado.json"
        with open(votos_file, "w", encoding="utf-8") as f:
            json.dump(votos, f, ensure_ascii=False, indent=2)

        proposicoes_senado = self.fetch_proposicoes_senado()
        prop_sen_file = PROCESSED_DATA_DIR / "proposicoes_senado.json"
        with open(prop_sen_file, "w", encoding="utf-8") as f:
            json.dump(proposicoes_senado, f, ensure_ascii=False, indent=2)

        logger.info("Dados do Senado Federal salvos em etl/data/processed/!")
        return {
            "total_senadores": len(senadores),
            "total_sessoes_senado": len(sessoes),
            "total_votos_senado": len(votos),
            "total_proposicoes_senado": len(proposicoes_senado)
        }


if __name__ == "__main__":
    extractor = SenadoExtractor()
    res = extractor.run_full_extraction()
    print("Resultado da extração:", res)
