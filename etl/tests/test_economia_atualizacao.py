"""Atualização diária das séries econômicas: extrai, carrega e não carrega nada se a extração falhar."""

from unittest.mock import MagicMock, patch

import pytest

from etl.pipelines import economia_atualizacao


def test_extrai_e_depois_carrega_so_series_e_mandatos():
    ordem = []
    pipeline = MagicMock()
    pipeline.return_value.run.side_effect = lambda use_cache: ordem.append("extrai") or {"annual_records": 32}

    def carga(engine, chaves=None):
        ordem.append(("carga", tuple(chaves)))
        return {"series": {"A": 1}, "presidencia": {"atualizados": 9}}

    with (
        patch.object(economia_atualizacao, "PresidentsEconomicSyncPipeline", pipeline),
        patch.object(economia_atualizacao, "carregar_tudo", side_effect=carga),
    ):
        resumo = economia_atualizacao.atualizar(MagicMock())
    # a composição e a PNAD (curadoria estática) ficam de fora de propósito
    assert ordem == ["extrai", ("carga", ("series", "presidencia"))]
    assert resumo == {"anos_resumo": 32, "series": 1, "presidentes": {"atualizados": 9}}


def test_falha_na_extracao_nao_carrega_nada():
    pipeline = MagicMock()
    pipeline.return_value.run.side_effect = RuntimeError("IPCA mensal vazio")
    with (
        patch.object(economia_atualizacao, "PresidentsEconomicSyncPipeline", pipeline),
        patch.object(economia_atualizacao, "carregar_tudo") as carga,
    ):
        with pytest.raises(RuntimeError, match="IPCA"):
            economia_atualizacao.atualizar(MagicMock())
    carga.assert_not_called()
