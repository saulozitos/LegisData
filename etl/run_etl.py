#!/usr/bin/env python3
"""
CLI Unificado de Execução do Pipeline de ETL e Carga no PostgreSQL

Uso:
    python3 etl/run_etl.py                      # Toda a esteira (extração + carga no PostgreSQL)
    python3 etl/run_etl.py --camara --senado    # Etapas selecionadas
    python3 etl/run_etl.py --load-db            # Somente a carga no PostgreSQL

Dados sintéticos/estimados NUNCA são gerados por padrão. Para demonstrações locais:
    python3 etl/run_etl.py --allow-synthetic

Cada etapa é isolada: uma falha é registrada, as demais seguem, o resumo final lista o que deu certo e o que
falhou, e o processo termina com código de saída 1 se alguma etapa falhou (antes, o script sempre dizia
"concluída com sucesso"). Na esteira completa, a carga no banco só roda se todas as extrações passaram.
"""

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

# Raiz do projeto no sys.path (o backend é adicionado sob demanda por etl.utils.bootstrap)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from etl.config import ensure_data_dirs  # noqa: E402

logger = logging.getLogger("run_etl")


@dataclass
class Etapa:
    chave: str
    titulo: str
    executar: Callable[[], object]
    depende_de_extracao: bool = False  # True para etapas de carga


def _economic(use_cache: bool):
    from etl.pipelines.presidents_economic_sync import PresidentsEconomicSyncPipeline

    return PresidentsEconomicSyncPipeline().run(use_cache=use_cache)


def _camara(force_refresh: bool):
    from etl.extractors.camara_extractor import CamaraExtractor

    return CamaraExtractor(request_delay=0.15).run_full_extraction(force_refresh=force_refresh)


def _senado():
    from etl.extractors.senado_extractor import SenadoExtractor

    return SenadoExtractor().run_full_extraction()


def _filiacoes():
    from etl.extractors.tse_extractor import TSEExtractor

    return TSEExtractor().run()


def _patrimonio(force: bool):
    from etl.extractors.tse_patrimonio_extractor import TSEPatrimonioExtractor

    return TSEPatrimonioExtractor().run(force=force)


def _doacoes(force: bool):
    from etl.extractors.tse_doacoes_extractor import TseDoacoesExtractor

    return TseDoacoesExtractor().run(force=force)


def _eleicoes(force: bool):
    from etl.extractors.tse_eleicoes_extractor import TSEEleicoesExtractor

    return TSEEleicoesExtractor().run(force=force)


def _candidaturas(force: bool):
    from etl.extractors.tse_candidaturas_extractor import TSECandidaturasExtractor

    return TSECandidaturasExtractor().run(force=force)


def _social(allow_synthetic: bool):
    from etl.extractors.social_indicators_extractor import SocialIndicatorsExtractor

    return SocialIndicatorsExtractor().export_all(allow_synthetic=allow_synthetic)


def _orcamento(allow_synthetic: bool):
    from etl.extractors.orcamento_extractor import OrcamentoExtractor

    return OrcamentoExtractor().run(allow_synthetic=allow_synthetic)


def _pnad(force: bool):
    from etl.extractors.pnad_extractor import PNADExtractor

    return PNADExtractor().run(force=force)


def _votacoes(ano_inicio: int, force: bool):
    from datetime import date

    from etl.extractors.votacoes_extractor import run_votacoes

    return run_votacoes(anos=list(range(ano_inicio, date.today().year + 1)), force=force)


def _composicao():
    from etl.extractors.composicao_extractor import save_composicao_congresso

    return save_composicao_congresso()


def _anos_ja_carregados_ou_none():
    """Os anos da CEAP que o `fin` já tem, ou None quando o banco não responde (a extração manual não exige banco)."""
    try:
        from etl.utils.bootstrap import ensure_backend_on_path

        ensure_backend_on_path()
        from app.core.database import engine

        from etl.pipelines.financas_atualizacao import anos_ja_carregados

        return anos_ja_carregados(engine)
    except Exception as exc:  # noqa: BLE001 - sem banco a extração segue só com o arquivo processado
        logger.warning("Sem o fin para conferir os anos da CEAP já carregados: %s", type(exc).__name__)
        return None


def _ceap_emendas(ano_inicio: int, usar_cache: bool = True):
    from etl.pipelines.sync_ceap_emendas import ANO_INICIAL_ARQUIVO, fontes_nao_gravadas, run

    if ano_inicio != ANO_INICIAL_ARQUIVO:
        logger.warning(
            "Janela da CEAP/emendas a partir de %s (a atualização diária usa %s): se o fin crescer com anos anteriores, a "
            "atualização diária vai recusar a carga porque ela deixaria esses anos sem gasto; aceite uma vez com "
            "LEGISDATA_ACEITAR_ENCOLHIMENTO=1.",
            ano_inicio,
            ANO_INICIAL_ARQUIVO,
        )
    from etl.pipelines.financas_atualizacao import CACHE_DIR

    # o mesmo cache por ano e a mesma proteção do começo do ano da atualização diária (os anos já carregados vêm do `fin`;
    # sem banco, vale só o arquivo processado)
    # --no-cache baixa tudo de novo, mas continua gravando o cache e mantém a reserva do cache vencido
    resumo = run(
        ano_inicio=ano_inicio,
        cache_dir=CACHE_DIR,
        anos_publicados=_anos_ja_carregados_ou_none(),
        ignorar_cache=not usar_cache,
    )
    if fontes_nao_gravadas(resumo):
        raise RuntimeError(f"CEAP/emendas não gravadas (arquivos anteriores preservados): {resumo}")
    # a API lê o banco, não os arquivos: o dossiê só enxerga o dado novo depois de `--load-economia`
    logger.info(
        "CEAP/emendas gravadas em arquivo. Com --load-economia nesta mesma execução a carga é automática; numa execução "
        "separada, rode --load-economia --recarregar-ceap-emendas --arquivos-frescos para levá-las ao schema fin."
    )
    return resumo


def _load_db(allow_synthetic: bool, allow_unverified: bool, purge: bool):
    from etl.pipelines.db_loader import DatabaseLoader

    return DatabaseLoader(
        allow_synthetic=allow_synthetic, allow_unverified=allow_unverified, purge_legacy_synthetic=purge
    ).load_all()


def _processos(allow_unverified_legal: bool):
    from etl.utils.bootstrap import ensure_backend_on_path

    ensure_backend_on_path()
    from app.core.database import SessionLocal  # backend já está no path (db_loader/bootstrap) — importado sob demanda

    from etl.extractors.processos_loader import populate_processos_judiciais

    with SessionLocal() as session:
        return populate_processos_judiciais(session, allow_unverified=allow_unverified_legal)


def _camara_bulk(force: bool, ano_inicio: int):
    from datetime import date

    from etl.utils.bootstrap import ensure_backend_on_path

    ensure_backend_on_path()
    from app.core.database import engine
    from app.core.migrations import upgrade_schema

    from etl.extractors.camara_bulk_extractor import CamaraBulkExtractor
    from etl.pipelines.camara_bulk_loader import carregar

    upgrade_schema()
    arquivos = CamaraBulkExtractor(anos=range(ano_inicio, date.today().year + 1)).run(force=force)
    resumo = carregar(engine, arquivos)
    print(f"    {resumo['merge']}")
    return resumo


def _camara_historico(force: bool):
    from etl.utils.bootstrap import ensure_backend_on_path

    ensure_backend_on_path()
    from app.core.database import engine
    from app.core.migrations import upgrade_schema

    from etl.extractors.camara_historico_extractor import CamaraHistoricoExtractor
    from etl.pipelines.camara_historico_loader import carregar

    upgrade_schema()
    extrator = CamaraHistoricoExtractor()
    baixado = extrator.run(force=force)
    if baixado["falhas"]:
        raise RuntimeError(f"{len(baixado['falhas'])} históricos não baixados (ex.: {baixado['falhas'][0]})")
    resumo = carregar(engine, extrator.raw_dir)
    print(f"    {resumo['merge']}")
    return resumo


def _presenca(no_cache: bool, max_paginas: Optional[int]):
    from etl.extractors.camara_presenca_eventos_extractor import CamaraPresencaEventosExtractor
    from etl.extractors.presenca_extractor import PresencaExtractor, ids_deputados_conhecidos

    arquivos = CamaraPresencaEventosExtractor().run(force=no_cache)
    print(f"    Câmara (antes de 2020): {len(arquivos)} arquivos de eventos e presença em eventos")
    resultado = PresencaExtractor().run(
        usar_cache=not no_cache, ids_camara=ids_deputados_conhecidos(), max_paginas_novas=max_paginas
    )
    for casa, dados in resultado.items():
        print(
            f"    {casa}: {len(dados['resumos'])} resumos parlamentar/ano, {len(dados['dias'])} dias, "
            f"{len(dados['falhas'])} falhas, {dados.get('paginas_pendentes', 0)} páginas pendentes"
        )
        if dados["falhas"]:
            raise RuntimeError(f"{casa}: {len(dados['falhas'])} falhas de extração (ex.: {dados['falhas'][0]})")


def _remuneracao(no_cache: bool):
    from etl.extractors.presenca_extractor import ids_deputados_conhecidos
    from etl.extractors.remuneracao_extractor import RemuneracaoExtractor

    resultado = RemuneracaoExtractor().run(usar_cache=not no_cache, ids_permitidos=ids_deputados_conhecidos())
    print(f"    {len(resultado['registros'])} registros mensais, {len(resultado['cobertura']['falhas'])} falhas")
    if resultado["cobertura"]["falhas"]:
        raise RuntimeError(f"{len(resultado['cobertura']['falhas'])} falhas de extração")


def _load_economia(recarregar_ceap_e_emendas: bool = False, extracao_fresca: bool = False):
    from functools import partial

    from etl.utils.bootstrap import ensure_backend_on_path

    ensure_backend_on_path()
    from app.core.database import engine

    from etl.pipelines.carga_economica import CARGAS, carregar_tudo
    from etl.pipelines.financas_loader import registrar_carga_do_git, registrar_carga_fresca

    # A carga de cada fonte das finanças registra, na própria transação, de onde veio o dado: extração fresca desta execução
    # (o `fin` passa a ter dado mais novo que o git e o deploy não semeia de novo essa fonte) ou o retrato do git.
    hook = partial(registrar_carga_fresca, origem="run_etl") if extracao_fresca else registrar_carga_do_git
    resultados = carregar_tudo(
        engine,
        recarregar_ceap_e_emendas=recarregar_ceap_e_emendas,
        opcoes={"financas": {"ao_confirmar": hook}},
    )
    nomes = {chave: nome for chave, nome, _, _ in CARGAS}
    for chave, resultado in resultados.items():
        print(f"    {nomes[chave]}:", resultado)


def _load_presenca_remuneracao():
    from etl.utils.bootstrap import ensure_backend_on_path

    ensure_backend_on_path()
    from app.core.database import SessionLocal, engine

    from etl.pipelines.load_attendance_and_remuneration import load_remunerations
    from etl.pipelines.presenca_leg_loader import carregar as carregar_presenca

    print("    Presença (leg.presenca):", carregar_presenca(engine))
    db = SessionLocal()
    try:
        print("    Remuneração:", load_remunerations(db))
    finally:
        db.close()


def montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pipeline Integrado: Política e Economia Brasileira (ETL & Carga no PostgreSQL)"
    )
    p.add_argument("--no-cache", action="store_true", help="Ignora caches locais (BCB e cache de deputados)")
    for flag, ajuda in [
        ("economic", "Extração econômica e de presidentes (BCB/INPE/indicadores)"),
        ("camara", "Dados abertos da Câmara dos Deputados"),
        ("senado", "Dados abertos do Senado Federal"),
        ("tse", "Filiações partidárias"),
        ("patrimonio", "Declarações de patrimônio (TSE, bem_candidato)"),
        ("doacoes", "Financiamento de campanha (TSE, prestação de contas de candidatos)"),
        ("eleicoes", "Eleições presidenciais por UF (TSE, votação por candidato/município/zona)"),
        ("candidaturas", "Situação do registro de candidatura / ficha limpa (TSE, consulta_cand)"),
        ("social", "Indicadores sociais oficiais (IBGE/SIDRA) e eleições presidenciais por UF (manuais)"),
        ("orcamento", "Repasses federais por UF (Portal da Transparência, CSV mensal oficial)"),
        ("composicao", "Composição histórica do Congresso"),
        ("pnad", "Faixas de salário mínimo a partir dos microdados da PNAD Contínua (IBGE)"),
        (
            "ceap",
            "CEAP (Câmara/Senado) e emendas oficiais; usa o cache por ano (--no-cache o ignora) e confere no fin os anos já carregados",
        ),
        ("votacoes", "Votações nominais em plenário (Câmara e Senado) com orientação do governo e ex-parlamentares"),
        ("presenca", "Presença em plenário (Câmara: portal oficial; Senado: votações nominais)"),
        ("remuneracao", "Remuneração mensal dos deputados (portal da Câmara)"),
        ("camara-bulk", "Proposições e autores de todos os anos (CSV em lote da Câmara) direto no PostgreSQL"),
        ("camara-historico", "Histórico de mandatos dos deputados (posse, licença, suplência, partido) desde 1995"),
        ("load-db", "Carga e upsert no PostgreSQL"),
        ("load-presenca", "Carga de presença e remuneração oficiais no PostgreSQL"),
        ("load-economia", "Carga das séries econômicas, mandatos, composição, PNAD (eco/leg) e finanças (fin)"),
        ("processos", "Carga do acervo manual de processos judiciais (exige --allow-unverified-legal)"),
    ]:
        p.add_argument(f"--{flag}", action="store_true", help=ajuda)
    p.add_argument(
        "--recarregar-ceap-emendas",
        action="store_true",
        help="Com --load-economia: recarrega CEAP e emendas dos arquivos mesmo com o fin já carregado (padrão: só as "
        "cargas estáticas, porque a atualização diária mantém CEAP e emendas mais novas que o arquivo do git)",
    )
    p.add_argument(
        "--arquivos-frescos",
        action="store_true",
        help="Com --load-economia --recarregar-ceap-emendas: declara que os arquivos de CEAP e emendas foram extraídos por um "
        "--ceap de outra execução (mais novos que o git). A carga grava a posse como fresca; sem esta opção, recarregar "
        "de arquivos que esta execução não extraiu é tratado como o retrato do git e o deploy volta a semeá-los.",
    )
    p.add_argument(
        "--ceap-ano-inicio",
        type=int,
        default=2019,
        help="Ano inicial do CEAP/emendas (padrão: 2019, o mesmo da atualização diária; outro valor faz a atualização diária recusar a carga como encolhimento)",
    )
    p.add_argument(
        "--presenca-max-paginas",
        type=int,
        default=None,
        help="Máximo de páginas novas do portal da Câmara por execução (o portal limita a taxa; a extração é retomável)",
    )
    p.add_argument(
        "--bulk-ano-inicio", type=int, default=1995, help="Ano inicial das proposições em lote (padrão: 1995)"
    )
    p.add_argument("--votacoes-ano-inicio", type=int, default=2019, help="Ano inicial das votações (padrão: 2019)")
    p.add_argument(
        "--allow-synthetic", action="store_true", help="Gera/carrega dados SINTÉTICOS marcados (demonstração)"
    )
    p.add_argument(
        "--allow-unverified", action="store_true", help="Carrega dados digitados e não verificados (eleições por UF)"
    )
    p.add_argument(
        "--allow-unverified-legal", action="store_true", help="Autoriza o acervo manual de processos judiciais"
    )
    p.add_argument(
        "--purge-legacy-synthetic",
        action="store_true",
        help="DESTRUTIVO: apaga sintéticos legados do banco antes da carga",
    )
    return p


def construir_etapas(args: argparse.Namespace) -> List[Etapa]:
    chaves = [
        "economic",
        "camara",
        "senado",
        "tse",
        "patrimonio",
        "doacoes",
        "eleicoes",
        "candidaturas",
        "social",
        "orcamento",
        "composicao",
        "pnad",
        "ceap",
        "votacoes",
        "presenca",
        "remuneracao",
        "camara_bulk",
        "camara_historico",
        "load_db",
        "load_presenca",
        "load_economia",
        "processos",
    ]
    selecionadas = {k for k in chaves if getattr(args, k)}
    modo_completo = not selecionadas

    def quer(chave: str) -> bool:
        # Etapas que exigem autorização explícita nunca entram só por "modo completo"
        if chave == "processos":
            return args.processos or args.allow_unverified_legal
        return modo_completo or chave in selecionadas

    cache = not args.no_cache
    ceap_gravada = {"ok": False}  # a extração desta execução terminou bem? Só então ela vale como "mais nova que o fin"

    def extrair_ceap():
        resumo = _ceap_emendas(args.ceap_ano_inicio, usar_cache=cache)  # levanta se alguma fonte não foi gravada
        ceap_gravada["ok"] = True
        return resumo

    catalogo = [
        Etapa("economic", "Extração econômica e presidentes (BCB / INPE)", lambda: _economic(cache)),
        Etapa("camara", "Dados abertos da Câmara dos Deputados", lambda: _camara(args.no_cache)),
        Etapa("senado", "Dados abertos do Senado Federal", _senado),
        Etapa("tse", "Filiações partidárias", _filiacoes),
        Etapa("patrimonio", "Declarações de patrimônio (TSE)", lambda: _patrimonio(args.no_cache)),
        Etapa("doacoes", "Financiamento de campanha (TSE)", lambda: _doacoes(args.no_cache)),
        Etapa("eleicoes", "Eleições presidenciais por UF (TSE)", lambda: _eleicoes(args.no_cache)),
        Etapa("candidaturas", "Situação do registro de candidatura (TSE)", lambda: _candidaturas(args.no_cache)),
        Etapa("social", "Indicadores sociais e eleições por UF", lambda: _social(args.allow_synthetic)),
        Etapa(
            "orcamento", "Repasses federais por UF (Portal da Transparência)", lambda: _orcamento(args.allow_synthetic)
        ),
        Etapa("composicao", "Composição do Congresso e governabilidade", _composicao),
        Etapa("pnad", "Faixas de salário mínimo (microdados PNAD Contínua)", lambda: _pnad(args.no_cache)),
        Etapa("ceap", "CEAP e emendas parlamentares oficiais", extrair_ceap),
        Etapa(
            "votacoes",
            "Votações nominais e orientação do governo (Câmara e Senado)",
            lambda: _votacoes(args.votacoes_ano_inicio, args.no_cache),
        ),
        Etapa(
            "presenca",
            "Presença em plenário (Câmara e Senado)",
            lambda: _presenca(args.no_cache, args.presenca_max_paginas),
        ),
        Etapa("remuneracao", "Remuneração mensal dos deputados", lambda: _remuneracao(args.no_cache)),
        Etapa(
            "camara_bulk",
            "Proposições e autores de todos os anos (CSV em lote da Câmara)",
            lambda: _camara_bulk(args.no_cache, args.bulk_ano_inicio),
        ),
        Etapa(
            "camara_historico",
            "Histórico de mandatos dos deputados (Câmara)",
            lambda: _camara_historico(args.no_cache),
        ),
        Etapa(
            "load_db",
            "Carga e upsert relacional no PostgreSQL",
            lambda: _load_db(args.allow_synthetic, args.allow_unverified, args.purge_legacy_synthetic),
            depende_de_extracao=True,
        ),
        Etapa(
            "load_presenca",
            "Carga de presença e remuneração oficiais",
            _load_presenca_remuneracao,
            depende_de_extracao=True,
        ),
        Etapa(
            "load_economia",
            "Carga das séries econômicas, mandatos presidenciais, composição do Congresso, PNAD e finanças (fin)",
            # a CEAP e as emendas extraídas COM SUCESSO nesta mesma execução são mais novas que o `fin`: entram na carga
            lambda: _load_economia(
                args.recarregar_ceap_emendas or ceap_gravada["ok"],
                # `--arquivos-frescos`: os arquivos foram extraídos por um `--ceap` de OUTRA execução (nenhum deploy os
                # devolveu ao git desde então); sem isso, recarregar a partir deles revogaria a posse do timer
                extracao_fresca=ceap_gravada["ok"] or args.arquivos_frescos,
            ),
            depende_de_extracao=True,
        ),
        Etapa(
            "processos",
            "Processos judiciais (acervo manual)",
            lambda: _processos(args.allow_unverified_legal),
            depende_de_extracao=True,
        ),
    ]
    etapas = [e for e in catalogo if quer(e.chave)]
    return etapas


def executar(etapas: List[Etapa], modo_completo: bool) -> Dict[str, str]:
    resultados: Dict[str, str] = {}
    total = len(etapas)
    for i, etapa in enumerate(etapas, start=1):
        print(f"\n>>> [ETAPA {i}/{total}] {etapa.titulo.upper()} <<<")

        falhas_extracao = [k for k, v in resultados.items() if v.startswith("FALHOU")]
        if modo_completo and etapa.depende_de_extracao and falhas_extracao:
            resultados[etapa.chave] = f"PULADA (extração com falha: {', '.join(falhas_extracao)})"
            print(f"    {resultados[etapa.chave]}")
            continue

        inicio = time.time()
        try:
            etapa.executar()
            resultados[etapa.chave] = f"OK ({time.time() - inicio:.1f}s)"
        except Exception as exc:  # noqa: BLE001 — a etapa é isolada de propósito; o erro é registrado e relatado
            logger.error("Etapa '%s' falhou: %s", etapa.chave, exc, exc_info=True)
            resultados[etapa.chave] = f"FALHOU: {exc}"
    return resultados


def imprimir_resumo(resultados: Dict[str, str]) -> bool:
    print("\n" + "=" * 70)
    print("RESUMO DA ESTEIRA")
    print("=" * 70)
    for chave, status in resultados.items():
        print(f"  {chave:<12} {status}")
    ok = all(v.startswith("OK") for v in resultados.values())
    print("=" * 70)
    print(
        "Esteira concluída com sucesso."
        if ok
        else "Esteira concluída COM FALHAS ou etapas puladas — veja o resumo acima."
    )
    return ok


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = montar_parser()
    args = parser.parse_args(argv)
    if args.arquivos_frescos and not (args.load_economia and args.recarregar_ceap_emendas):
        parser.error("--arquivos-frescos só vale com --load-economia --recarregar-ceap-emendas")
    ensure_data_dirs()

    etapas = construir_etapas(args)
    if not etapas:
        print("Nenhuma etapa selecionada.")
        return 0
    modo_completo = not any(
        getattr(args, k)
        for k in [
            "economic",
            "camara",
            "senado",
            "tse",
            "patrimonio",
            "social",
            "orcamento",
            "composicao",
            "pnad",
            "ceap",
            "votacoes",
            "presenca",
            "remuneracao",
            "camara_bulk",
            "camara_historico",
            "load_db",
            "load_presenca",
            "load_economia",
            "processos",
        ]
    )
    resultados = executar(etapas, modo_completo)
    return 0 if imprimir_resumo(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
