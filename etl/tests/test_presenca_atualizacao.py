from unittest.mock import MagicMock, patch

import pytest

from etl.pipelines import presenca_atualizacao as pa


def test_atualizar_interrompe_sem_carregar_quando_a_extracao_tem_falhas():
    with (
        patch.object(pa, "CamaraPresencaEventosExtractor") as eventos,
        patch.object(pa, "PresencaExtractor") as extrator,
        patch.object(pa, "carregar") as carga,
    ):
        eventos.return_value.run.return_value = []
        extrator.return_value.run.return_value = {"SENADO": {"falhas": ["2026-09: erro"]}, "CAMARA": {"falhas": []}}
        with pytest.raises(RuntimeError, match="carga não executada"):
            pa.atualizar(MagicMock())
        carga.assert_not_called()


def test_atualizar_carrega_so_as_linhas_oficiais():
    with (
        patch.object(pa, "CamaraPresencaEventosExtractor") as eventos,
        patch.object(pa, "PresencaExtractor") as extrator,
        patch.object(pa, "carregar", return_value={"senado": {}}) as carga,
    ):
        eventos.return_value.run.return_value = ["a", "b"]
        extrator.return_value.run.return_value = {"SENADO": {"falhas": []}, "CAMARA": {"falhas": []}}
        resumo = pa.atualizar(MagicMock())
        assert carga.call_args.kwargs == {"anos_eventos": []}  # a história inferida anterior a 2020 não é regravada
        assert resumo["arquivos_eventos"] == 2
