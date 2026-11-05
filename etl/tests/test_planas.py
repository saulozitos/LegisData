"""
As tabelas planas: o que o Python lê dos arquivos e copia, sem consultar o banco nem decidir identidade. As funções de
conversão são puras e a cópia (`gravar_planas*`) exige o Postgres de teste.
"""

import gzip
import json

import pytest
from sqlalchemy import text

from etl.pipelines import planas_cadastro as pc
from etl.pipelines import planas_proposicoes as pp
from etl.pipelines import planas_votacoes as pv
from etl.utils.copia import transacao_de_carga
from etl.utils.execucao import Contagem


def escrever(pasta, nome, dados):
    (pasta / nome).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


# ── cadastro ───────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("EXPULSAO", "EXPULSAO"),
        ("MOTIVO_QUE_NAO_EXISTE", "MUDANCA_VOLUNTARIA"),
        (None, None),
        (float("nan"), None),
        ("None", None),
        ("", None),
    ],
)
def test_motivo_de_desfiliacao_valido_ou_voluntaria_ou_nulo(bruto, esperado):
    assert pc._motivo(bruto) == esperado


def test_filiacoes_arquivo_ausente_devolve_none_e_id_nan_vira_nulo(tmp_path):
    assert pc.linhas_filiacoes(tmp_path) is None
    escrever(
        tmp_path,
        "filiacoes_partidarias.json",
        [
            {"politico_nome": "Ana", "camara_id": float("nan"), "senado_id": 3, "partido_sigla": "PT", "fonte": "x"},
            {"politico_nome": "Beto", "partido_sigla": "PL", "data_desfiliacao": "2020-01-01", "is_synthetic": True},
        ],
    )
    ana, beto = pc.linhas_filiacoes(tmp_path)
    nomes = pc.COLUNAS_FILIACAO
    ana, beto = dict(zip(nomes, ana)), dict(zip(nomes, beto))
    assert (
        ana["camara_id"] is None and ana["senado_id"] == 3 and ana["is_atual"] == "true" and ana["sintetico"] == "false"
    )
    assert beto["fonte"] is None and beto["sintetico"] == "true"
    assert beto["is_atual"] == "false"  # sem a chave `is_atual`: atual só se não tem desfiliação


def test_datas_do_mandato_de_senador_da_fonte_da_legislatura_ou_o_inicio_da_atual_sem_termino():
    informadas = pc.datas_do_mandato_de_senador({"mandato_inicio": "2019-02-01", "mandato_fim": "2027-01-31"})
    assert [str(informadas[0]), str(informadas[1]), informadas[2], informadas[3]] == [
        "2019-02-01",
        "2027-01-31",
        2018,
        True,
    ]
    legislatura = pc.datas_do_mandato_de_senador({"legislatura_inicio": 56, "legislatura_fim": 57})
    assert [str(legislatura[0]), str(legislatura[1]), legislatura[3]] == ["2019-02-01", "2027-01-31", True]
    sem = pc.datas_do_mandato_de_senador({})
    assert [str(sem[0]), sem[1], sem[2], sem[3]] == ["2023-02-01", None, 2022, False]  # não afirma eleição nem fim


def test_deputados_deduplicados_com_biografia_da_legislatura_e_sem_cpf(tmp_path):
    escrever(
        tmp_path,
        "deputados_camara.json",
        [
            {
                "camara_id": 1,
                "nome_eleitoral": "Ana",
                "partido_sigla": "PT",
                "uf": "SP",
                "id_legislatura": 57,
                "email": "",
            },
            {"camara_id": 1, "nome_eleitoral": "Ana", "partido_sigla": "PT", "uf": "SP", "email": "ana@camara.leg.br"},
            {"camara_id": 2, "nome_eleitoral": "Beto", "partido_sigla": "PL", "uf": "RJ", "cpf": "00000000000"},
        ],
    )
    linhas = [dict(zip(pc.COLUNAS_DEPUTADO, linha)) for linha in pc.linhas_deputados(tmp_path)]
    assert [(d["camara_id"], d["email"]) for d in linhas] == [
        (1, "ana@camara.leg.br"),
        (2, None),
    ]  # o repetido completa
    assert linhas[0]["biografia"] == "Deputado Federal pela UF SP (PT). Legislatura 57."
    assert linhas[1]["biografia"] == "Deputado Federal pela UF RJ (PL)."
    assert all("cpf" not in d for d in linhas)  # nenhum CPF passa daqui (decisão D3)


def test_presidentes_nao_levam_o_cpf_do_arquivo(tmp_path):
    escrever(
        tmp_path,
        "presidentes_historico.json",
        [
            {
                "id_referencia": "x",
                "nome_civil": "A",
                "nome_eleitoral": "A",
                "cpf": "00000000000",
                "mandato_numero": 1,
                "ano_eleicao": 2018,
                "data_inicio": "2019-01-01",
                "status_mandato": "CONCLUIDO",
                "ministros_fazenda_chave": [{"nome": "M", "inicio": "2019-01-01"}],
            }
        ],
    )
    presidentes, ministros = pc.linhas_presidentes(tmp_path)
    assert len(presidentes) == 1 and len(presidentes[0]) == len(pc.COLUNAS_PRESIDENTE)
    assert "00000000000" not in json.dumps(presidentes) and ministros == [["x", "M", "2019-01-01", None]]


# ── proposições ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_autoria_so_vale_com_fonte_a_menos_que_autorizada_e_executivo_e_fato_curado(tmp_path):
    escrever(
        tmp_path,
        "proposicoes_2023.json",
        [
            {"camara_id": 1, "tipo": "PL", "numero": 1, "ano": 2023, "autor_nome": "Ana", "autor_camara_id": 5},
            {"camara_id": 2, "tipo": "PL", "numero": 2, "ano": 2023, "autor_nome": "Ana", "autor_fonte": "API"},
            {"camara_id": 3, "tipo": "MPV", "numero": 3, "ano": 2023, "iniciativa_executivo": True},
            {"tipo": "PL", "numero": 4, "ano": 2023},
        ],
    )
    contagem = Contagem()
    sem, ignorados = pp.linhas_camara(tmp_path, False, contagem)
    campos = {d["camara_id"]: d for d in (dict(zip(pp.COLUNAS_CAMARA, linha)) for linha in sem)}
    assert (campos[1]["autor_nome"], campos[1]["autor_camara_id"]) == (None, None) and ignorados == 2
    assert campos[2]["autor_nome"] == "Ana" and campos[3]["autor_nome"] == "Poder Executivo"
    assert (contagem.lidas, contagem.gravadas, contagem.motivos) == (4, 3, {"SEM_ID": 1})
    com, _ = pp.linhas_camara(tmp_path, True, Contagem())
    assert {d[0]: d[10] for d in com}[1] == "Ana"  # --allow-unverified: a autoria do arquivo legado entra


def test_proposicao_do_senado_rejeita_formato_legado_e_sem_id(tmp_path):
    escrever(
        tmp_path,
        "proposicoes_senado.json",
        [123, {"senado_id": 9, "tipo": "pl", "numero": 1, "ano": 2020, "ementa": ""}, {"tipo": "PL"}],
    )
    contagem = Contagem()
    linhas, _ = pp.linhas_senado(tmp_path, False, contagem)
    assert contagem.motivos == {"FORMATO_LEGADO": 1, "SEM_ID": 1} and len(linhas) == 1
    registro = dict(zip(pp.COLUNAS_SENADO, linhas[0]))
    assert registro["tipo"] == "PL" and registro["ementa"] == "Sem ementa disponível"
    assert registro["url_oficial"].endswith("/9")


# ── votações ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_sessao_historica_com_tipo_nao_suportado_nao_e_valida_e_o_resultado_vem_do_arquivo():
    base = {"id": "V1", "data_hora": "2023-03-01T19:00:00", "descricao": "Aprovada a matéria.", "totais": {"SIM": 3}}
    boa = dict(
        zip(
            pv.COLUNAS_SESSAO_HISTORICO,
            pv._linha_de_sessao(
                {**base, "proposicao": {"camara_id": 1, "tipo": "PL", "numero": 4, "ano": 2023}}, pv.CAMARA
            ),
        )
    )
    assert boa["prop_valida"] == "true" and boa["total_sim"] == 3 and boa["prop_titulo"] == "PL 4/2023"
    assert boa["titulo_pauta"] == "Votação sobre matéria"
    ruim = dict(
        zip(
            pv.COLUNAS_SESSAO_HISTORICO,
            pv._linha_de_sessao({**base, "proposicao": {"tipo": "REQ", "numero": 4, "ano": 2023}}, pv.CAMARA),
        )
    )
    assert ruim["prop_valida"] == "false" and ruim["prop_tipo"] is None


def test_par_incompleto_de_sessoes_e_votos_do_plenario_nao_entra_e_conta_o_arquivo_ignorado(tmp_path, pg_engine):
    escrever(tmp_path, "sessoes_votacao_2023.json", [])  # sem votos_nominais_2023.json
    with transacao_de_carga(pg_engine) as cursor:
        votos = pv.gravar_planas_plenario(cursor, tmp_path, 1)
    assert votos.arquivos_ignorados == 1 and votos.lidas == 0


def test_ex_parlamentares_suplente_sem_voto_e_sem_id_sao_rejeitados(tmp_path):
    escrever(
        tmp_path,
        pv.ARQUIVO_HISTORICOS,
        {
            "fonte": "oficial",
            "is_synthetic": False,
            "deputados": [
                {"camara_id": 7, "nome_eleitoral": "Ex Dep", "partido_sigla": "PSL", "legislaturas": [56]},
                {"nome_eleitoral": "Sem Id"},
            ],
            "senadores": [
                {
                    "senado_id": 9,
                    "nome_eleitoral": "Titular",
                    "mandatos": [{"inicio": "2019-02-01", "participacao": "Titular"}],
                },
                {
                    "senado_id": 10,
                    "nome_eleitoral": "Suplente",
                    "mandatos": [{"inicio": "2019-02-01", "participacao": "1º Suplente"}],
                },
            ],
        },
    )
    contagem = Contagem()
    linhas = pv.linhas_parlamentares_anteriores(tmp_path, contagem)
    assert [dict(zip(pv.COLUNAS_PARLAMENTAR, linha))["ext_id"] for linha in linhas] == [7, 9]
    assert (contagem.lidas, contagem.gravadas, contagem.motivos) == (4, 2, {"SEM_ID": 1, "SUPLENTE_SEM_VOTO": 1})


def test_ex_parlamentares_sem_proveniencia_nao_entram(tmp_path):
    assert pv.linhas_parlamentares_anteriores(tmp_path, Contagem()) is None
    escrever(tmp_path, pv.ARQUIVO_HISTORICOS, {"deputados": []})
    assert pv.linhas_parlamentares_anteriores(tmp_path, Contagem()) is None


# ── cópia para o banco ─────────────────────────────────────────────────────────────────────────────────────────────
def test_cada_carga_substitui_a_plana_e_numera_as_linhas_com_a_execucao(tmp_path, pg_engine):
    escrever(
        tmp_path,
        "deputados_camara.json",
        [{"camara_id": 1, "nome_eleitoral": "Ana"}, {"camara_id": 2, "nome_eleitoral": "Beto"}],
    )
    escrever(tmp_path, "senadores_senado.json", [])
    escrever(tmp_path, "presidentes_historico.json", [])
    with transacao_de_carga(pg_engine) as cursor:
        assert pc.gravar_planas(cursor, tmp_path, 41, "politicos")["stg.camara_deputado"] == 2
    escrever(tmp_path, "deputados_camara.json", [{"camara_id": 3, "nome_eleitoral": "Carla", "email": ""}])
    with transacao_de_carga(pg_engine) as cursor:
        pc.gravar_planas(cursor, tmp_path, 42, "politicos")
    with pg_engine.connect() as conexao:
        linhas = conexao.execute(text("SELECT execucao_id, linha, camara_id, email FROM stg.camara_deputado")).all()
    assert [tuple(linha) for linha in linhas] == [
        (42, 1, 3, None)
    ]  # só a última carga; vazio é nulo, nunca texto vazio


def test_recurso_sem_tabela_plana_e_recusado(tmp_path, pg_engine):
    with transacao_de_carga(pg_engine) as cursor, pytest.raises(ValueError, match="sem tabela plana"):
        pc.gravar_planas(cursor, tmp_path, 1, "mandatos")


def test_historico_anual_copia_sessoes_votos_e_parlamentares_e_pula_arquivo_sem_proveniencia(tmp_path, pg_engine):
    pasta = tmp_path / "votacoes"
    pasta.mkdir()
    bom = {
        "fonte": "oficial",
        "is_synthetic": False,
        "partidos": ["PT"],
        "parlamentares": {"1": {"nome": "Ana", "partido": "PT", "legislaturas": [57]}},
        "sessoes": [
            {"id": "V1", "data_hora": "2023-03-01T19:00:00", "proposicao": {"camara_id": 9, "tipo": "PL", "numero": 1, "ano": 2023},
             "totais": {}, "votos": [[1, "SIM", 0], [1, "NAO_EXISTE", 0]]},
        ],
    }  # fmt: skip
    (pasta / "camara_2023.json.gz").write_bytes(gzip.compress(json.dumps(bom).encode()))
    (pasta / "camara_2024.json.gz").write_bytes(gzip.compress(json.dumps({**bom, "fonte": None}).encode()))
    (pasta / "senado_2023.json.gz").write_bytes(b"isto nao e gzip")
    with transacao_de_carga(pg_engine) as cursor:
        votos = pv.gravar_planas_historico(cursor, tmp_path, 7)
    # 2 lidos, 1 de opção desconhecida (rejeitado já na carga) e 2 arquivos pulados: o sem fonte e o ilegível
    assert (votos.lidas, votos.gravadas, votos.rejeitadas, votos.arquivos_ignorados) == (2, 1, 1, 2)
    with pg_engine.connect() as conexao:
        opcoes = conexao.execute(text("SELECT opcao FROM stg.historico_voto ORDER BY linha")).scalars().all()
    assert opcoes == ["SIM"]


def test_votos_sao_cumulativos_e_o_primeiro_de_cada_par_vale(pg_engine):
    with transacao_de_carga(pg_engine) as cursor:
        cursor.execute("TRUNCATE stg.historico_voto")
        pv.acumular_votos(
            cursor,
            1,
            [["CAMARA", "V1", 5, "SIM", "PT"], ["CAMARA", "V1", 6, "NAO", None], ["CAMARA", "V1", 5, "NAO", "PL"]],
        )
        pv.acumular_votos(
            cursor, 2, [["CAMARA", "V1", 5, "ABSTENCAO", "PT"], ["SENADO", "V1", 5, "SIM", None]]
        )  # o par de V1/5 já existe
    with pg_engine.connect() as conexao:
        linhas = conexao.execute(
            text("SELECT execucao_id, casa, parlamentar_ext_id, opcao FROM stg.historico_voto ORDER BY 1, 2, 3")
        ).all()
    assert [tuple(linha) for linha in linhas] == [
        (1, "CAMARA", 5, "SIM"),
        (1, "CAMARA", 6, "NAO"),
        (2, "SENADO", 5, "SIM"),
    ]


def test_plenario_acumula_so_voto_com_parlamentar_e_opcao_validos(tmp_path, pg_engine):
    escrever(
        tmp_path,
        "sessoes_votacao_2023.json",
        [{"sessao_externa_id": "S1", "proposicao_camara_id": 1, "data_hora": "2023-05-10T19:00:00"}],
    )
    escrever(
        tmp_path,
        "votos_nominais_2023.json",
        [
            {"sessao_externa_id": "S1", "deputado_camara_id": 1, "voto": "SIM", "partido_sigla": "PT"},
            {"sessao_externa_id": "S1", "deputado_camara_id": 2, "voto": "OPCAO_NOVA"},
            {"sessao_externa_id": "S1", "deputado_camara_id": None, "voto": "SIM"},
        ],
    )
    with transacao_de_carga(pg_engine) as cursor:
        cursor.execute("TRUNCATE stg.historico_voto")
        votos = pv.gravar_planas_plenario(cursor, tmp_path, 3)
    assert (votos.lidas, votos.gravadas, votos.rejeitadas) == (3, 1, 2)
    with pg_engine.connect() as conexao:
        assert [
            tuple(r)
            for r in conexao.execute(
                text("SELECT casa, sessao_ext_id, parlamentar_ext_id, opcao, partido FROM stg.historico_voto")
            )
        ] == [("CAMARA", "S1", 1, "SIM", "PT")]
