"""
As funções SQL que resolvem o staging (`etl.preparar_staging` e as que ela chama), sobre linhas inseridas à mão nas tabelas
planas. Cada teste roda numa transação que é desfeita no fim e começa com `core`/`leg` e as planas vazias; as conferências
leem as tabelas de trabalho (`w_*`), que existem até o fim da transação. O fluxo ponta a ponta, com a fusão em `core`/`leg`,
está em `test_carga_cadastro`. Exige o Postgres de teste (`make test-db-up`).
"""

import itertools
import json
from contextlib import contextmanager

from sqlalchemy import text

from etl.utils.names import normalize_name_tokens

PLANAS = (
    "curadoria_partido",
    "curadoria_partido_conhecido",
    "curadoria_presidente",
    "curadoria_ministro_fazenda",
    "camara_deputado",
    "senado_senador",
    "tse_filiacao",
    "camara_proposicao_api",
    "senado_proposicao_api",
    "camara_sessao_plenario",
    "camara_voto_plenario",
    "senado_sessao_plenario",
    "senado_voto_plenario",
    "historico_parlamentar",
    "historico_partido",
    "historico_sessao",
    "historico_voto",
)
_linha = itertools.count(1)


@contextmanager
def transacao(pg_engine):
    """Uma transação sobre bancos vazios (planas e domínio); tudo é desfeito ao sair."""
    conexao = pg_engine.connect()
    corrente = conexao.begin()
    try:
        conexao.execute(text("TRUNCATE " + ", ".join(f"stg.{t}" for t in PLANAS)))
        conexao.execute(
            text(
                "TRUNCATE core.pessoa, core.partido, core.midia, leg.proposicao, leg.votacao, etl.rejeito "
                "RESTART IDENTITY CASCADE"
            )
        )
        yield conexao
    finally:
        corrente.rollback()
        conexao.close()


def inserir(conexao, tabela, *linhas):
    for dados in linhas:
        dados = {"linha": next(_linha), **dados}
        colunas = ", ".join(f'"{c}"' for c in dados)
        marcas = ", ".join(f":{c}" for c in dados)
        conexao.execute(text(f"INSERT INTO stg.{tabela} ({colunas}) VALUES ({marcas})"), dados)  # nosec B608


def partido_curado(conexao, *siglas):
    inserir(conexao, "curadoria_partido", *({"sigla": s, "nome": f"Partido {s}"} for s in siglas))


def preparar(conexao, sintetico=False, nao_verificado=False):
    return conexao.execute(
        text("SELECT etl.preparar_staging(:s, :n)"), {"s": sintetico, "n": nao_verificado}
    ).scalar_one()


def consulta(conexao, sql, **parametros):
    return [tuple(linha) for linha in conexao.execute(text(sql), parametros).all()]


def deputado(camara_id, nome, **extra):
    return {
        "camara_id": camara_id,
        "nome_eleitoral": nome,
        "nome_civil": nome,
        "partido_sigla": "PT",
        "uf": "SP",
        **extra,
    }


# ── nome normalizado: o SQL tem de dar o mesmo resultado que o Python ──────────────────────────────────────────────
NOMES = [
    "Flávio Dino",
    "Dr. Flávio",
    "Senador Humberto Costa (PT/PE)",
    "Deputada Professora Dorinha Seabra",
    "JOÃO DA SILVA [Suplente]",
    "Pastor Gil Diniz, Padre João",
    "Capitão Alberto Neto",
    "  espaços   extras  ",
    "Maria-José D'Ávila",
    "Çedilha & Ñandú",
    "",
    None,
]


def test_nome_tokens_do_sql_igual_ao_do_python(pg_engine):
    with transacao(pg_engine) as c:
        for nome in NOMES:
            esperado = normalize_name_tokens(nome)
            obtido = c.execute(text("SELECT etl.nome_tokens(:n)"), {"n": nome}).scalar()
            assert obtido == esperado, nome


def test_nome_conjunto_ignora_ordem_e_repeticao(pg_engine):
    with transacao(pg_engine) as c:
        assert c.execute(text("SELECT etl.nome_conjunto('silva joao silva')")).scalar() == "joao silva"
        assert c.execute(text("SELECT etl.nome_conjunto('joao silva')")).scalar() == "joao silva"
        assert c.execute(text("SELECT etl.nome_conjunto('')")).scalar() == ""


# ── partidos ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_partido_curado_entra_e_numero_que_outro_partido_ja_usa_e_descartado(pg_engine):
    with transacao(pg_engine) as c:
        c.execute(text("INSERT INTO core.partido (sigla, nome, numero_eleitoral) VALUES ('CCC', 'Ccc', 11)"))
        inserir(
            c,
            "curadoria_partido",
            {"sigla": "AAA", "nome": "A", "numero": 10, "espectro": "CENTRO"},
            {"sigla": "DDD", "nome": "D", "numero": 11},  # o 11 é do CCC, que já está em core
        )
        preparar(c)
        linhas = consulta(c, 'SELECT sigla, "numeroEleitoral", "espectroPolitico"::text FROM w_partidos ORDER BY sigla')
    assert linhas == [("AAA", 10, "CENTRO"), ("DDD", None, None)]


def test_sigla_desconhecida_vira_partido_com_nome_generico_e_a_conhecida_leva_o_nome_curado(pg_engine):
    with transacao(pg_engine) as c:
        inserir(
            c,
            "curadoria_partido_conhecido",
            {"sigla_maiuscula": "PTB", "nome": "Partido Trabalhista Brasileiro", "espectro": "CENTRO_DIREITA"},
        )
        partido_curado(c, "S.PART.")
        preparar(c)
        criado_ptb = c.execute(text("SELECT etl.garantir_partido('ptb')")).scalar()
        criado_zzz = c.execute(text("SELECT etl.garantir_partido('ZZZ')")).scalar()
        repetido = c.execute(text("SELECT etl.garantir_partido('zzz')")).scalar()
        linhas = dict(consulta(c, 'SELECT sigla, "nomeCompleto" FROM w_partidos'))
    assert criado_zzz == repetido and criado_ptb != criado_zzz  # a segunda chamada acha a que a primeira criou
    assert linhas["ptb"] == "Partido Trabalhista Brasileiro" and linhas["ZZZ"] == "Partido ZZZ"


def test_partido_ja_em_core_e_achado_pela_sigla_sem_criar_outro(pg_engine):
    with transacao(pg_engine) as c:
        uid = c.execute(text("INSERT INTO core.partido (sigla, nome) VALUES ('XPTO', 'Xpto') RETURNING uid")).scalar()
        partido_curado(c, "S.PART.")
        preparar(c)
        achado = c.execute(text("SELECT etl.partido_id('xpto')")).scalar()
        criado = c.execute(text("SELECT etl.garantir_partido('xpto')")).scalar()
    assert achado == uid == criado


# ── políticos ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_deputado_novo_vira_politico_e_o_repetido_nao_duplica(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        inserir(c, "camara_deputado", deputado(1, "Ana"), deputado(2, "Beto"))
        preparar(c)
        preparar(c)  # idempotente dentro da transação: recomeça do zero e dá o mesmo resultado
        assert consulta(c, 'SELECT "camaraId", "nomeEleitoral" FROM w_politicos ORDER BY 1') == [
            (1, "Ana"),
            (2, "Beto"),
        ]


def test_pessoa_ja_cadastrada_pelo_id_oficial_nao_vira_duplicata_e_mantem_o_uid(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        (pid, uid) = c.execute(
            text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Ana Antiga') RETURNING id, uid")
        ).one()
        c.execute(
            text(
                "INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) "
                "VALUES (:p, (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API'), 'CAMARA_ID', '1')"
            ),
            {"p": pid},
        )
        inserir(c, "camara_deputado", deputado(1, "Ana Nova"))
        preparar(c)
        linhas = consulta(c, 'SELECT id::text, "nomeEleitoral" FROM w_politicos WHERE "camaraId" = 1')
    assert linhas == [(str(uid), "Ana Antiga")]  # o mesmo uid; o nome do cadastro só muda na fusão


def test_contato_inventado_e_limpo_e_o_real_so_entra_onde_estava_vazio(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        (pid,) = c.execute(
            text(
                "INSERT INTO core.pessoa (nome_exibicao, email, gabinete_sala, gabinete_telefone) VALUES "
                "('Ana', 'dep.7@camara.leg.br', 'Anexo IV, Gabinete 123', '(61) 3215-5123') RETURNING id"
            )
        ).one()
        c.execute(
            text(
                "INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) "
                "VALUES (:p, (SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API'), 'CAMARA_ID', '7')"
            ),
            {"p": pid},
        )
        c.execute(
            text(
                "INSERT INTO core.pessoa_nome (pessoa_id, tipo, nome, fonte_id) VALUES "
                "(:p, 'CIVIL', 'Ana', (SELECT id FROM etl.fonte WHERE codigo = 'LEGADO'))"
            ),
            {"p": pid},
        )
        inserir(c, "camara_deputado", deputado(7, "Ana", email="ana@camara.leg.br"))
        preparar(c)
        (email, sala, telefone) = consulta(
            c, 'SELECT email, "gabineteSala", "gabineteTelefone" FROM w_politicos WHERE "camaraId" = 7'
        )[0]
    assert email == "ana@camara.leg.br" and sala is None and telefone is None


def test_presidente_com_dois_mandatos_e_uma_pessoa_so(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "MDB", "S.PART.")
        base = {"nome_civil": "Luiz Inácio Lula da Silva", "nome_eleitoral": "Lula", "partido_sigla": "PT",
                "status_mandato": "CONCLUIDO", "biografia": "x"}  # fmt: skip
        inserir(
            c,
            "curadoria_presidente",
            {
                **base,
                "id_referencia": "lula-2003",
                "mandato_numero": 1,
                "ano_eleicao": 2002,
                "data_inicio": "2003-01-01",
                "data_fim": "2006-12-31",
            },
            {
                **base,
                "id_referencia": "lula-2007",
                "mandato_numero": 2,
                "ano_eleicao": 2006,
                "data_inicio": "2007-01-01",
                "data_fim": "2010-12-31",
            },
        )
        inserir(
            c, "curadoria_ministro_fazenda", {"id_referencia": "lula-2003", "nome": "Palocci", "inicio": "2003-01-01"}
        )
        preparar(c)
        assert consulta(c, "SELECT count(*) FROM w_politicos") == [(1,)]
        assert consulta(c, 'SELECT "anoEleicao", "numeroMandato", cargo::text FROM w_mandatos ORDER BY 1') == [
            (2002, 1, "PRESIDENTE"),
            (2006, 2, "PRESIDENTE"),
        ]
        assert consulta(c, 'SELECT "nomeOcupante", "ministerioNome" FROM w_gabinete') == [
            ("Palocci", "Ministério da Fazenda")
        ]


# ── filiações ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _fil(**extra):
    return {"politico_nome": "Ana", "camara_id": 1, "partido_sigla": "PT", "fonte": "teste", "sintetico": False,
            "is_atual": True, **extra}  # fmt: skip


def test_filiacao_sem_fonte_sintetica_ou_sem_pessoa_e_rejeitada_com_motivo(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        inserir(c, "camara_deputado", deputado(1, "Ana"))
        inserir(
            c,
            "tse_filiacao",
            _fil(data_filiacao="2020-01-01"),
            _fil(data_filiacao="2019-01-01", fonte=None),
            _fil(data_filiacao="2018-01-01", sintetico=True),
            _fil(data_filiacao="2017-01-01", camara_id=None, politico_nome="Fulano Que Ninguém Conhece"),
        )
        rejeitos = preparar(c)["rejeitos"]
        assert consulta(c, 'SELECT "dataFiliacao"::text FROM w_filiacoes') == [("2020-01-01",)]
        liberado = preparar(c, sintetico=True, nao_verificado=True)["rejeitos"]
    assert (rejeitos["SEM_PROVENIENCIA"], rejeitos["SINTETICO"], rejeitos["NAO_CADASTRADO"]) == (1, 1, 1)
    assert (liberado["SEM_PROVENIENCIA"], liberado["SINTETICO"]) == (0, 0)


def test_filiacao_sem_data_usa_o_inicio_da_legislatura_e_a_repetida_conta_uma_vez(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        inserir(c, "camara_deputado", deputado(1, "Ana"))
        inserir(c, "tse_filiacao", _fil(data_filiacao=None), _fil(data_filiacao=None))
        preparar(c)
        assert consulta(c, 'SELECT "dataFiliacao"::text, "isAtual" FROM w_filiacoes') == [("2023-02-01", True)]


def test_pessoa_achada_pelo_nome_so_quando_o_nome_e_unico(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        inserir(c, "camara_deputado", deputado(1, "João Silva"), deputado(2, "Maria Souza"), deputado(3, "Maria Souza"))
        inserir(
            c,
            "tse_filiacao",
            _fil(politico_nome="Joao Silva", camara_id=None, data_filiacao="2020-01-01"),
            _fil(politico_nome="Maria Souza", camara_id=None, data_filiacao="2020-01-01"),
        )
        rejeitos = preparar(c)["rejeitos"]
        nomes = consulta(c, 'SELECT p."nomeEleitoral" FROM w_filiacoes f JOIN w_politicos p ON p.id = f."politicoId"')
    assert nomes == [("João Silva",)] and rejeitos["NAO_CADASTRADO"] == 1  # homônimo nunca se atribui por palpite


# ── mandatos ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_mandato_de_deputado_segue_a_legislatura_e_nao_duplica(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        inserir(c, "camara_deputado", deputado(1, "Ana", id_legislatura=56), deputado(2, "Beto"))
        preparar(c)
        linhas = consulta(
            c,
            'SELECT p."camaraId", m."dataInicio"::text, m."dataFim"::text, m."anoEleicao", m.status::text '
            'FROM w_mandatos m JOIN w_politicos p ON p.id = m."politicoId" ORDER BY 1',
        )
    assert linhas == [
        (1, "2019-02-01", "2023-01-31", 2018, "TITULAR_ATIVO"),
        (2, "2023-02-01", "2027-01-31", 2022, "TITULAR_ATIVO"),
    ]


def test_senador_sem_datas_na_fonte_nao_ganha_termino_e_com_datas_corrige_o_mandato(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        sem = {"nome_eleitoral": "Sem Datas", "nome_civil": "Sem Datas", "partido_sigla": "PT", "uf": "MG",
               "mandato_inicio": "2023-02-01", "ano_eleicao": 2022, "datas_informadas": False}  # fmt: skip
        com = {"nome_eleitoral": "Com Datas", "nome_civil": "Com Datas", "partido_sigla": "PT", "uf": "BA",
               "mandato_inicio": "2019-02-01", "mandato_fim": "2027-01-31", "ano_eleicao": 2018, "datas_informadas": True}  # fmt: skip
        inserir(c, "senado_senador", {"senado_id": 1, **sem}, {"senado_id": 2, **com})
        preparar(c)
        linhas = consulta(
            c,
            'SELECT p."senadoId", m."dataFim"::text, m."anoEleicao" FROM w_mandatos m JOIN w_politicos p ON p.id = m."politicoId" ORDER BY 1',
        )
        assert linhas == [(1, None, 2022), (2, "2027-01-31", 2018)]
        # a fonte passa a informar as datas do primeiro: o mandato que já existe é corrigido, não recriado
        c.execute(
            text(
                "UPDATE stg.senado_senador SET mandato_fim = '2031-01-31', datas_informadas = true WHERE senado_id = 1"
            )
        )
        preparar(c)
        assert consulta(c, "SELECT count(*) FROM w_mandatos WHERE cargo::text = 'SENADOR'") == [(2,)]


# ── proposições e autor ────────────────────────────────────────────────────────────────────────────────────────────
def _prop(camara_id, numero, **extra):
    return {"camara_id": camara_id, "tipo": "PL", "numero": numero, "ano": 2023, "titulo": f"PL {numero}/2023",
            "ementa": "x", "reforma_estrutural": False, "iniciativa_executivo": False, **extra}  # fmt: skip


def test_autor_por_id_nome_exato_normalizado_e_conjunto_so_quando_unico(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        inserir(
            c,
            "camara_deputado",
            deputado(1, "Flávio Dino", nome_civil="Flávio Dino de Castro e Costa"),
            deputado(2, "Dr. Flávio"),
            deputado(3, "Ana Souza"),
            deputado(4, "Ana Souza"),
            deputado(5, "Lúcia Maria Prado"),
        )
        inserir(
            c,
            "camara_proposicao_api",
            _prop(10, 1, autor_nome="Flávio Dino"),
            _prop(11, 2, autor_nome="Dr. Flávio, Fulano"),
            _prop(12, 3, autor_nome="Ana Souza"),  # homônimo: ninguém
            _prop(13, 4, autor_nome="Qualquer Um", autor_camara_id=1),  # o id oficial vale mais que o nome
            _prop(14, 5, autor_nome="Prado Lúcia Maria"),  # mesmo conjunto de palavras
            _prop(15, 6, autor_nome="Poder Executivo"),
        )
        preparar(c)
        autores = dict(
            consulta(
                c,
                'SELECT pr."idExternoCamara", p."nomeEleitoral" FROM w_proposicoes pr LEFT JOIN w_politicos p ON p.id = pr."autorPoliticoId"',
            )
        )
    assert autores == {
        10: "Flávio Dino",
        11: "Dr. Flávio",
        12: None,
        13: "Flávio Dino",
        14: "Lúcia Maria Prado",
        15: None,
    }


def test_proposicao_da_camara_e_do_senado_com_mesmo_numero_sao_proposicoes_diferentes(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "S.PART.")
        inserir(c, "camara_proposicao_api", _prop(10, 74))
        inserir(
            c,
            "senado_proposicao_api",
            {"senado_id": 900, "tipo": "PL", "numero": 74, "ano": 2023, "titulo": "t", "ementa": "e"},
        )
        preparar(c)
        assert consulta(c, "SELECT count(*) FROM w_proposicoes") == [(2,)]


def test_proposicao_de_outra_carga_entra_pelo_id_com_o_uid_que_ja_tem(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "S.PART.")
        uid = c.execute(
            text(
                "INSERT INTO leg.proposicao (id_camara, tipo_codigo, numero, ano, titulo, data_apresentacao, status_codigo) "
                "VALUES (10, 'PL', 74, 2023, 'PL 74/2023', DATE '2023-03-01', 'EM_TRAMITACAO') RETURNING uid"
            )
        ).scalar()
        inserir(c, "camara_proposicao_api", _prop(10, 74, area_tematica="Saúde"))
        preparar(c)
        linhas = consulta(c, 'SELECT id::text, "areaTematica" FROM w_proposicoes')
    assert linhas == [(str(uid), "Saúde")]  # o contrato público (uid) não muda; só o enriquecimento entra


# ── votações do plenário ───────────────────────────────────────────────────────────────────────────────────────────
def _plenario(c):
    partido_curado(c, "PT", "S.PART.")
    inserir(c, "camara_deputado", deputado(1, "Ana"), deputado(2, "Beto"))
    inserir(c, "camara_proposicao_api", _prop(10, 74))
    inserir(
        c,
        "camara_sessao_plenario",
        {"sessao_externa_id": "S1", "proposicao_camara_id": 10, "data_hora": "2023-05-10T19:00:00Z", "titulo_pauta": "Pauta",
         "aprovada": True, "total_sim": 99, "total_nao": 99, "total_abstencao": 0, "total_obstrucao": 0},
        {"sessao_externa_id": "ORFA", "proposicao_camara_id": 999, "data_hora": "2023-05-10T19:00:00Z", "titulo_pauta": "x",
         "total_sim": 0, "total_nao": 0, "total_abstencao": 0, "total_obstrucao": 0},
    )  # fmt: skip
    inserir(
        c,
        "camara_voto_plenario",
        {"sessao_externa_id": "S1", "deputado_camara_id": 1, "partido_sigla": "PT", "voto": "SIM"},
        {"sessao_externa_id": "S1", "deputado_camara_id": 2, "partido_sigla": "PT", "voto": "NAO"},
        {"sessao_externa_id": "S1", "deputado_camara_id": 1, "voto": "NAO"},  # repetido: vale o primeiro
        {"sessao_externa_id": "S1", "deputado_camara_id": 2, "voto": "OPCAO_NOVA"},  # opção desconhecida
        {"sessao_externa_id": "S1", "deputado_camara_id": 777, "voto": "SIM"},  # sem político
    )
    # o que o carregador acumula em `historico_voto`: só opção válida, e o primeiro voto de cada par (sessão, parlamentar)
    inserir(
        c,
        "historico_voto",
        {"casa": "CAMARA", "sessao_ext_id": "S1", "parlamentar_ext_id": 1, "opcao": "SIM", "partido": "PT"},
        {"casa": "CAMARA", "sessao_ext_id": "S1", "parlamentar_ext_id": 2, "opcao": "NAO", "partido": "PT"},
        {"casa": "CAMARA", "sessao_ext_id": "S1", "parlamentar_ext_id": 777, "opcao": "SIM", "partido": None},
    )


def test_plenario_recalcula_totais_dos_votos_descarta_sessao_sem_proposicao_e_conta_o_rejeitado(pg_engine):
    with transacao(pg_engine) as c:
        _plenario(c)
        resumo = preparar(c)
        sessoes = consulta(c, 'SELECT "idExterno", "totalSim", "totalNao" FROM w_sessoes')
        votos = consulta(
            c, 'SELECT p."camaraId", v.voto::text FROM w_votos v JOIN w_politicos p ON p.id = v."politicoId" ORDER BY 1'
        )
    # recalculado dos votos nominais do arquivo (todos eles, como antes), não os 99 do cabeçalho da sessão
    assert sessoes == [("S1", 2, 2)]
    assert votos == [(1, "SIM"), (2, "NAO")]
    assert resumo["plenario"]["sessoes_descartadas"] == 1
    assert resumo["votos_lidos"] == 3 and resumo["rejeitos"]["SEM_SESSAO_POLITICO_OU_OPCAO"] == 1  # o do deputado 777


def test_plenario_do_senado_acha_a_proposicao_por_tipo_numero_e_ano_exatos(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        inserir(c, "senado_senador", {"senado_id": 7, "nome_eleitoral": "Sen", "nome_civil": "Sen", "partido_sigla": "PT", "uf": "BA",
                                      "mandato_inicio": "2019-02-01", "ano_eleicao": 2018, "datas_informadas": True})  # fmt: skip
        inserir(c, "camara_proposicao_api", _prop(10, 93, tipo="PLP"))
        inserir(
            c,
            "senado_sessao_plenario",
            {"sessao_externa_id": "SEN-1", "materia_sigla": "PLP", "materia_numero": 93, "materia_ano": 2023,
             "data_hora": "2023-06-01T10:00:00Z", "titulo_pauta": "p", "total_sim": 0, "total_nao": 0, "total_abstencao": 0, "total_obstrucao": 0},
            {"sessao_externa_id": "SEN-2", "materia_sigla": "PL", "materia_numero": 5555, "materia_ano": 2023,
             "data_hora": "2023-06-02T10:00:00Z", "titulo_pauta": "p", "total_sim": 0, "total_nao": 0, "total_abstencao": 0, "total_obstrucao": 0},
        )  # fmt: skip
        inserir(c, "senado_voto_plenario", {"sessao_externa_id": "SEN-1", "senador_id": 7, "voto": "SIM"})
        preparar(c)
        assert consulta(c, 'SELECT "idExterno", "casaLegislativa"::text FROM w_sessoes') == [
            ("SEN-1", "SENADO_FEDERAL")
        ]


# ── histórico ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _sessao_historica(**extra):
    base = {"casa": "CAMARA", "ext_id": "V1", "data_hora": "2023-03-01T19:00:00Z", "titulo_pauta": "Votação sobre PL 100/2023",
            "aprovada": True, "secreta": False, "total_sim": 1, "total_nao": 1, "total_abstencao": 0, "total_obstrucao": 0,
            "prop_valida": True, "prop_camara_id": 1000, "prop_tipo": "PL", "prop_numero": 100, "prop_ano": 2023,
            "prop_titulo": "PL 100/2023", "prop_ementa": "x", "prop_status": "EM_TRAMITACAO", **extra}  # fmt: skip
    return base


def _parlamentar(ext_id, nome, **extra):
    return {"origem": "VOTACOES", "casa": "CAMARA", "ext_id": ext_id, "nome": nome, "partido": "PT", "uf": "SP",
            "biografia": "b", "legislaturas": json.dumps([56, 57]), **extra}  # fmt: skip


def test_historico_cria_parlamentar_proposicao_sessao_voto_e_mandatos_por_legislatura(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        inserir(c, "historico_partido", {"sigla": "PT"}, {"sigla": "NOVO"})
        inserir(
            c,
            "historico_parlamentar",
            _parlamentar(1, "Ana Dep"),
            _parlamentar(2, "Beto Dep", legislaturas=json.dumps([57])),
        )
        inserir(
            c,
            "historico_sessao",
            _sessao_historica(),
            _sessao_historica(ext_id="V2", prop_tipo=None, prop_valida=False),
        )
        inserir(
            c,
            "historico_voto",
            {"casa": "CAMARA", "sessao_ext_id": "V1", "parlamentar_ext_id": 1, "opcao": "SIM", "partido": "PT"},
            {"casa": "CAMARA", "sessao_ext_id": "V1", "parlamentar_ext_id": 2, "opcao": "NAO", "partido": "NOVO"},
            {"casa": "CAMARA", "sessao_ext_id": "V1", "parlamentar_ext_id": 99, "opcao": "SIM", "partido": "PT"},
            {"casa": "CAMARA", "sessao_ext_id": "V2", "parlamentar_ext_id": 1, "opcao": "SIM", "partido": "PT"},
        )
        resumo = preparar(c)["historico"]
        assert (
            resumo["sessoes_novas"],
            resumo["sessoes_descartadas"],
            resumo["proposicoes_criadas"],
        ) == (1, 1, 1)
        assert consulta(c, "SELECT count(*) FROM w_politicos") == [(2,)]
        assert consulta(c, "SELECT sigla FROM w_partidos WHERE sigla = 'NOVO'") == [
            ("NOVO",)
        ]  # criado mesmo sem curadoria
        anos = consulta(
            c,
            'SELECT p."camaraId", m."anoEleicao", m.status::text FROM w_mandatos m JOIN w_politicos p ON p.id = m."politicoId" ORDER BY 1, 2',
        )
        # a legislatura 56 terminou em 2023-01-31 (concluída); a 57 segue ativa
        assert anos == [(1, 2018, "CONCLUIDO"), (1, 2022, "TITULAR_ATIVO"), (2, 2022, "TITULAR_ATIVO")]
        votantes = consulta(
            c, 'SELECT p."camaraId", v.voto::text FROM w_votos v JOIN w_politicos p ON p.id = v."politicoId" ORDER BY 1'
        )
        assert votantes == [
            (1, "SIM"),
            (2, "NAO"),
        ]  # o 99 não está na lista de parlamentares: sem pessoa, o voto fica de fora


def test_historico_vincula_por_nome_unico_quem_ja_existe_com_outro_id(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        inserir(c, "senado_senador", {"senado_id": 50, "nome_eleitoral": "Beto Dep", "nome_civil": "Beto Dep",
                                      "partido_sigla": "PT", "uf": "BA", "mandato_inicio": "2019-02-01", "ano_eleicao": 2018,
                                      "datas_informadas": True})  # fmt: skip
        inserir(c, "historico_parlamentar", _parlamentar(2, "Beto Dep", legislaturas=json.dumps([57])))
        inserir(c, "historico_sessao", _sessao_historica())
        resumo = preparar(c)["historico"]
        assert consulta(c, 'SELECT "camaraId", "senadoId" FROM w_politicos') == [
            (2, 50)
        ]  # a mesma pessoa, agora com os dois ids
    assert resumo["sessoes_novas"] == 1


def test_historico_liga_proposicao_do_senado_a_da_camara_so_com_numeracao_unica_a_partir_de_2019(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        inserir(c, "camara_proposicao_api", _prop(1000, 100))
        inserir(
            c,
            "historico_sessao",
            _sessao_historica(casa="SENADO", ext_id="SEN-10", prop_camara_id=None, prop_senado_id=777),
            _sessao_historica(casa="SENADO", ext_id="SEN-11", prop_camara_id=None, prop_senado_id=888, prop_ano=2015,
                              prop_titulo="PL 100/2015"),  # fmt: skip
        )
        preparar(c)
        props = consulta(c, 'SELECT "idExternoCamara", "idExternoSenado", ano FROM w_proposicoes ORDER BY ano, 1')
    # a de 2023 ganha o id do Senado; a de 2015 NÃO é fundida com outra de mesmo número
    assert props == [(None, 888, 2015), (1000, 777, 2023)]


def test_sessao_de_outra_casa_com_o_mesmo_codigo_e_descartada(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        inserir(c, "historico_parlamentar", _parlamentar(1, "Ana Dep"))
        inserir(c, "historico_sessao", _sessao_historica())
        preparar(c)
        c.execute(text("UPDATE stg.historico_sessao SET casa = 'SENADO', prop_senado_id = 5, prop_camara_id = NULL"))
        # a sessão "V1" agora é do Senado, mas já existe como da Câmara em w_sessoes (semeada): é descartada
        c.execute(
            text(
                'INSERT INTO w_sessoes (id, "idExterno", "proposicaoId", "casaLegislativa", "dataHoraVotacao", "tituloPauta", "isVotacaoSecreta", aprovada, "totalSim", "totalNao", "totalAbstencao", "totalObstrucao") SELECT gen_random_uuid(), \'V1\', id, \'CAMARA_DOS_DEPUTADOS\', now(), \'t\', false, true, 0, 0, 0, 0 FROM w_proposicoes LIMIT 1'
            )
        )
        resumo = c.execute(text("SELECT etl.preparar_votacoes_historico()")).scalar()
    assert resumo["sessoes_descartadas"] == 1


def test_ex_senador_suplente_ganha_mandato_de_suplente_e_o_titular_o_de_senador(pg_engine):
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        suplente = json.dumps(
            [{"uf": "SP", "inicio": "2019-02-01", "fim": "2023-01-31", "participacao": "1º Suplente"}]
        )
        titular = json.dumps([{"uf": "BA", "inicio": "2019-02-01", "fim": "2027-01-31", "participacao": "Titular"}])
        base = {"origem": "LEGISLATURAS_ANTERIORES", "casa": "SENADO", "partido": "PT", "biografia": "b"}
        inserir(
            c,
            "historico_parlamentar",
            {**base, "ext_id": 11, "nome": "Suplente Votante", "mandatos": suplente},
            {**base, "ext_id": 9, "nome": "Sen Titular", "mandatos": titular},
        )
        resumo = preparar(c)["anteriores"]
        linhas = consulta(
            c,
            'SELECT p."senadoId", m.status::text, m."ufJurisdicao", m."anoEleicao" FROM w_mandatos m '
            'JOIN w_politicos p ON p.id = m."politicoId" ORDER BY 1',
        )
    assert resumo == {"politicos_criados": 2, "politicos_vinculados": 0, "mandatos_criados": 2}
    assert linhas == [(9, "TITULAR_ATIVO", "BA", 2018), (11, "SUPLENTE_EM_EXERCICIO", "SP", 2018)]


def test_votos_acumulados_sobrevivem_a_uma_carga_sem_arquivos_de_sessao(pg_engine):
    """`leg.voto` é refeito a cada fusão: o voto já acumulado entra de novo mesmo sem a sessão estar nos arquivos de hoje."""
    with transacao(pg_engine) as c:
        partido_curado(c, "PT", "S.PART.")
        inserir(c, "camara_deputado", deputado(1, "Ana"))
        inserir(c, "camara_proposicao_api", _prop(10, 74))
        c.execute(text("INSERT INTO leg.proposicao (uid, id_camara, tipo_codigo, numero, ano, titulo, data_apresentacao, status_codigo, fonte_id) VALUES (gen_random_uuid(), 10, 'PL', 74, 2023, 't', DATE '2023-03-01', 'EM_TRAMITACAO', (SELECT id FROM etl.fonte WHERE codigo = 'LEGADO'))"))  # fmt: skip
        c.execute(text("INSERT INTO leg.votacao (uid, id_externo, proposicao_id, casa_id, data_hora, tipo_deliberacao, aprovada, fonte_id) SELECT gen_random_uuid(), 'S1', p.id, (SELECT id FROM ref.casa_legislativa WHERE codigo = 'CAMARA_DOS_DEPUTADOS'), now(), 'NOMINAL', true, p.fonte_id FROM leg.proposicao p"))  # fmt: skip
        c.execute(text("INSERT INTO leg.votacao_legado (legado_id, tabela, votacao_id) SELECT gen_random_uuid(), 'sessoes_votacao', id FROM leg.votacao"))  # fmt: skip
        inserir(
            c,
            "historico_voto",
            {"casa": "CAMARA", "sessao_ext_id": "S1", "parlamentar_ext_id": 1, "opcao": "SIM", "partido": "PT"},
        )
        # nenhuma sessão nas planas de hoje: a da fusão anterior vem de leg.votacao_legado
        preparar(c)
        assert consulta(c, 'SELECT v.voto::text FROM w_votos v JOIN w_sessoes s ON s.id = v."sessaoVotacaoId"') == [
            ("SIM",)
        ]
