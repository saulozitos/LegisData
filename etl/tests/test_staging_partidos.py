"""Os partidos da carga: o montador puro (`montar_partidos`). A junção com `core.partido` está em `test_carga_cadastro`."""

import json

from etl.config import PROCESSED_DATA_DIR
from etl.pipelines import dados_partidos as dp
from etl.pipelines import staging_partidos as sp
from etl.pipelines.loader_helpers import SEM_PARTIDO


def _dados(tmp_path, deputados=(), senadores=(), filiacoes=(), presidentes=()):
    for nome, linhas in [
        ("deputados_camara.json", deputados),
        ("senadores_senado.json", senadores),
        ("filiacoes_partidarias.json", filiacoes),
        ("presidentes_historico.json", presidentes),
    ]:
        (tmp_path / nome).write_text(json.dumps(list(linhas)), encoding="utf-8")
    return tmp_path


def _por_sigla(partidos):
    return {p["sigla"].upper(): p for p in partidos}


def test_partidos_base_e_sem_partido_sempre_existem(tmp_path):
    partidos = _por_sigla(sp.montar_partidos(_dados(tmp_path)))
    assert {"PT", "PL", "MDB", SEM_PARTIDO.upper()} <= set(partidos)
    assert partidos["PT"]["nome"] == "Partido dos Trabalhadores" and partidos["PT"]["numero"] == 13


def test_sigla_citada_nas_fontes_entra_com_nome_conhecido_ou_generico(tmp_path):
    dados = _dados(
        tmp_path,
        deputados=[{"camara_id": 1, "partido_sigla": "PRB"}],
        senadores=[{"senado_id": 2, "partido_sigla": "ZZZ"}],
        filiacoes=[{"partido_sigla": "yyy"}, {"partido_sigla": None}, {"partido_sigla": 7}],
        presidentes=[{"partido_sigla": "PT"}],  # já é base: não duplica
    )
    partidos = _por_sigla(sp.montar_partidos(dados))
    assert partidos["ZZZ"]["nome"] == "Partido ZZZ" and partidos["YYY"]["nome"] == "Partido yyy"
    assert partidos["PRB"]["sigla"] == "PRB"
    assert [p["sigla"].upper() for p in sp.montar_partidos(dados)].count("PT") == 1


def test_sigla_sem_metadado_curado_fica_sem_ideologia_lema_e_espectro(tmp_path):
    p = _por_sigla(sp.montar_partidos(_dados(tmp_path, deputados=[{"camara_id": 1, "partido_sigla": "ZZZ"}])))["ZZZ"]
    assert (p["espectro"], p["ideologia"], p["lema"], p["numero"], p["logo_url"]) == (
        None,
    ) * 5  # nunca texto inventado


def test_numero_eleitoral_repetido_fica_so_com_o_primeiro(tmp_path, monkeypatch):
    monkeypatch.setattr(sp, "PARTIDOS_BASE", {"AAA": "A", "BBB": "B", "CCC": "C"})
    monkeypatch.setattr(sp, "PARTY_METADATA_MAP", {"AAA": {"numero": 10}, "BBB": {"numero": 10}, "CCC": {"numero": 11}})
    partidos = _por_sigla(sp.montar_partidos(_dados(tmp_path)))
    assert (partidos["AAA"]["numero"], partidos["BBB"]["numero"], partidos["CCC"]["numero"]) == (10, None, 11)


def test_podemos_nao_duplica_o_pode(tmp_path, monkeypatch):
    monkeypatch.setattr(sp, "PARTIDOS_BASE", {"PODE": "Podemos"})
    monkeypatch.setattr(sp, "PARTY_METADATA_MAP", {"PODEMOS": {"numero": 20}, "XYZ": {}})
    dados = _dados(tmp_path, deputados=[{"camara_id": 1, "partido_sigla": "PODEMOS"}])  # a fonte usa o nome antigo
    assert sorted(p["sigla"] for p in sp.montar_partidos(dados)) == ["PODE", "XYZ"]


def test_arquivos_reais_geram_os_36_partidos_da_linha_de_base():
    """A carga antiga a partir do banco vazio criou 36 destes (mais 7 sob demanda nas etapas seguintes)."""
    partidos = sp.montar_partidos(PROCESSED_DATA_DIR)
    assert len(partidos) == len({p["sigla"].upper() for p in partidos}) == 36
    assert all(p["numero"] is None or isinstance(p["numero"], int) for p in partidos)


def test_arquivos_reais_respeitam_as_invariantes_que_nao_dependem_do_retrato_dos_dados():
    """Vale para qualquer atualização dos arquivos (o `== 36` acima é a linha de base e muda com os dados)."""
    partidos = sp.montar_partidos(PROCESSED_DATA_DIR)
    siglas = [p["sigla"].upper() for p in partidos]
    assert len(siglas) == len(set(siglas))  # sem sigla repetida
    assert {s.upper() for s in dp.PARTIDOS_BASE} <= set(siglas)  # os partidos de base nunca somem
    numeros = [p["numero"] for p in partidos if p["numero"] is not None]
    assert len(numeros) == len(set(numeros))  # o número eleitoral é único (a coluna do staging exige)


def test_mapas_curados_usam_chaves_em_maiusculas_e_o_nome_generico_so_sem_curadoria():
    for mapa in (dp.PARTY_SPECTRUM_MAP, dp.PARTY_FULL_NAMES, dp.PARTY_LOGOS_MAP, dp.PARTY_METADATA_MAP):
        assert all(chave == chave.upper() for chave in mapa)
    assert dp.PARTY_SPECTRUM_MAP["PC DO B"] == "ESQUERDA"  # a grafia "PC do B" era descartada na consulta em maiúsculas
    assert dp.nome_do_partido("ptb") == dp.PARTY_FULL_NAMES["PTB"]
    assert dp.nome_do_partido("ZZZ") == "Partido ZZZ"
