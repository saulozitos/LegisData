"""Atualização diária das séries econômicas: extrai, carrega e não carrega nada se a extração falhar."""

from unittest.mock import MagicMock, patch

import pytest

from etl.pipelines import economia_atualizacao


def test_extrai_e_depois_carrega():
    ordem = []
    pipeline = MagicMock()
    pipeline.return_value.run.side_effect = lambda use_cache: ordem.append("extrai") or {"annual_records": 32}
    with (
        patch.object(economia_atualizacao, "PresidentsEconomicSyncPipeline", pipeline),
        patch.object(economia_atualizacao, "carregar_series", side_effect=lambda e: ordem.append("series") or {"A": 1}),
        patch.object(
            economia_atualizacao,
            "carregar_presidencia",
            side_effect=lambda e: ordem.append("pres") or {"atualizados": 9},
        ),
    ):
        resumo = economia_atualizacao.atualizar(MagicMock())
    assert ordem == ["extrai", "series", "pres"]
    assert resumo == {"anos_resumo": 32, "series": 1, "presidentes": {"atualizados": 9}}


def test_falha_na_extracao_nao_carrega_nada():
    pipeline = MagicMock()
    pipeline.return_value.run.side_effect = RuntimeError("IPCA mensal vazio")
    with (
        patch.object(economia_atualizacao, "PresidentsEconomicSyncPipeline", pipeline),
        patch.object(economia_atualizacao, "carregar_series") as series,
        patch.object(economia_atualizacao, "carregar_presidencia") as presidencia,
    ):
        with pytest.raises(RuntimeError, match="IPCA"):
            economia_atualizacao.atualizar(MagicMock())
    series.assert_not_called()
    presidencia.assert_not_called()
