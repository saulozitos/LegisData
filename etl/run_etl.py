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
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

# Raiz do projeto no sys.path (o backend é adicionado sob demanda por etl.utils.bootstrap)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from etl.config import ensure_data_dirs  # noqa: E402
from etl.fontes import ESTAGIOS, FONTES, resolver  # noqa: E402

logger = logging.getLogger("run_etl")


@dataclass
class Etapa:
    chave: str
    titulo: str
    executar: Callable[[], object]
    depende_de_extracao: bool = False  # True para etapas de carga
    # True para etapas que gravam no Postgres: ao fim da esteira rodam os derivados e o ANALYZE
    grava_banco: bool = False


def _economic(use_cache: bool):
    from etl.pipelines.presidents_economic_sync import PresidentsEconomicSyncPipeline

    return PresidentsEconomicSyncPipeline().run(use_cache=use_cache)


def _camara(force_refresh: bool):
    from etl.extractors.camara_extractor import CamaraExtractor

    return CamaraExtractor(request_delay=0.15).run_full_extraction(force_refresh=force_refresh)


def _senado():
    from etl.extractors.senado_extractor import SenadoExtractor

    return SenadoExtractor().run_full_extraction()


def _senadores_basicos():
    from etl.extractors import senadores_basicos_extractor

    return senadores_basicos_extractor.gerar()


def _senadores_filiacoes():
    from etl.extractors import senadores_filiacoes_extractor

    return senadores_filiacoes_extractor.gerar()


def _cpf():
    from etl.extractors.cpf_extractor import gerar

    return gerar()


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


def _votacoes(ano_inicio: Optional[int], force: bool):
    from datetime import date

    from etl.extractors.votacoes_extractor import ANO_INICIAL_PADRAO, run_votacoes

    inicio = _ano_a_partir_do_corte("CAMARA_API", "votacoes", ano_inicio, ANO_INICIAL_PADRAO)
    return run_votacoes(anos=list(range(inicio, date.today().year + 1)), force=force)


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


def _load_db(allow_synthetic: bool, allow_unverified: bool, recursos: Optional[List[str]] = None):
    from etl.carga.orquestra import RECURSOS, Carga
    from etl.utils.bootstrap import ensure_backend_on_path

    ensure_backend_on_path()
    from app.core.migrations import upgrade_schema

    upgrade_schema()
    # camara_historico e camara_lote têm etapa própria (baixam e carregam juntos): aqui só o que vem dos arquivos processados
    pedidos = [r for r in (recursos or RECURSOS) if r not in ("camara_historico", "camara_lote")]
    resultados = Carga(allow_synthetic=allow_synthetic, allow_unverified=allow_unverified).carregar(pedidos)
    return {recurso: vars(r.contagem) for recurso, r in resultados.items()}


def _processos():
    from etl.extractors.processos_extractor import extrair

    return extrair()


def _ano_a_partir_do_corte(fonte: str, recurso: str, explicito: Optional[int], padrao: int) -> int:
    """
    O primeiro ano a baixar: o que o usuário pediu; sem pedido, o ano do corte da última carga (os arquivos do ano
    corrente mudam todo dia, então o ano anterior ao corte é refeito por segurança); sem corte, o início da janela.
    """
    if explicito is not None:
        return explicito
    from etl.carga.base import data_de_corte
    from etl.utils.bootstrap import ensure_backend_on_path

    ensure_backend_on_path()
    from app.core.database import engine

    corte = data_de_corte(engine, fonte, recurso)
    return max(padrao, corte.year - 1) if corte else padrao


def _camara_bulk(force: bool, ano_inicio: Optional[int]):
    from datetime import date

    from etl.utils.bootstrap import ensure_backend_on_path

    ensure_backend_on_path()
    from app.core.database import engine
    from app.core.migrations import upgrade_schema

    from etl.carga.orquestra import Carga
    from etl.extractors.camara_bulk_extractor import CamaraBulkExtractor

    upgrade_schema()
    inicio = _ano_a_partir_do_corte("CAMARA_CSV", "camara_lote", ano_inicio, 1995)
    arquivos = CamaraBulkExtractor(anos=range(inicio, date.today().year + 1)).run(force=force)
    resultados = Carga(engine=engine, lote_arquivos=arquivos).carregar(["camara_lote"])
    print(f"    {resultados['camara_lote'].contagem}")
    return {"camara_lote": resultados["camara_lote"].extras}


def _camara_historico(force: bool):
    from etl.utils.bootstrap import ensure_backend_on_path

    ensure_backend_on_path()
    from app.core.database import engine
    from app.core.migrations import upgrade_schema

    from etl.carga.orquestra import Carga
    from etl.extractors.camara_historico_extractor import CamaraHistoricoExtractor

    upgrade_schema()
    extrator = CamaraHistoricoExtractor()
    baixado = extrator.run(force=force)
    if baixado["falhas"]:
        raise RuntimeError(f"{len(baixado['falhas'])} históricos não baixados (ex.: {baixado['falhas'][0]})")
    resultados = Carga(engine=engine, historico_dir=extrator.raw_dir).carregar(["camara_historico"])
    print(f"    {resultados['camara_historico'].contagem}")
    return {"camara_historico": resultados["camara_historico"].extras}


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


def _load_presenca():
    from etl.utils.bootstrap import ensure_backend_on_path

    ensure_backend_on_path()
    from app.core.database import engine

    from etl.pipelines.presenca_leg_loader import carregar as carregar_presenca

    print("    Presença (leg.presenca):", carregar_presenca(engine))


def _engine_ou_none():
    """O engine do backend, ou None quando o banco não está configurado (extração e relatório não exigem banco)."""
    try:
        from etl.utils.bootstrap import ensure_backend_on_path

        ensure_backend_on_path()
        from app.core.database import engine

        return engine
    except Exception as exc:  # noqa: BLE001 - sem banco a esteira de extração segue
        logger.warning("Sem acesso ao banco para registrar a esteira: %s", type(exc).__name__)
        return None


def executar_registrando(etapas: List[Etapa], modo_completo: bool) -> Dict[str, str]:
    """
    Roda a esteira e, quando alguma etapa grava no banco, registra a rodada inteira em `etl.execucao` (fonte `PIPELINE`,
    estágio `TUDO`): `lidas` = etapas, `gravadas` = etapas que terminaram bem, `rejeitadas` = as que falharam ou foram
    puladas. Registrar a rodada nunca derruba a esteira.
    """
    engine = _engine_ou_none() if any(e.grava_banco for e in etapas) else None
    with ExitStack() as pilha:
        execucao = None
        if engine is not None:
            try:
                from etl.utils.execucao import registrar_execucao

                # o registro abre aqui dentro: banco fora do ar ou migração 0039 ainda não aplicada falham ao ENTRAR
                execucao = pilha.enter_context(
                    registrar_execucao(engine, "PIPELINE", "TUDO", {"etapas": [e.chave for e in etapas]})
                )
            except Exception as exc:  # noqa: BLE001 - registrar a rodada nunca derruba a esteira
                logger.warning("Rodada não registrada em etl.execucao: %s", type(exc).__name__)
        resultados = executar(etapas, modo_completo)
        if execucao is not None:
            falhas = sum(1 for v in resultados.values() if not v.startswith("OK"))
            execucao.lidas, execucao.rejeitadas = len(resultados), falhas
            execucao.gravadas = len(resultados) - falhas
    return resultados


def imprimir_relatorio(desde: datetime) -> None:
    """O relatório das execuções registradas desde `desde`; sem banco ou sem execuções, não imprime nada de errado."""
    engine = _engine_ou_none()
    if engine is None:
        return
    try:
        from etl.utils.relatorio import montar_relatorio

        print("\n" + montar_relatorio(engine, desde))
    except Exception as exc:  # noqa: BLE001 - o relatório é um extra: a esteira já terminou
        logger.warning("Relatório não gerado: %s", type(exc).__name__)


def montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pipeline Integrado: Política e Economia Brasileira (ETL & Carga no PostgreSQL)"
    )
    p.add_argument("--no-cache", action="store_true", help="Ignora caches locais (BCB e cache de deputados)")
    for flag, ajuda in [
        ("economic", "Extração econômica e de presidentes (BCB/INPE/indicadores)"),
        ("camara", "Dados abertos da Câmara dos Deputados"),
        ("senado", "Dados abertos do Senado Federal"),
        ("cpf", "Identificador do CPF por HMAC (Câmara e TSE; o CPF nunca é gravado)"),
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
        ("load-presenca", "Carga de presença oficial (leg.presenca) no PostgreSQL"),
        ("load-economia", "Carga das séries econômicas, mandatos, composição, PNAD (eco/leg) e finanças (fin)"),
        (
            "processos",
            "Processos judiciais: enriquece a curadoria com o DataJud (CNJ) e grava o arquivo da carga; só extrai, carregue com --load-economia",
        ),
    ]:
        p.add_argument(f"--{flag}", action="store_true", help=ajuda)
    p.add_argument(
        "--fonte",
        action="append",
        choices=sorted(FONTES),
        help="Só esta fonte (repetível); com --estagio escolhe extrair, carregar ou tudo. Reexecuta a fonte sem tocar nas outras",
    )
    p.add_argument(
        "--estagio",
        choices=ESTAGIOS,
        default="tudo",
        help="Com --fonte: extrair (baixa os arquivos), carregar (grava no banco) ou tudo (padrão)",
    )
    p.add_argument("--listar-fontes", action="store_true", help="Lista as fontes de --fonte e sai")
    p.add_argument(
        "--relatorio",
        action="store_true",
        help="Só imprime o relatório das execuções das últimas 24 horas (fontes, linhas, rejeitos e verificações) e sai",
    )
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
        "--bulk-ano-inicio",
        type=int,
        default=None,
        help="Ano inicial das proposições em lote (padrão: o ano anterior ao corte da última carga; sem corte, 1995)",
    )
    p.add_argument(
        "--votacoes-ano-inicio",
        type=int,
        default=None,
        help="Ano inicial das votações (padrão: o ano anterior ao corte da última carga; sem corte, 2003)",
    )
    p.add_argument(
        "--allow-synthetic", action="store_true", help="Gera/carrega dados SINTÉTICOS marcados (demonstração)"
    )
    p.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Carrega dados sem fonte registrada (proposições e autores sem `autor_fonte`)",
    )
    return p


def construir_etapas(args: argparse.Namespace) -> List[Etapa]:
    chaves = [
        "economic",
        "camara",
        "senado",
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
        "cpf",
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
    recursos_load_db: Optional[List[str]] = None
    if args.fonte:
        chaves_da_fonte, recursos_load_db = resolver(args.fonte, args.estagio)
        selecionadas |= set(chaves_da_fonte)
    modo_completo = not selecionadas

    def quer(chave: str) -> bool:
        # O DataJud só entra quando pedido (consulta uma API externa por processo)
        if chave == "processos":
            return args.processos
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
        # depois de votações e presença (de onde vêm os senadores a completar) e antes do CPF (que casa por nome e nascimento)
        Etapa("senadores_basicos", "Nome completo e nascimento dos senadores (Senado)", _senadores_basicos),
        Etapa("senadores_filiacoes", "Filiações partidárias dos senadores (Senado)", _senadores_filiacoes),
        Etapa("cpf", "Identificador do CPF por HMAC (Câmara e TSE)", _cpf),
        Etapa("remuneracao", "Remuneração mensal dos deputados", lambda: _remuneracao(args.no_cache)),
        Etapa(
            "camara_bulk",
            "Proposições e autores de todos os anos (CSV em lote da Câmara)",
            lambda: _camara_bulk(args.no_cache, args.bulk_ano_inicio),
            grava_banco=True,
        ),
        Etapa(
            "camara_historico",
            "Histórico de mandatos dos deputados (Câmara)",
            lambda: _camara_historico(args.no_cache),
            grava_banco=True,
        ),
        Etapa(
            "load_db",
            "Carga e upsert relacional no PostgreSQL",
            lambda: _load_db(args.allow_synthetic, args.allow_unverified, recursos_load_db or None),
            depende_de_extracao=True,
            grava_banco=True,
        ),
        Etapa(
            "load_presenca",
            "Carga de presença oficial (leg.presenca)",
            _load_presenca,
            depende_de_extracao=True,
            grava_banco=True,
        ),
        Etapa("processos", "Processos judiciais (DataJud)", _processos),
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
            grava_banco=True,
        ),
    ]
    etapas = [e for e in catalogo if quer(e.chave)]
    return etapas


def _posprocessar() -> str:
    """
    Uma vez, no fim da esteira, se alguma etapa gravou: o ANALYZE e os derivados do legislativo. Nunca derruba a esteira;
    devolve o estado dos derivados (`'refeito'`, `'em_dia'`, `'ocupado'` ou `'falhou'`).
    """
    try:
        from etl.utils.bootstrap import ensure_backend_on_path

        ensure_backend_on_path()
        from app.core.database import engine

        from etl.utils.manutencao import posprocessar_carga

        return posprocessar_carga(engine)
    except Exception as exc:  # noqa: BLE001 - as etapas já terminaram; o leitor refaz o que faltar
        logger.warning("Pós-processamento da carga não executado: %s", exc)
        # literal de propósito: `etl.utils.manutencao.ESTADO_FALHOU` mora num módulo cujo import pode ser o que falhou aqui
        # (um teste confere que os dois valores são o mesmo)
        return "falhou"


def executar(etapas: List[Etapa], modo_completo: bool) -> Dict[str, str]:
    resultados: Dict[str, str] = {}
    total = len(etapas)
    gravou = False
    for i, etapa in enumerate(etapas, start=1):
        print(f"\n>>> [ETAPA {i}/{total}] {etapa.titulo.upper()} <<<")

        falhas_extracao = [k for k, v in resultados.items() if v.startswith("FALHOU")]
        if modo_completo and etapa.depende_de_extracao and falhas_extracao:
            resultados[etapa.chave] = f"PULADA (extração com falha: {', '.join(falhas_extracao)})"
            print(f"    {resultados[etapa.chave]}")
            continue

        inicio = time.time()
        gravou = gravou or etapa.grava_banco  # uma etapa que confirma lotes e falha depois também deixou o banco mudado
        try:
            etapa.executar()
            resultados[etapa.chave] = f"OK ({time.time() - inicio:.1f}s)"
        except Exception as exc:  # noqa: BLE001 — a etapa é isolada de propósito; o erro é registrado e relatado
            logger.error("Etapa '%s' falhou: %s", etapa.chave, exc, exc_info=True)
            resultados[etapa.chave] = f"FALHOU: {exc}"
    if gravou:
        logger.info("Derivados do legislativo ao fim da esteira: %s", _posprocessar())
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
    if args.listar_fontes:
        for slug, fonte in sorted(FONTES.items()):
            print(f"  {slug:<18} {fonte.descricao}")
        return 0
    if args.relatorio:
        imprimir_relatorio(datetime.now(timezone.utc) - timedelta(hours=24))
        return 0

    etapas = construir_etapas(args)
    if not etapas:
        print("Nenhuma etapa selecionada.")
        return 0
    modo_completo = not args.fonte and not any(
        getattr(args, k)
        for k in [
            "economic",
            "camara",
            "senado",
            "patrimonio",
            "social",
            "orcamento",
            "composicao",
            "pnad",
            "ceap",
            "votacoes",
            "cpf",
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
    inicio = datetime.now(timezone.utc)
    resultados = executar_registrando(etapas, modo_completo)
    ok = imprimir_resumo(resultados)
    if any(e.grava_banco for e in etapas):
        imprimir_relatorio(inicio)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
