"""
Carga de presença da Câmara em `leg.presenca` contra o Postgres de teste (porta 5433, `make test-db-up`).

Cobre o que o parsing dos CSV não alcança: o DELETE por fonte e por ano, a falta inferida (só deputado em exercício, só
de 2003 em diante e só antes do portal), a idempotência e a preservação da história quando a carga é parcial.
"""

import gzip
import json
import os
from collections import Counter
from datetime import date

import pytest

os.environ.setdefault("POSTGRES_PASSWORD", "test_db_password_ci")

from sqlalchemy import text  # noqa: E402

from etl.extractors.camara_presenca_eventos_extractor import caminho_do_arquivo  # noqa: E402
from etl.pipelines import presenca_leg_loader as loader  # noqa: E402

CAB_EVENTOS = '"id";"uri";"urlDocumentoPauta";"dataHoraInicio";"dataHoraFim";"situacao";"descricao";"descricaoTipo";"localExterno";"localCamara.nome";"localCamara.predio";"localCamara.sala";"localCamara.andar"\n'
CAB_PRESENCA = '"idEvento";"uriEvento";"dataHoraInicio";"idDeputado";"uriDeputado"\n'
PLENARIO = "Plenário da Câmara dos Deputados"
FIGURANTES = list(range(5000, 5000 + loader.QUORUM_ABERTURA))  # deputados só para dar quórum às sessões

COM_EXERCICIO, LICENCIADO, EXERCICIO_AUSENTE = 101, 102, 103
SEM_PRESENCA_NO_ANO = 104  # mandato em exercício, mas nenhuma presença em 2005: não recebe falta inferida
D2002, D1, D2, D2021 = date(2002, 5, 7), date(2005, 4, 12), date(2005, 4, 13), date(2021, 4, 13)


@pytest.fixture()
def banco(pg_engine, monkeypatch):
    """Banco limpo, com três deputados cadastrados: em exercício, licenciado e em exercício que comparece em D1."""
    monkeypatch.setattr(loader, "_nome_deputado_api", lambda camara_id: f"Deputado {camara_id}")
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE core.pessoa, core.mandato, leg.presenca RESTART IDENTITY CASCADE"))
        circunscricao = conn.execute(text("SELECT id FROM ref.circunscricao WHERE uf = 'AC'")).scalar()
        cargo = conn.execute(text("SELECT id FROM ref.cargo WHERE codigo = 'DEPUTADO_FEDERAL'")).scalar()
        fonte = conn.execute(text("SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API'")).scalar()
        for camara_id, situacao in (
            (COM_EXERCICIO, "EXERCICIO"),
            (LICENCIADO, "LICENCA"),
            (EXERCICIO_AUSENTE, "EXERCICIO"),
            (SEM_PRESENCA_NO_ANO, "EXERCICIO"),
        ):
            pessoa = conn.execute(
                text("INSERT INTO core.pessoa (nome_exibicao) VALUES (:n) RETURNING id"), {"n": f"Dep {camara_id}"}
            ).scalar()
            conn.execute(
                text(
                    "INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) "
                    "VALUES (:p, :f, 'CAMARA_ID', :v)"
                ),
                {"p": pessoa, "f": fonte, "v": str(camara_id)},
            )
            mandato = conn.execute(
                text(
                    "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio) "
                    "VALUES (:p, :c, :ci, '2003-02-01') RETURNING id"
                ),
                {"p": pessoa, "c": cargo, "ci": circunscricao},
            ).scalar()
            conn.execute(
                text(
                    "INSERT INTO core.mandato_situacao (mandato_id, situacao, periodo) "
                    "VALUES (:m, :s, '[2003-02-01,2008-02-01)')"
                ),
                {"m": mandato, "s": situacao},
            )
    yield pg_engine


def _evento(id_, data, tipo, local):
    return f'"{id_}";"";"";"{data}T15:00:00";"";"Encerrada";"";"{tipo}";"";"{local}";"";"";""\n'


def _presencas(evento, data, deputados):
    return [f'"{evento}";"";"{data}T15:00:00";"{d}";""\n' for d in deputados]


def _gravar(raw, ano, eventos, presencas):
    for recurso, conteudo in (
        ("eventos", CAB_EVENTOS + "".join(eventos)),
        ("eventosPresencaDeputados", CAB_PRESENCA + "".join(presencas)),
    ):
        caminho = caminho_do_arquivo(raw, recurso, ano)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(conteudo, encoding="utf-8-sig")


@pytest.fixture()
def arquivos(tmp_path):
    raw = tmp_path / "raw"
    # 2002: sessão com quórum; o deputado 101 não aparece, mas ainda não há falta inferida antes de 2003
    _gravar(
        raw,
        2002,
        [_evento(1, "2002-05-07", "Sessão Deliberativa", PLENARIO)],
        _presencas(1, "2002-05-07", FIGURANTES),
    )
    # 2005, D1: quórum com 103 presente; 101 só aparece numa reunião de comissão (não conta) -> falta inferida
    # 2005, D2: sessão com quórum e uma segunda, sem quórum, onde só 101 consta -> presente (qualquer sessão do dia)
    _gravar(
        raw,
        2005,
        [
            _evento(10, "2005-04-12", "Sessão Deliberativa", PLENARIO),
            _evento(11, "2005-04-12", "Reunião Deliberativa", "Anexo II, Plenário 01"),
            _evento(20, "2005-04-13", "Sessão Deliberativa", PLENARIO),
            _evento(21, "2005-04-13", "Sessão Deliberativa", PLENARIO),
        ],
        _presencas(10, "2005-04-12", FIGURANTES + [EXERCICIO_AUSENTE])
        + _presencas(11, "2005-04-12", [COM_EXERCICIO])
        + _presencas(20, "2005-04-13", FIGURANTES)
        + _presencas(21, "2005-04-13", [COM_EXERCICIO]),
    )
    # 2021: pertence ao portal da Câmara, não aos arquivos de eventos
    _gravar(
        raw,
        2021,
        [_evento(30, "2021-04-13", "Sessão Deliberativa", PLENARIO)],
        _presencas(30, "2021-04-13", FIGURANTES),
    )
    return raw


@pytest.fixture()
def processed_vazio(tmp_path):
    """Sem arquivo de presença do portal/Senado: a carga mexe só nos arquivos de eventos."""
    pasta = tmp_path / "processed"
    pasta.mkdir()
    return pasta


def _linhas(engine, fonte="CAMARA_CSV"):
    with engine.connect() as conn:
        return conn.execute(
            text(
                """
                SELECT i.valor::int AS camara_id, p.data_sessao, p.tipo_codigo
                FROM leg.presenca p
                JOIN core.pessoa_identificador i ON i.pessoa_id = p.pessoa_id AND i.tipo = 'CAMARA_ID'
                JOIN etl.fonte f ON f.id = p.fonte_id
                WHERE f.codigo = :fonte
                """
            ),
            {"fonte": fonte},
        ).all()


def _tipos(engine):
    return Counter((r.camara_id, r.data_sessao, r.tipo_codigo) for r in _linhas(engine) if r.camara_id < 5000)


def test_falta_inferida_so_para_quem_estava_em_exercicio_e_so_depois_de_2003(banco, arquivos, processed_vazio):
    resumo = loader.carregar(banco, raw_dir=arquivos, processed_dir=processed_vazio, anos_eventos=[2002, 2005, 2021])

    assert resumo["camara_eventos"]["faltas_inferidas"] == 2
    esperado = Counter(
        {
            (EXERCICIO_AUSENTE, D1, "PRESENTE"): 1,
            (COM_EXERCICIO, D1, "AUSENCIA_INFERIDA"): 1,  # a reunião de comissão não conta como presença
            (COM_EXERCICIO, D2, "PRESENTE"): 1,  # esteve numa sessão deliberativa do dia, mesmo sem quórum nela
            (EXERCICIO_AUSENTE, D2, "AUSENCIA_INFERIDA"): 1,
        }
    )
    # o licenciado (102) nunca recebe falta; o presente nunca vira inferida; quem não aparece em nenhum dia do ano (104)
    # tem o mandato fora do plenário (cadastro desatualizado) e não ganha falta inventada
    assert _tipos(banco) == esperado
    anos = {r.data_sessao.year for r in _linhas(banco)}
    assert anos == {2002, 2005}  # 2021 (portal) não vem dos arquivos de eventos
    assert not [r for r in _linhas(banco) if r.data_sessao.year == 2002 and r.tipo_codigo != "PRESENTE"]


def test_carga_e_idempotente_e_cria_os_figurantes_sem_cpf(banco, arquivos, processed_vazio):
    loader.carregar(banco, raw_dir=arquivos, processed_dir=processed_vazio, anos_eventos=[2002, 2005])
    antes = Counter((r.camara_id, r.data_sessao, r.tipo_codigo) for r in _linhas(banco))
    loader.carregar(banco, raw_dir=arquivos, processed_dir=processed_vazio, anos_eventos=[2002, 2005])

    assert Counter((r.camara_id, r.data_sessao, r.tipo_codigo) for r in _linhas(banco)) == antes
    with banco.connect() as conn:
        figurantes = conn.execute(
            text("SELECT count(*) FROM core.pessoa_identificador WHERE tipo = 'CAMARA_ID' AND valor::int >= 5000")
        ).scalar()
        assert figurantes == len(FIGURANTES)


def test_carga_sem_anos_preserva_a_historia_anterior_a_2020(banco, arquivos, processed_vazio):
    loader.carregar(banco, raw_dir=arquivos, processed_dir=processed_vazio, anos_eventos=[2002, 2005])
    antes = Counter((r.camara_id, r.data_sessao, r.tipo_codigo) for r in _linhas(banco))

    loader.carregar(banco, raw_dir=arquivos, processed_dir=processed_vazio, anos_eventos=[])

    assert Counter((r.camara_id, r.data_sessao, r.tipo_codigo) for r in _linhas(banco)) == antes


def test_carga_de_um_ano_nao_apaga_os_outros_anos(banco, arquivos, processed_vazio):
    loader.carregar(banco, raw_dir=arquivos, processed_dir=processed_vazio, anos_eventos=[2002, 2005])
    antes = Counter((r.camara_id, r.data_sessao, r.tipo_codigo) for r in _linhas(banco))

    loader.carregar(banco, raw_dir=arquivos, processed_dir=processed_vazio, anos_eventos=[2005])

    assert Counter((r.camara_id, r.data_sessao, r.tipo_codigo) for r in _linhas(banco)) == antes
    assert any(r.data_sessao == D2002 for r in _linhas(banco))


def test_ano_sem_arquivo_falha_antes_de_alterar_o_banco(banco, arquivos, processed_vazio):
    loader.carregar(banco, raw_dir=arquivos, processed_dir=processed_vazio, anos_eventos=[2002, 2005])
    antes = Counter((r.camara_id, r.data_sessao, r.tipo_codigo) for r in _linhas(banco))

    with pytest.raises(FileNotFoundError, match="2008"):
        loader.carregar(banco, raw_dir=arquivos, processed_dir=processed_vazio, anos_eventos=[2005, 2008])

    assert Counter((r.camara_id, r.data_sessao, r.tipo_codigo) for r in _linhas(banco)) == antes


def test_fonte_oficial_sem_linhas_nao_apaga_a_base(banco, arquivos, tmp_path):
    with banco.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO leg.presenca (pessoa_id, casa_id, data_sessao, tipo_codigo, fonte_id)
                SELECT pi.pessoa_id, c.id, '2023-03-01', 'PRESENTE', f.id
                FROM core.pessoa_identificador pi, ref.casa_legislativa c, etl.fonte f
                WHERE pi.tipo = 'CAMARA_ID' AND pi.valor = '101' AND c.codigo = 'CAMARA_DOS_DEPUTADOS'
                  AND f.codigo = 'CAMARA_PORTAL'
                """
            )
        )
    processed = tmp_path / "processed_incompleto"
    processed.mkdir()
    (processed / "presenca_plenario_dias.json.gz").write_bytes(
        gzip.compress(json.dumps({"camara": [], "senado": [], "senado_partidos": []}).encode())
    )
    (processed / "presenca_plenario_resumo.json").write_text(json.dumps({"resumos": []}), encoding="utf-8")

    resumo = loader.carregar(banco, raw_dir=arquivos, processed_dir=processed, anos_eventos=[])

    assert resumo["camara_portal"] == {"apagados": 0, "inseridos": 0, "lidos": 0}
    assert len(_linhas(banco, "CAMARA_PORTAL")) == 1
