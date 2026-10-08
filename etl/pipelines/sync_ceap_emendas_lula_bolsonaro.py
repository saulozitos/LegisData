"""
Pipeline de Extração e Consolidação Histórica de CEAP e Emendas (Lula 1 até Bolsonaro / Presente)
Abrange desde a instituição dos dados abertos da Cota Parlamentar (2008). Emendas não são geradas aqui.
"""

import re
import os
import io
import gc
import json
import time
import zipfile
import logging
import http.client
import urllib.request
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SyncLulaBolsonaro")

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _mascarar_cpf(doc):
    """Mascara CPF de pessoa física (11 dígitos) no padrão do TSE; mantém CNPJ.

    Fornecedores pessoa física não são agentes públicos: republicar o CPF completo
    não é necessário para a finalidade de transparência (LGPD, art. 6º, III).
    """
    if doc is None:
        return None
    d = "".join(ch for ch in str(doc) if ch.isdigit())
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    return str(doc)

_CPF_EM_TEXTO = re.compile(r"(?<!\d)(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?!\d)")


def _mascarar_cpf_no_nome(nome):
    """MEI costuma vir como 'NOME SOBRENOME 12345678901': mascara o CPF embutido no nome."""
    if not nome:
        return nome
    return _CPF_EM_TEXTO.sub(lambda m: f"***.{m.group(2)}.{m.group(3)}-**", str(nome))


def extract_senado_ceaps_year(ano: int) -> List[Dict[str, Any]]:
    """Extrai despesas da CEAPS do Senado para um ano específico."""
    url = f"https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = resp.read()
            break
        except http.client.IncompleteRead as e:
            data = e.partial
            logger.info(f"   [Senado {ano}] IncompleteRead capturado ({len(data):,} bytes)")
            break
        except Exception as e:
            if attempt < 3:
                time.sleep(1.5 * attempt)
            else:
                logger.warning(f"   [Senado {ano}] Falha após 3 tentativas: {e}")
                return []
    try:
        j = json.loads(data)
        if isinstance(j, list):
            return j
        return j.get("despesas", [])
    except Exception as e:
        logger.warning(f"   [Senado {ano}] Erro ao parsear JSON: {e}")
        return []


def process_camara_ceap_year(ano: int, ceap_resumo: Dict[str, Any]) -> int:
    """Baixa e agrega o CSV anual da Câmara diretamente no dicionário consolidado."""
    url = f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    
    usecols = [
        "txNomeParlamentar", "sgUF", "txtDescricao", "txtFornecedor",
        "txtCNPJCPF", "vlrLiquido", "numAno", "numMes"
    ]
    
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                content = resp.read()
            break
        except Exception as e:
            if attempt < 3:
                time.sleep(2 * attempt)
            else:
                logger.warning(f"   [Câmara {ano}] Falha no download: {e}")
                return 0

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                df = pd.read_csv(
                    f, sep=";", encoding="utf-8-sig", low_memory=False, usecols=usecols
                )
    except Exception as e:
        logger.warning(f"   [Câmara {ano}] Erro ao descompactar CSV: {e}")
        return 0

    df["vlrLiquido"] = pd.to_numeric(df["vlrLiquido"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
    df["txNomeParlamentar"] = df["txNomeParlamentar"].astype(str).str.upper().str.strip()
    df = df[df["vlrLiquido"] > 0]
    
    records_count = len(df)
    
    # Agregação anual por deputado
    for name, group in df.groupby("txNomeParlamentar"):
        if not name or name == "NAN":
            continue
        
        tot_ano = float(group["vlrLiquido"].sum())
        notas_ano = len(group)
        
        if name not in ceap_resumo:
            ceap_resumo[name] = {
                "nome": name,
                "cargo": "DEPUTADO_FEDERAL",
                "total_gasto": 0.0,
                "total_notas": 0,
                "por_ano": {},
                "por_tipo": {},
                "fornecedores": {}
            }
            
        p = ceap_resumo[name]
        p["total_gasto"] += tot_ano
        p["total_notas"] += notas_ano
        p["por_ano"][str(ano)] = round(p["por_ano"].get(str(ano), 0.0) + tot_ano, 2)
        
        # Agregação por tipo
        for tipo, sum_val in group.groupby("txtDescricao")["vlrLiquido"].sum().items():
            tipo_str = str(tipo).strip()
            p["por_tipo"][tipo_str] = round(p["por_tipo"].get(tipo_str, 0.0) + float(sum_val), 2)
            
        # Top fornecedores
        for forn, subg in group.groupby("txtFornecedor"):
            forn_str = _mascarar_cpf_no_nome(str(forn).strip())
            tot_f = float(subg["vlrLiquido"].sum())
            cnt_f = len(subg)
            cnpj_f = str(subg["txtCNPJCPF"].iloc[0]) if "txtCNPJCPF" in subg and pd.notna(subg["txtCNPJCPF"].iloc[0]) else None
            
            if forn_str not in p["fornecedores"]:
                p["fornecedores"][forn_str] = {"nome": forn_str, "cnpj_cpf": _mascarar_cpf(cnpj_f), "total": 0.0, "notas": 0}
            p["fornecedores"][forn_str]["total"] += tot_f
            p["fornecedores"][forn_str]["notas"] += cnt_f

    del df
    gc.collect()
    return records_count


def main():
    start_time = time.time()
    logger.info("=" * 80)
    logger.info("INICIANDO EXTRAÇÃO HISTÓRICA: LULA 1 (2003) ATÉ BOLSONARO / ATUAL (2026)")
    logger.info("=" * 80)
    
    # 1. Carregar base consolidada já existente de 2019-2026 (se existir)
    ceap_file_existing = DATA_DIR / "despesas_ceap_2019_2026.json"
    ceap_resumo = {}
    if ceap_file_existing.exists():
        logger.info(f"-> Carregando base pré-processada existente: {ceap_file_existing.name}")
        with open(ceap_file_existing, "r", encoding="utf-8") as f:
            ceap_resumo = json.load(f)
        logger.info(f"   Base prévia possui {len(ceap_resumo)} parlamentares catalogados.")
        
    # Anos históricos a processar para CEAP (2008 a 2018 - período de vigência aberta da CEAP)
    anos_ceap_historico = list(range(2008, 2019))
    logger.info(f"-> Anos a extrair para CEAP histórica: {anos_ceap_historico}")
    
    # 2. Extração Senado Federal (2008-2018)
    t_sen_start = time.time()
    total_sen_registros = 0
    for ano in anos_ceap_historico:
        t0 = time.time()
        sen_itens = extract_senado_ceaps_year(ano)
        total_sen_registros += len(sen_itens)
        logger.info(f"   [Senado {ano}] {len(sen_itens):,} registros obtidos em {time.time() - t0:.2f}s")
        
        for item in sen_itens:
            nome = item.get("nomeSenador", "").upper().strip()
            val = float(item.get("valorReembolsado") or 0.0)
            tipo = item.get("tipoDespesa", "OUTROS")
            forn = _mascarar_cpf_no_nome(item.get("fornecedor", "Não Informado"))
            cnpj = item.get("cpfCnpj")
            
            if not nome or val <= 0:
                continue
                
            if nome not in ceap_resumo:
                ceap_resumo[nome] = {
                    "nome": nome,
                    "cargo": "SENADOR",
                    "total_gasto": 0.0,
                    "total_notas": 0,
                    "por_ano": {},
                    "por_tipo": {},
                    "fornecedores": {}
                }
                
            p = ceap_resumo[nome]
            p["total_gasto"] = round(p["total_gasto"] + val, 2)
            p["total_notas"] += 1
            p["por_ano"][str(ano)] = round(p["por_ano"].get(str(ano), 0.0) + val, 2)
            p["por_tipo"][tipo] = round(p["por_tipo"].get(tipo, 0.0) + val, 2)
            
            if forn not in p["fornecedores"]:
                p["fornecedores"][forn] = {"nome": forn, "cnpj_cpf": _mascarar_cpf(cnpj), "total": 0.0, "notas": 0}
            p["fornecedores"][forn]["total"] = round(p["fornecedores"][forn]["total"] + val, 2)
            p["fornecedores"][forn]["notas"] += 1

    t_sen_end = time.time()
    logger.info(f"-> Senado (2008-2018): {total_sen_registros:,} registros processados em {t_sen_end - t_sen_start:.2f}s")

    # 3. Extração Câmara dos Deputados (2008-2018)
    t_cam_start = time.time()
    total_cam_registros = 0
    for ano in anos_ceap_historico:
        t0 = time.time()
        cnt = process_camara_ceap_year(ano, ceap_resumo)
        total_cam_registros += cnt
        logger.info(f"   [Câmara {ano}] {cnt:,} registros processados em {time.time() - t0:.2f}s")
    t_cam_end = time.time()
    logger.info(f"-> Câmara (2008-2018): {total_cam_registros:,} registros processados em {t_cam_end - t_cam_start:.2f}s")

    # 4. Filtrar Top 10 Fornecedores por parlamentar para manter arquivo leve
    for nome, data in ceap_resumo.items():
        data["total_gasto"] = round(data["total_gasto"], 2)
        top_f = sorted(data["fornecedores"].values(), key=lambda x: x["total"], reverse=True)[:10]
        data["fornecedores"] = {f["nome"]: f for f in top_f}

    # 5. Salvar CEAP Consolidada (2008 a 2026)
    out_ceap = DATA_DIR / "despesas_ceap_2019_2026.json"
    with open(out_ceap, "w", encoding="utf-8") as f:
        json.dump(ceap_resumo, f, ensure_ascii=False)
        
    logger.info(f"-> Base CEAP salva com sucesso! ({out_ceap.stat().st_size / (1024*1024):.2f} MB, {len(ceap_resumo)} parlamentares)")

    # 6. Emendas parlamentares: removido. O antigo histórico 2003-2026 era gerado por
    #    fórmula. A fonte oficial (Portal da Transparência) é integrada em PR próprio.

    total_duration = time.time() - start_time
    logger.info("=" * 80)
    logger.info(f"SINCRONIZAÇÃO COMPLETA CONCLUÍDA EM {total_duration:.2f} SEGUNDOS!")
    logger.info(f"Total CEAP registros históricos adicionados: {total_sen_registros + total_cam_registros:,}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
