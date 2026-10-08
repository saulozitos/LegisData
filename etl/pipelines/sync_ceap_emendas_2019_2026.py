"""
Pipeline Unificado de Extração e Consolidação: CEAP e Emendas Parlamentares (2019 - 2026)
Abrange desde a posse de Flávio Bolsonaro (Senado) e 56ª Legislatura até os dias atuais.
Fontes Oficiais:
- Senado Federal: API de Dados Abertos Administrativos (CEAPS 2019-2026)
- Câmara dos Deputados: Dados Abertos de Cota Parlamentar (CEAP 2019-2026)
- Emendas Parlamentares: NÃO geradas aqui (ver comentário em main()).
"""

import io
import json
import time
import zipfile
import logging
import urllib.request
from pathlib import Path
from typing import Dict, Any, List
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CeapEmendasSync")

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parents[1]
DATA_DIR = PROJECT_ROOT / "etl" / "data" / "processed"


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


def extract_senado_ceaps(anos: List[int]) -> List[Dict[str, Any]]:
    """Extrai despesas da CEAPS diretamente da API do Senado Federal para todos os anos com retry."""
    logger.info(f"-> Extraindo CEAPS do Senado Federal para os anos: {anos}...")
    todas_despesas = []
    
    for ano in anos:
        t0 = time.time()
        url = f"https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        
        sucesso = False
        for tentativa in range(1, 4):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list):
                        todas_despesas.extend(data)
                        logger.info(f"   [Senado {ano}] {len(data):,} registros extraídos em {time.time() - t0:.2f}s")
                        sucesso = True
                        break
            except Exception as e:
                logger.warning(f"   [Senado {ano}] Tentativa {tentativa} falhou ({e}). Retentando em 2s...")
                time.sleep(2)
        if not sucesso:
            logger.error(f"   [Senado {ano}] Falha definitiva após 3 tentativas.")
            
    return todas_despesas


def extract_camara_ceap(anos: List[int]) -> pd.DataFrame:
    """Extrai despesas da CEAP diretamente dos arquivos compactados da Câmara dos Deputados."""
    logger.info(f"-> Extraindo CEAP da Câmara dos Deputados para os anos: {anos}...")
    dfs = []
    
    usecols = [
        "txNomeParlamentar", "ideCadastro", "sgUF", "sgPartido",
        "numAno", "numMes", "txtDescricao", "vlrLiquido",
        "txtFornecedor", "txtCNPJCPF", "datEmissao", "urlDocumento"
    ]
    
    for ano in anos:
        t0 = time.time()
        url = f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                content = resp.read()
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                csv_name = z.namelist()[0]
                with z.open(csv_name) as f:
                    df = pd.read_csv(
                        f, sep=";", encoding="utf-8-sig", low_memory=False, usecols=usecols
                    )
                    dfs.append(df)
                    logger.info(f"   [Câmara {ano}] {len(df):,} registros extraídos em {time.time() - t0:.2f}s")
        except Exception as e:
            logger.warning(f"   [Câmara {ano}] Falha na extração: {e}")
            
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()


def main():
    start_time = time.time()
    anos = list(range(2019, 2027))
    logger.info("=" * 80)
    logger.info(f"INICIANDO EXTRAÇÃO DE CEAP E EMENDAS: 2019 A 2026 (PERÍODO FLÁVIO BOLSONARO ATÉ HOJE)")
    logger.info("=" * 80)
    
    # 1. Carregar lista de senadores e deputados
    with open(DATA_DIR / "senadores_senado.json", "r", encoding="utf-8") as f:
        senadores = json.load(f)
    with open(DATA_DIR / "deputados_camara.json", "r", encoding="utf-8") as f:
        deputados = json.load(f)
        
    logger.info(f"Total de Senadores catalogados: {len(senadores)}")
    logger.info(f"Total de Deputados catalogados: {len(deputados)}")
    
    # 2. Extração Senado Federal (CEAPS)
    t_senado_start = time.time()
    senado_raw = extract_senado_ceaps(anos)
    t_senado_end = time.time()
    logger.info(f"-> Senado Federal: {len(senado_raw):,} registros extraídos em {t_senado_end - t_senado_start:.2f}s")
    
    # 3. Extração Câmara dos Deputados (CEAP)
    t_camara_start = time.time()
    camara_df = extract_camara_ceap(anos)
    t_camara_end = time.time()
    logger.info(f"-> Câmara dos Deputados: {len(camara_df):,} registros extraídos em {t_camara_end - t_camara_start:.2f}s")
    
    # 4. Emendas parlamentares: removido. O antigo "portfólio" era gerado por fórmula
    #    (teto x peso x taxa de execução). A fonte oficial é o Portal da Transparência
    #    (download-de-dados/emendas-parlamentares), integrada em PR próprio.

    # 5. Agregação Consolidada de CEAP por Parlamentar (Senado + Câmara)
    logger.info("-> Consolidando resumos analíticos de despesas CEAP por parlamentar...")
    ceap_resumo = {}
    
    # Processar Senado
    for item in senado_raw:
        nome = item.get("nomeSenador", "").upper().strip()
        ano = item.get("ano")
        val = float(item.get("valorReembolsado") or 0.0)
        tipo = item.get("tipoDespesa", "OUTROS")
        forn = item.get("fornecedor", "Não Informado")
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
        p["total_gasto"] += val
        p["total_notas"] += 1
        p["por_ano"][ano] = p["por_ano"].get(ano, 0.0) + val
        p["por_tipo"][tipo] = p["por_tipo"].get(tipo, 0.0) + val
        
        if forn not in p["fornecedores"]:
            p["fornecedores"][forn] = {"nome": forn, "cnpj_cpf": _mascarar_cpf(cnpj), "total": 0.0, "notas": 0}
        p["fornecedores"][forn]["total"] += val
        p["fornecedores"][forn]["notas"] += 1

    # Processar Câmara via DataFrame vetorizado
    if not camara_df.empty:
        # Filtrar valores positivos
        c_clean = camara_df[camara_df["vlrLiquido"] > 0]
        for nome_dep, group in c_clean.groupby("txNomeParlamentar"):
            nome_key = str(nome_dep).upper().strip()
            total_gasto = float(group["vlrLiquido"].sum())
            total_notas = int(len(group))
            
            por_ano = {int(k): round(float(v), 2) for k, v in group.groupby("numAno")["vlrLiquido"].sum().items()}
            por_tipo = {str(k): round(float(v), 2) for k, v in group.groupby("txtDescricao")["vlrLiquido"].sum().items()}
            
            top_forn = (
                group.groupby(["txtFornecedor", "txtCNPJCPF"])["vlrLiquido"]
                .agg(["sum", "count"])
                .reset_index()
                .sort_values(by="sum", ascending=False)
                .head(15)
            )
            fornecedores_dict = {}
            for _, r in top_forn.iterrows():
                fornecedores_dict[str(r["txtFornecedor"])] = {
                    "nome": str(r["txtFornecedor"]),
                    "cnpj_cpf": _mascarar_cpf(r["txtCNPJCPF"]) if pd.notna(r["txtCNPJCPF"]) else None,
                    "total": round(float(r["sum"]), 2),
                    "notas": int(r["count"])
                }
                
            ceap_resumo[nome_key] = {
                "nome": nome_key,
                "cargo": "DEPUTADO",
                "total_gasto": round(total_gasto, 2),
                "total_notas": total_notas,
                "por_ano": por_ano,
                "por_tipo": por_tipo,
                "fornecedores": fornecedores_dict
            }
            
    # Arredondar valores do Senado
    for k, p in ceap_resumo.items():
        if p["cargo"] == "SENADOR":
            p["total_gasto"] = round(p["total_gasto"], 2)
            p["por_ano"] = {int(ano): round(v, 2) for ano, v in p["por_ano"].items()}
            p["por_tipo"] = {tipo: round(v, 2) for tipo, v in p["por_tipo"].items()}
            top_forn_sen = sorted(p["fornecedores"].values(), key=lambda x: x["total"], reverse=True)[:15]
            p["fornecedores"] = {f["nome"]: {**f, "total": round(f["total"], 2)} for f in top_forn_sen}
            
    # 6. Salvar arquivos finais processados
    logger.info("-> Salvando arquivos finais consolidados...")
    output_ceap = DATA_DIR / "despesas_ceap_2019_2026.json"
    with open(output_ceap, "w", encoding="utf-8") as f:
        json.dump(ceap_resumo, f, ensure_ascii=False, indent=2)
        
        
    total_time = time.time() - start_time
    logger.info("=" * 80)
    logger.info(f"SUCESSO TOTAL! EXTRAÇÃO CONCLUÍDA EM: {total_time:.2f} SEGUNDOS")
    logger.info(f"- Despesas CEAP: {len(ceap_resumo)} parlamentares consolidados -> {output_ceap.name}")
    logger.info("=" * 80)
    
    # Resumo de Flávio Bolsonaro
    flavio_resumo = ceap_resumo.get("FLÁVIO BOLSONARO") or ceap_resumo.get("FLAVIO BOLSONARO")
    if flavio_resumo:
        print("\n" + "#" * 60)
        print("DADOS CONSOLIDADOS DE FLÁVIO BOLSONARO (2019-2026):")
        print(f"Total gasto CEAPS: R$ {flavio_resumo['total_gasto']:,.2f}")
        print(f"Total de notas fiscais/reembolsos: {flavio_resumo['total_notas']}")
        print("Evolução anual dos gastos:")
        for a, val in sorted(flavio_resumo['por_ano'].items()):
            print(f"  - {a}: R$ {val:,.2f}")
        print("Top 3 Maiores Fornecedores:")
        for forn_nome, f_info in list(flavio_resumo['fornecedores'].items())[:3]:
            print(f"  - {forn_nome}: R$ {f_info['total']:,.2f} ({f_info['notas']} notas)")
        print("#" * 60 + "\n")


if __name__ == "__main__":
    main()
