#!/usr/bin/env python3
"""
CLI Unificado de Execução do Pipeline de ETL e Carga no PostgreSQL
Uso:
    python3 etl/run_etl.py              # Executa toda a esteira (ETL + Carga no PostgreSQL)
    python3 etl/run_etl.py --camara     # Executa apenas a extração da Câmara dos Deputados
    python3 etl/run_etl.py --load-db    # Executa apenas a carga no PostgreSQL
    python3 etl/run_etl.py --economic   # Executa apenas BCB/IBGE e Presidentes
    python3 etl/run_etl.py --emendas    # Baixa/processa emendas do Portal da Transparência
"""

import sys
import argparse
from pathlib import Path

# Adicionar raiz do projeto e backend ao sys.path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
backend_dir = project_root / "backend"
for p in [str(project_root), str(backend_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from etl.pipelines.presidents_economic_sync import PresidentsEconomicSyncPipeline
from etl.extractors.camara_extractor import CamaraExtractor
from etl.extractors.senado_extractor import SenadoExtractor
from etl.extractors.tse_extractor import TSEExtractor
from etl.extractors.tse_oficial_extractor import TSEOficialExtractor
from etl.extractors.orcamento_extractor import OrcamentoExtractor
from etl.extractors.composicao_extractor import save_composicao_congresso
from etl.extractors.salario_inflacao_extractor import SalarioInflacaoExtractor
from etl.pipelines.db_loader import DatabaseLoader
from etl.extractors.emendas_cgu_extractor import EmendasCguExtractor


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline Integrado: Política e Economia Brasileira (ETL & Carga no PostgreSQL)"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Força requisição direta às APIs públicas sem usar cache local"
    )
    parser.add_argument(
        "--economic",
        action="store_true",
        help="Executa apenas a extração econômica e de presidentes (BCB/IBGE)"
    )
    parser.add_argument(
        "--camara",
        action="store_true",
        help="Executa apenas a extração de dados abertos da Câmara dos Deputados"
    )
    parser.add_argument(
        "--senado",
        action="store_true",
        help="Executa apenas a extração de dados abertos do Senado Federal"
    )
    parser.add_argument(
        "--tse",
        action="store_true",
        help="Executa apenas a extração de filiações partidárias do TSE"
    )
    parser.add_argument(
        "--tse-oficial",
        action="store_true",
        help="Baixa candidaturas, bens e receitas oficiais do TSE (arquivos grandes: 200-475 MB por eleição)"
    )
    parser.add_argument(
        "--orcamento",
        action="store_true",
        help="Executa a modelagem de repasses orçamentários por UF"
    )
    parser.add_argument(
        "--composicao",
        action="store_true",
        help="Executa a curadoria histórica da composição do Congresso Nacional"
    )
    parser.add_argument(
        "--renda",
        action="store_true",
        help="Executa a análise de salário mínimo vs salário parlamentar vs inflação"
    )
    parser.add_argument(
        "--emendas",
        action="store_true",
        help="Baixa e processa as emendas parlamentares do Portal da Transparência (CGU)"
    )
    parser.add_argument(
        "--load-db",
        action="store_true",
        help="Executa apenas a carga e upsert no PostgreSQL"
    )

    args = parser.parse_args()
    use_cache = not args.no_cache

    # Modo seletivo ou completo
    specific_run = args.economic or args.camara or args.senado or args.tse or args.tse_oficial or args.orcamento or args.composicao or args.renda or args.emendas or args.load_db
    run_economic = args.economic or not specific_run
    run_camara = args.camara or not specific_run
    run_senado = args.senado or not specific_run
    run_tse = args.tse or not specific_run
    run_orcamento = args.orcamento or not specific_run
    run_composicao = args.composicao or not specific_run
    run_renda = args.renda or not specific_run
    run_emendas = args.emendas or not specific_run
    run_load = args.load_db or not specific_run

    if run_economic:
        print("\n>>> [ETAPA 1/7] EXTRAÇÃO ECONÔMICA E PRESIDENTES (BCB / IBGE) <<<")
        econ_pipeline = PresidentsEconomicSyncPipeline()
        econ_pipeline.run(use_cache=use_cache)

    if run_camara:
        print("\n>>> [ETAPA 2/7] EXTRAÇÃO DADOS ABERTOS DA CÂMARA DOS DEPUTADOS <<<")
        camara_extractor = CamaraExtractor(request_delay=0.15)
        camara_extractor.run_full_extraction()

    if run_senado:
        print("\n>>> [ETAPA 3/7] EXTRAÇÃO DADOS ABERTOS DO SENADO FEDERAL <<<")
        senado_extractor = SenadoExtractor()
        senado_extractor.run_full_extraction()

    if run_tse:
        print("\n>>> [ETAPA 4/7] EXTRAÇÃO DE FILIAÇÕES PARTIDÁRIAS DO TSE <<<")
        tse_extractor = TSEExtractor()
        tse_extractor.run()

    # Opcional e explícito: downloads grandes. Não roda na esteira completa por padrão.
    if args.tse_oficial:
        print("\n>>> [TSE OFICIAL] CANDIDATURAS, BENS DECLARADOS E RECEITAS DE CAMPANHA <<<")
        print(TSEOficialExtractor().run())

    if run_orcamento:
        print("\n>>> [ETAPA 5/7] REPASSES FEDERAIS E ORÇAMENTO POR UF <<<")
        orc_extractor = OrcamentoExtractor()
        orc_extractor.run()

    if run_composicao:
        print("\n>>> [ETAPA 6/7] COMPOSIÇÃO DO CONGRESSO E GOVERNABILIDADE <<<")
        save_composicao_congresso()

    if run_renda:
        print("\n>>> [ETAPA 7/7] SALÁRIO MÍNIMO VS SUBSÍDIO PARLAMENTAR VS INFLAÇÃO <<<")
        renda_extractor = SalarioInflacaoExtractor()
        renda_extractor.run()

    if run_emendas:
        print("\n>>> [EMENDAS] PORTAL DA TRANSPARÊNCIA (CGU) <<<")
        EmendasCguExtractor().run(use_cache=use_cache)

    if run_load:
        print("\n>>> [CARGA] CARGA E UPSERT RELACIONAL NO POSTGRESQL <<<")
        loader = DatabaseLoader()
        loader.load_all()

    print("\nEsteira de execução concluída com sucesso!")


if __name__ == "__main__":
    main()
