"""Etapa 1 da carga do staging: o montador puro dos partidos e o upsert por COPY em `stg.partidos_politicos`."""

import json
import uuid

import pytest
from sqlalchemy import text

from etl.config import PROCESSED_DATA_DIR
from etl.pipelines import dados_partidos as dp
from etl.pipelines import staging_partidos as sp
from etl.pipelines.loader_helpers import SEM_PARTIDO
from etl.utils import copia


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


PREFIXO = "ZT"  # siglas dos testes, para apagar só o que eles gravam


@pytest.fixture
def staging(pg_engine):
    def limpar():
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM stg.partidos_politicos WHERE sigla LIKE :p"), {"p": PREFIXO + "%"})

    limpar()
    yield pg_engine
    limpar()


def _gravar(engine, partidos):
    with copia.transacao_de_carga(engine) as cursor:
        return sp.gravar_partidos(cursor, partidos)


def _p(sigla, nome="Nome", **extra):
    return {"sigla": sigla, "nome": nome, "espectro": None, "ideologia": None, "lema": None, "numero": None,
            "logo_url": None, **extra}  # fmt: skip


def _linha(engine, sigla):
    with engine.connect() as conn:
        return conn.execute(
            text(
                'SELECT id, sigla, "nomeCompleto", "espectroPolitico"::text AS espectro, ideologia, lema, '
                '"numeroEleitoral" AS numero, "logoUrl" AS logo FROM stg.partidos_politicos WHERE upper(sigla) = upper(:s)'
            ),
            {"s": sigla},
        ).one()


def test_partido_novo_recebe_id_e_o_mapa_traz_a_sigla_e_a_forma_maiuscula(staging):
    mapa = _gravar(staging, [_p("ZTa", "Partido A", espectro="CENTRO", ideologia="Ideia", numero=9991)])

    linha = _linha(staging, "ZTa")
    assert mapa["ZTa"] == mapa["ZTA"] == linha.id and isinstance(mapa["ZTa"], uuid.UUID)
    assert (linha[2], linha.espectro, linha.ideologia, linha.numero) == (
        "Partido A",
        "CENTRO",
        "Ideia",
        9991,
    )


def test_recarga_mantem_o_id_e_nao_duplica(staging):
    primeiro = _gravar(staging, [_p("ZTb")])["ZTb"]
    segundo = _gravar(staging, [_p("ZTb")])["ZTb"]

    assert primeiro == segundo
    with staging.connect() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM stg.partidos_politicos WHERE upper(sigla) = 'ZTB'")).scalar() == 1
        )


def test_sigla_casa_sem_distinguir_maiusculas_e_preserva_a_grafia_original(staging):
    original = _gravar(staging, [_p("ZTc")])["ZTc"]
    mapa = _gravar(staging, [_p("ZTC", ideologia="Nova")])  # outra grafia do mesmo partido, agora com metadado

    assert mapa["ZTC"] == original and _linha(staging, "ZTc").sigla == "ZTc"
    assert _linha(staging, "ZTc").ideologia == "Nova"  # o metadado chegou à linha existente, não a uma duplicata


def test_valor_ausente_nao_apaga_o_que_ja_estava_e_o_nome_nao_muda(staging):
    _gravar(staging, [_p("ZTd", "Nome Antigo", espectro="DIREITA", ideologia="I", lema="L", numero=9992, logo_url="u")])
    _gravar(staging, [_p("ZTd", "Nome Novo")])  # sem metadados

    linha = _linha(staging, "ZTd")
    assert (linha[2], linha.espectro, linha.ideologia, linha.lema, linha.numero, linha.logo) == (
        "Nome Antigo",
        "DIREITA",
        "I",
        "L",
        9992,
        "u",
    )


def test_metadado_novo_atualiza_o_que_ja_estava(staging):
    _gravar(staging, [_p("ZTe", espectro="DIREITA", ideologia="Velha")])
    _gravar(staging, [_p("ZTe", espectro="ESQUERDA", ideologia="Nova")])

    linha = _linha(staging, "ZTe")
    assert (linha.espectro, linha.ideologia) == ("ESQUERDA", "Nova")


def test_numero_que_outro_partido_do_staging_ja_usa_e_descartado(staging):
    _gravar(staging, [_p("ZTf", numero=9993)])
    _gravar(staging, [_p("ZTg", numero=9993)])  # mesmo número, outro partido: não viola a unicidade

    assert _linha(staging, "ZTf").numero == 9993 and _linha(staging, "ZTg").numero is None


def test_recarga_sem_mudanca_nao_toca_a_linha(staging):
    partido = _p("ZTi", espectro="CENTRO", ideologia="I", numero=9994)
    _gravar(staging, [partido])
    with staging.connect() as conn:
        antes = conn.execute(text("SELECT updated_at FROM stg.partidos_politicos WHERE sigla = 'ZTi'")).scalar()

    _gravar(staging, [partido, _p("ZTj")])  # recarga idêntica (e um partido novo na mesma carga)
    _gravar(staging, [_p("ZTi")])  # valor ausente não muda nada
    with staging.connect() as conn:
        depois = conn.execute(text("SELECT updated_at FROM stg.partidos_politicos WHERE sigla = 'ZTi'")).scalar()
    assert depois == antes  # sem UPDATE: nem trava a linha numa recarga idempotente, nem `updated_at` novo

    _gravar(staging, [_p("ZTi", ideologia="Outra")])
    with staging.connect() as conn:
        mudou = conn.execute(text("SELECT updated_at FROM stg.partidos_politicos WHERE sigla = 'ZTi'")).scalar()
    assert mudou > antes  # com mudança real, a linha é atualizada


def test_a_tabela_temporaria_some_com_a_transacao(staging):
    # Na MESMA conexão: tabela temporária é da sessão do Postgres, e numa conexão nova do pool ela nunca apareceria
    conexao = staging.raw_connection()
    try:
        cursor = conexao.cursor()
        sp.gravar_partidos(cursor, [_p("ZTh")])
        cursor.execute("SELECT to_regclass('pg_temp._partido')")
        assert cursor.fetchone()[0] is not None  # existe enquanto a transação não termina
        conexao.commit()
        cursor.execute("SELECT to_regclass('pg_temp._partido')")
        assert cursor.fetchone()[0] is None  # ON COMMIT DROP
    finally:
        conexao.close()


def test_duas_cargas_na_mesma_transacao_reaproveitam_a_tabela_sem_misturar_linhas(staging):
    with copia.transacao_de_carga(staging) as cursor:
        primeiro = sp.gravar_partidos(cursor, [_p("ZTk", numero=9995)])
        segundo = sp.gravar_partidos(cursor, [_p("ZTl")])  # a segunda chamada não reprocessa a linha da primeira
        cursor.execute("SELECT count(*) FROM _partido")
        sobrando = cursor.fetchone()[0]
    assert set(primeiro) == {"ZTk", "ZTK"} and set(segundo) == {"ZTl", "ZTL"}
    assert sobrando == 0
    assert _linha(staging, "ZTk").numero == 9995 and _linha(staging, "ZTl").numero is None
