from unittest.mock import patch

from etl.pipelines import cidadania_atualizacao as job


def test_sai_com_zero_quando_as_consultas_foram_gravadas():
    with patch.object(job, "atualizar", return_value={"atualizado": True, "itens": 12, "abertas": 4}):
        assert job.main() == 0


def test_sai_com_erro_quando_as_fontes_oficiais_nao_responderam(caplog):
    with patch.object(job, "atualizar", return_value={"atualizado": False, "itens": 0, "abertas": 0}):
        assert job.main() == 1
    assert "foto anterior foi mantida" in caplog.text
