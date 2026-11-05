"""
Carga no banco (Postgres de teste): idempotência, proveniência e resolução inequívoca de pessoas.

Usa o fluxo completo de `CargaCadastro.load_all` (migrações Alembic, cópia dos arquivos para as tabelas planas de `stg` e
fusão em `core`/`leg` pela função SQL `etl.preparar_staging` e as `etl.merge_*`), por isso exige o Postgres de teste
(`make test-db-up`). As conferências leem o resultado em `core` e `leg`: é onde as regras de identificação aparecem.
"""

import gzip
import json
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from etl.extractors.presidents_extractor import PresidentsExtractor  # noqa: E402
from etl.pipelines import carga_cadastro  # noqa: E402


class _Resultado:
    def __init__(self, linhas):
        self.linhas = linhas

    def all(self):
        return self.linhas

    def scalar(self):
        return self.linhas[0][0] if self.linhas else None

    def scalar_one(self):
        assert len(self.linhas) == 1
        return self.linhas[0][0]

    def __iter__(self):
        return iter(self.linhas)


class _Leitor:
    """
    Consultas soltas ao banco de teste, cada uma na sua transação (confirmada na hora). Uma sessão do ORM esquecida aberta
    deixaria a transação pendente e travaria o `DROP SCHEMA` do teste seguinte.
    """

    def __init__(self, engine):
        self.engine = engine

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, comando, parametros=None):
        with self.engine.begin() as conexao:
            resultado = conexao.execute(comando, parametros or {})
            return _Resultado([tuple(linha) for linha in resultado.all()] if resultado.returns_rows else [])

    def commit(self):
        return None


def escrever(dir_, nome, dados):
    (dir_ / nome).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg2://test:test_pass@localhost:5433/legis_test")
    engine = create_engine(url)
    with engine.begin() as conn:
        for schema in ("api", "stg", "fin", "leg", "param", "etl", "eco", "core", "ref", "public"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", url)
    monkeypatch.setattr(carga_cadastro, "SessionLocal", sessionmaker(bind=engine))  # a fusão usa o banco de teste
    monkeypatch.setattr(carga_cadastro, "engine_padrao", engine)
    Sessao = lambda: _Leitor(engine)  # noqa: E731
    Sessao.engine = engine

    dados = tmp_path / "processed"
    dados.mkdir()
    escrever(dados, "presidentes_historico.json", PresidentsExtractor.get_presidents())
    escrever(
        dados,
        "deputados_camara.json",
        [
            # duplicado (como o arquivo legado) + contato real só em um dos registros
            {
                "camara_id": 1,
                "nome_eleitoral": "Eduardo Bolsonaro",
                "nome_civil": "Eduardo Nantes Bolsonaro",
                "partido_sigla": "PL",
                "uf": "SP",
                "id_legislatura": 57,
            },
            {
                "camara_id": 1,
                "nome_eleitoral": "Eduardo Bolsonaro",
                "partido_sigla": "PL",
                "uf": "SP",
                "email": "dep.eduardo@camara.leg.br",
                "gabinete_sala": "Anexo 4, Gabinete 100",
                "uf_nascimento": "RJ",
            },
            {
                "camara_id": 2,
                "nome_eleitoral": "Flávio Dino",
                "nome_civil": "Flávio Dino de Castro e Costa",
                "partido_sigla": "PSB",
                "uf": "MA",
            },
            {"camara_id": 3, "nome_eleitoral": "Dr. Flávio", "partido_sigla": "PTB", "uf": "RJ"},
            {"camara_id": 4, "nome_eleitoral": "Lula da Fonte", "partido_sigla": "PP", "uf": "PE"},
        ],
    )
    escrever(
        dados,
        "senadores_senado.json",
        [
            {
                "senado_id": 100,
                "nome_eleitoral": "Senadora Sem Datas",
                "nome_civil": "Senadora Sem Datas",
                "partido_sigla": "PSD",
                "uf": "MG",
            },
            {
                "senado_id": 101,
                "nome_eleitoral": "Senador Com Datas",
                "nome_civil": "Senador Com Datas",
                "partido_sigla": "PT",
                "uf": "BA",
                "mandato_inicio": "2019-02-01",
                "mandato_fim": "2027-01-31",
            },
        ],
    )
    escrever(
        dados,
        "filiacoes_partidarias.json",
        [
            {
                "politico_nome": "Eduardo Bolsonaro",
                "fonte": "teste",
                "camara_id": 1,
                "partido_sigla": "PSL",
                "data_filiacao": "2018-03-06",
                "data_desfiliacao": "2021-11-29",
                "is_atual": False,
                "motivo_desfiliacao": "MUDANCA_VOLUNTARIA",
            },
            {
                "politico_nome": "Eduardo Bolsonaro",
                "fonte": "teste",
                "camara_id": 1,
                "partido_sigla": "PL",
                "data_filiacao": None,
                "is_atual": True,
            },
            {"politico_nome": "Fulano Sem Id", "partido_sigla": "PL", "data_filiacao": "2020-01-01", "fonte": "teste"},
            {
                "politico_nome": "Flávio Dino",
                "camara_id": 2,
                "partido_sigla": "DEM",
                "data_filiacao": "2018-04-05",
            },  # legado: sem proveniência
        ],
    )
    return dados, Sessao


def carregar(dados, **kwargs):
    return carga_cadastro.CargaCadastro(data_dir=dados, engine=carga_cadastro.engine_padrao, **kwargs).load_all()


def consulta(Sessao, sql, **parametros):
    with Sessao() as s:
        return [tuple(linha) for linha in s.execute(text(sql), parametros).all()]


def escalar(Sessao, sql, **parametros):
    with Sessao() as s:
        return s.execute(text(sql), parametros).scalar()


def pessoa_por(Sessao, tipo, valor):
    """A pessoa de `core` com o identificador oficial: `(id, uid, nome_exibicao, email, sala, telefone, uf_nasc)`."""
    return consulta(
        Sessao,
        "SELECT p.id, p.uid, p.nome_exibicao, p.email, p.gabinete_sala, p.gabinete_telefone, p.uf_nascimento "
        "FROM core.pessoa p JOIN core.pessoa_identificador i ON i.pessoa_id = p.id "
        "WHERE i.tipo = :t AND i.valor = :v",
        t=tipo,
        v=str(valor),
    )


def _estado(Sessao):
    """Contagem das tabelas de domínio que a fusão preenche: se a carga é idempotente, não muda entre duas rodadas."""
    tabelas = (
        "core.pessoa",
        "core.pessoa_nome",
        "core.pessoa_identificador",
        "core.partido",
        "core.filiacao",
        "core.mandato",
        "core.mandato_situacao",
        "leg.proposicao",
        "leg.autoria",
        "leg.votacao",
        "leg.voto",
    )
    return {t: escalar(Sessao, f"SELECT count(*) FROM {t}") for t in tabelas}  # nosec B608 - nomes constantes


def test_politicos_deduplicados_e_sem_contato_inventado(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    assert escalar(Sessao, "SELECT count(*) FROM core.pessoa_identificador WHERE tipo = 'CAMARA_ID'") == 4
    ((_, _, _, email, sala, _, uf_nasc),) = pessoa_por(Sessao, "CAMARA_ID", 1)
    assert email == "dep.eduardo@camara.leg.br"  # vem da fonte
    assert sala == "Anexo 4, Gabinete 100" and uf_nasc == "RJ"
    ((_, _, _, email, sala, telefone, uf_nasc),) = pessoa_por(Sessao, "CAMARA_ID", 2)
    assert email is None and sala is None and telefone is None
    assert uf_nasc is None  # UF eleitoral não é naturalidade


def test_carga_e_idempotente(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    primeira, estado = carregar(dados), None
    estado = _estado(Sessao)
    segunda = carregar(dados)
    assert primeira == segunda
    assert _estado(Sessao) == estado  # a segunda rodada não muda nenhuma linha de core/leg


def test_filiacoes_partidos_extintos_e_data_desconhecida(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    siglas = {r[0] for r in consulta(Sessao, "SELECT sigla FROM core.partido")}
    assert {"PSL", "PTB", "PL"} <= siglas  # extintos viram partidos reais, não "Sem Partido"
    filiacoes = consulta(
        Sessao,
        "SELECT lower(f.periodo), upper_inf(f.periodo) FROM core.filiacao f "
        "JOIN core.pessoa_identificador i ON i.pessoa_id = f.pessoa_id AND i.tipo = 'CAMARA_ID' AND i.valor = '1'",
    )
    assert len(filiacoes) == 2
    (inicio,) = [str(f[0]) for f in filiacoes if f[1]]  # a atual (sem fim)
    assert inicio == "2023-02-01"  # limite inferior de observação, não data real inventada
    assert (
        escalar(Sessao, "SELECT count(*) FROM core.filiacao") == 2
    )  # linha sem id e com nome desconhecido não vira vínculo


def test_mandatos_de_senadores_usam_datas_da_fonte(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    sql = (
        "SELECT m.inicio, m.fim, e.ano FROM core.mandato m JOIN core.pessoa_identificador i ON i.pessoa_id = m.pessoa_id "
        "JOIN core.eleicao e ON e.id = m.eleicao_id WHERE i.tipo = :t AND i.valor = :v AND m.fonte_id IS NOT NULL"
    )
    ((ini, fim, ano),) = consulta(Sessao, sql, t="SENADO_ID", v="101")
    assert (ini.isoformat(), fim.isoformat(), ano) == ("2019-02-01", "2027-01-31", 2018)
    ((_, fim_sem, _),) = consulta(Sessao, sql, t="SENADO_ID", v="100")
    assert fim_sem is None  # sem datas na fonte: não se inventa término em 2031
    ((ini, fim, ano),) = consulta(Sessao, sql, t="CAMARA_ID", v="1")
    assert (ini.isoformat(), fim.isoformat(), ano) == ("2023-02-01", "2027-01-31", 2022)


def proposicoes_e_votacoes(dados):
    escrever(
        dados,
        "proposicoes_2023.json",
        [
            {
                "camara_id": 10,
                "tipo": "PL",
                "numero": 74,
                "ano": 2023,
                "titulo": "PL 74/2023",
                "ementa": "Assunto neutro",
                "autor_nome": "Flávio Dino",
                "autor_fonte": "API",
                "autor_camara_id": None,
                "data_apresentacao": "2023-03-01",
                "url_oficial": None,
            },
            {
                "camara_id": 11,
                "tipo": "PL",
                "numero": 75,
                "ano": 2023,
                "titulo": "PL 75/2023",
                "ementa": "Assunto neutro",
                "autor_nome": "Dr. Flávio, Fulano",
                "autor_fonte": "API",
                "data_apresentacao": None,
            },
            {
                "camara_id": 12,
                "tipo": "PLP",
                "numero": 93,
                "ano": 2023,
                "titulo": "Arcabouço",
                "ementa": "arcabouço fiscal",
                "autor_nome": "Poder Executivo",
                "autor_fonte": "API",
                "iniciativa_executivo": True,
                "data_apresentacao": "2023-04-18",
            },
        ],
    )
    escrever(
        dados,
        "proposicoes_senado.json",
        [
            # mesmo tipo/número/ano de um PL da Câmara, mas é OUTRA proposição (id do Senado distinto)
            {
                "senado_id": 900,
                "tipo": "PL",
                "numero": 74,
                "ano": 2023,
                "titulo": "PL 74/2023 (Senado)",
                "ementa": "Outra coisa",
                "autor_nome": "Senador Com Datas",
                "autor_fonte": "API",
                "data_apresentacao": "2023-05-02",
            },
        ],
    )
    escrever(
        dados,
        "sessoes_votacao_2023.json",
        [
            {
                "sessao_externa_id": "S-CAM-1",
                "proposicao_camara_id": 12,
                "data_hora": "2023-05-10T19:00:00",
                "descricao": "Aprovada",
                "aprovada": True,
            },
            {"sessao_externa_id": "S-ORFA", "proposicao_camara_id": 999, "data_hora": "2023-05-10T19:00:00"},
        ],
    )
    escrever(
        dados,
        "votos_nominais_2023.json",
        [
            {"sessao_externa_id": "S-CAM-1", "deputado_camara_id": 1, "voto": "SIM", "partido_sigla": "PL"},
            {"sessao_externa_id": "S-CAM-1", "deputado_camara_id": 2, "voto": "NAO", "partido_sigla": "PSB"},
            {"sessao_externa_id": "S-CAM-1", "deputado_camara_id": 3, "voto": "ARTIGO_17"},
            {
                "sessao_externa_id": "S-CAM-1",
                "deputado_camara_id": 4,
                "voto": "OPCAO_NOVA",
            },  # antes: KeyError derrubava a carga
        ],
    )
    escrever(
        dados,
        "sessoes_votacao_senado.json",
        [
            {
                "sessao_externa_id": "SEN-1",
                "materia_sigla": "PLP",
                "materia_numero": 93,
                "materia_ano": 2023,
                "data_hora": "2023-06-01T10:00:00",
                "aprovada": True,
            },
            # matéria desconhecida: antes caía em "a primeira proposição qualquer"
            {
                "sessao_externa_id": "SEN-2",
                "materia_sigla": "PL",
                "materia_numero": 5555,
                "materia_ano": 2023,
                "data_hora": "2023-06-02T10:00:00",
            },
            {
                "sessao_externa_id": "SEN-3",
                "materia_sigla": "PLP",
                "materia_numero": 93,
                "materia_ano": 2023,
            },  # sem data
        ],
    )
    escrever(
        dados,
        "votos_nominais_senado.json",
        [
            {"sessao_externa_id": "SEN-1", "senador_id": 101, "voto": "SIM"},
            {"sessao_externa_id": "SEN-1", "senador_id": 100, "voto": "AUSENTE"},
            {"sessao_externa_id": "SEN-2", "senador_id": 101, "voto": "SIM"},
        ],
    )


def _proposicao(Sessao, coluna, valor):
    """`(uid, autor_pessoa_id, autor_nome, eixo_impacto, area_tematica, iniciativa_executivo)` da proposição pelo id da casa."""
    (linha,) = consulta(
        Sessao,
        f"SELECT uid, autor_pessoa_id, autor_nome, eixo_impacto, area_tematica, iniciativa_executivo "  # nosec B608
        f"FROM leg.proposicao WHERE {coluna} = :v",
        v=valor,
    )
    return linha


def test_autoria_exata_e_senado_nao_funde_com_camara(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    dino = pessoa_por(Sessao, "CAMARA_ID", 2)[0][0]
    drflavio = pessoa_por(Sessao, "CAMARA_ID", 3)[0][0]
    p74 = _proposicao(Sessao, "id_camara", 10)
    assert p74[1] == dino  # "Flávio Dino" != "Dr. Flávio"
    # "Dr. Flávio" (1 token após normalização) não pode virar autor por subconjunto de tokens; aqui é igualdade exata
    assert _proposicao(Sessao, "id_camara", 11)[1] == drflavio
    assert _proposicao(Sessao, "id_senado", 900)[0] != p74[0]
    assert escalar(Sessao, "SELECT count(*) FROM leg.proposicao") == 4  # nada foi fundido
    executivo = _proposicao(Sessao, "id_camara", 12)
    assert executivo[1] is None and executivo[2] == "Poder Executivo" and executivo[5]
    assert p74[3] is None and p74[4] is None  # sem eixo aleatório e sem área temática inventada


def test_votacoes_sem_proposicao_unica_sao_descartadas_e_voto_invalido_nao_derruba(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    externos = {r[0] for r in consulta(Sessao, "SELECT id_externo FROM leg.votacao")}
    assert externos == {"S-CAM-1", "SEN-1"}  # órfã, matéria desconhecida e sem data ficaram de fora
    ((sim, nao, votos),) = consulta(
        Sessao,
        "SELECT v.total_sim_fonte, v.total_nao_fonte, (SELECT count(*) FROM leg.voto x WHERE x.votacao_id = v.id) "
        "FROM leg.votacao v WHERE v.id_externo = 'S-CAM-1'",
    )
    assert (sim, nao) == (1, 1)  # recalculado dos votos nominais
    assert votos == 3  # voto "OPCAO_NOVA" ignorado
    (mesma,) = consulta(
        Sessao,
        "SELECT p.id_camara FROM leg.votacao v JOIN leg.proposicao p ON p.id = v.proposicao_id WHERE v.id_externo = 'SEN-1'",
    )[0]
    assert mesma == 12  # a do Senado achou o PLP 93/2023 da Câmara por tipo, número e ano


def test_vinculo_errado_antigo_e_corrigido_na_recarga(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    edu = pessoa_por(Sessao, "CAMARA_ID", 1)[0][0]
    with Sessao() as s:  # vínculo errado como o do caso Eduardo Bolsonaro
        s.execute(text("UPDATE leg.proposicao SET autor_pessoa_id = :p WHERE id_camara = 10"), {"p": edu})
        s.commit()
    carregar(dados)
    dino = pessoa_por(Sessao, "CAMARA_ID", 2)[0][0]
    assert _proposicao(Sessao, "id_camara", 10)[1] == dino


def test_mandato_presidencial_nao_usa_vice_como_coligacao(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    presidenciais = consulta(
        Sessao,
        "SELECT m.coligacao FROM core.mandato m JOIN ref.cargo c ON c.id = m.cargo_id WHERE c.codigo = 'PRESIDENTE'",
    )
    assert presidenciais and all(m[0] is None for m in presidenciais)


def test_autoria_legada_sem_proveniencia_e_ignorada_a_menos_que_autorizada(ambiente):
    dados, Sessao = ambiente
    escrever(
        dados,
        "proposicoes_2023.json",
        [
            # como o arquivo legado: autor sorteado (round-robin) quando a API falhava, sem `autor_fonte`
            {
                "camara_id": 10,
                "tipo": "PL",
                "numero": 1,
                "ano": 2023,
                "titulo": "PL 1/2023",
                "ementa": "x",
                "autor_nome": "Flávio Dino",
                "autor_camara_id": 2,
                "data_apresentacao": "2023-03-01",
            },
            {
                "camara_id": 11,
                "tipo": "MPV",
                "numero": 2,
                "ano": 2023,
                "titulo": "MPV 2/2023",
                "ementa": "x",
                "autor_nome": "Comissão / Parlamentares",
                "iniciativa_executivo": True,
                "data_apresentacao": "2023-03-01",
            },
        ],
    )
    carregar(dados)
    p1 = _proposicao(Sessao, "id_camara", 10)
    assert p1[1] is None and p1[2] is None
    assert (
        _proposicao(Sessao, "id_camara", 11)[2] == "Poder Executivo"
    )  # iniciativa do Executivo é fato curado, não palpite
    carregar(dados, allow_unverified=True)
    dino = pessoa_por(Sessao, "CAMARA_ID", 2)[0][0]
    assert _proposicao(Sessao, "id_camara", 10)[1] == dino


def test_filiacoes_legadas_sem_proveniencia_sao_ignoradas(ambiente):
    dados, Sessao = ambiente
    conta = (
        "SELECT count(*) FROM core.filiacao f JOIN core.pessoa_identificador i ON i.pessoa_id = f.pessoa_id "
        "AND i.tipo = 'CAMARA_ID' AND i.valor = '2'"
    )
    carregar(dados)
    assert escalar(Sessao, conta) == 0
    carregar(dados, allow_unverified=True)
    assert escalar(Sessao, conta) == 1


def test_sessoes_legadas_do_senado_sem_ano_usam_materias_conhecidas(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    escrever(
        dados,
        "sessoes_votacao_senado.json",
        [
            {
                "sessao_externa_id": "SEN-LEG",
                "materia_sigla": "PLP",
                "materia_numero": 93,
                "data_hora": "2023-06-01T10:00:00",
                "aprovada": True,
            },
        ],
    )
    escrever(dados, "votos_nominais_senado.json", [{"sessao_externa_id": "SEN-LEG", "senador_id": 101, "voto": "SIM"}])
    carregar(dados)
    assert escalar(Sessao, "SELECT count(*) FROM leg.votacao WHERE id_externo = 'SEN-LEG'") == 1


def _execucoes(sessao, recurso, estagio="CARREGAR"):
    """As execuções do recurso (do mais antigo ao mais novo): status, estágio, erro, lidas, gravadas, rejeitadas."""
    return (
        sessao()
        .execute(
            text(
                "SELECT e.status, e.estagio, e.erro, e.linhas_lidas, e.linhas_gravadas, e.linhas_rejeitadas "
                "FROM etl.execucao e WHERE e.parametros->>'recurso' = :recurso AND e.estagio = :estagio ORDER BY e.id"
            ),
            {"recurso": recurso, "estagio": estagio},
        )
        .all()
    )


def test_fusao_do_staging_que_falha_sobe_para_a_etapa_nao_aparecer_como_ok(ambiente, monkeypatch):
    """A carga das planas já foi confirmada, mas `core`/`leg` ficaram sem ela: a esteira tem de registrar a falha."""
    dados, Sessao = ambiente

    def quebra(_sessao, **_):
        raise RuntimeError("fusão quebrou")

    carregar(dados)  # aplica as migrações e deixa as planas prontas
    monkeypatch.setattr("app.services.staging_merge.merge_staging", quebra)
    carga = carga_cadastro.CargaCadastro(data_dir=dados, engine=Sessao.engine)
    with pytest.raises(RuntimeError, match="fusão quebrou"):
        carga._fundir_staging()
    (status, _, erro, *_) = _execucoes(Sessao, "cadastro_e_legislativo", "MERGE")[-1]
    assert (status, erro) == ("ERRO", "RuntimeError")  # só a classe da exceção vai para o banco


def test_cada_recurso_registra_a_sua_execucao_e_a_fusao_a_dela(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    for recurso in carga_cadastro.RECURSOS:
        (status, estagio, erro, lidas, gravadas, rejeitadas) = _execucoes(Sessao, recurso)[-1]
        assert (estagio, erro) == ("CARREGAR", None), recurso
        assert lidas == gravadas + rejeitadas, recurso  # as contagens de cada recurso fecham
    (status, *_) = _execucoes(Sessao, "cadastro_e_legislativo", "MERGE")[-1]
    assert status in ("OK", "COM_ALERTA")
    # a fonte, o arquivo de origem e as verificações ficam registrados
    fontes = Sessao().execute(
        text(
            "SELECT f.codigo FROM etl.execucao e JOIN etl.fonte f ON f.id = e.fonte_id "
            "WHERE e.parametros->>'recurso' = 'filiacoes'"
        )
    )
    assert {r[0] for r in fontes} == {"TSE"}
    arquivos = Sessao().execute(
        text("SELECT count(*) FROM etl.arquivo_bruto WHERE caminho LIKE '%presidentes_historico.json'")
    )
    assert arquivos.scalar() >= 1
    verificacoes = Sessao().execute(
        text(
            "SELECT count(*) FROM etl.verificacao v JOIN etl.execucao e ON e.id = v.execucao_id "
            "WHERE e.parametros->>'recurso' = 'politicos'"
        )
    )
    assert verificacoes.scalar() >= 4  # a de contagens e a da cópia de cada tabela plana


def test_recurso_pode_ser_recarregado_sozinho_sem_mudar_o_resto(ambiente):
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    conta = text(
        "SELECT count(*) FROM etl.execucao WHERE parametros->>'recurso' IS NOT NULL"
    )  # as da carga, não as da fusão
    antes = Sessao().execute(conta).scalar()
    estado = _estado(Sessao)
    carga_cadastro.CargaCadastro(data_dir=dados, engine=Sessao.engine).load_all(recursos=["votacoes_plenario"])
    depois = Sessao().execute(conta).scalar()
    assert depois == antes + 2  # só o recurso pedido e a fusão
    assert _estado(Sessao) == estado  # e o resultado é o mesmo: os 5 votos válidos da fixture, sem duplicar
    assert estado["leg.voto"] == 5
    with pytest.raises(ValueError, match="recurso desconhecido"):
        carga_cadastro.CargaCadastro(data_dir=dados, engine=Sessao.engine).load_all(recursos=["nao_existe"])


def test_carga_registra_a_execucao_com_contagens_de_votos(ambiente):
    dados, Sessao = ambiente
    carregar(dados)
    (status, estagio, erro, lidas, gravadas, rejeitadas) = _execucoes(Sessao, "votacoes_plenario")[-1]
    assert (status, estagio, erro) == ("OK", "CARREGAR", None)
    assert (lidas, gravadas, rejeitadas) == (0, 0, 0)  # sem arquivos de votação, as contagens são zero e fecham


def test_carga_que_falha_registra_erro_so_com_a_classe_da_excecao(ambiente, monkeypatch):
    dados, Sessao = ambiente

    def explode(self, cursor, execucao_id):
        raise RuntimeError("detalhe sigiloso: senha=abc")

    monkeypatch.setattr(carga_cadastro.CargaCadastro, "_politicos", explode)
    with pytest.raises(RuntimeError, match="detalhe sigiloso"):  # a exceção sobe inteira; o registro guarda só a classe
        carregar(dados)
    (status, _, erro, *_) = _execucoes(Sessao, "politicos")[-1]
    assert (status, erro) == ("ERRO", "RuntimeError")


def test_votos_da_carga_sao_copiados_inteiros_e_a_fusao_rejeita_com_motivo(ambiente):
    """A carga das planas copia os 7 votos do arquivo; o que não vira `leg.voto` aparece como rejeitado na fusão."""
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    carregar(dados)  # a recarga não duplica: as planas são substituídas e o resultado é o mesmo
    (status, _, _, lidas, gravadas, rejeitadas) = _execucoes(Sessao, "votacoes_plenario")[-1]
    # 4 votos da Câmara (1 com opção desconhecida, que já fica de fora na carga) + 3 do Senado (1 de sessão descartada)
    assert (lidas, gravadas, rejeitadas) == (7, 6, 1) and status == "COM_ALERTA"
    assert escalar(Sessao, "SELECT count(*) FROM leg.voto") == 5  # nenhum duplicado, mesmo recarregando
    motivos = consulta(
        Sessao,
        "SELECT r.motivo, (r.payload->>'total')::int FROM etl.rejeito r JOIN etl.execucao e ON e.id = r.execucao_id "
        "WHERE e.id = (SELECT max(id) FROM etl.execucao WHERE parametros->>'recurso' = 'cadastro_e_legislativo')",
    )
    assert (carga_cadastro.MOTIVO_VOTO, 1) in motivos  # o do Senado cuja sessão foi descartada, em etl.rejeito
    assert ("SEM_PROVENIENCIA", 1) in motivos and ("NAO_CADASTRADO", 1) in motivos  # filiações do arquivo


def test_votos_ja_acumulados_nao_somem_quando_os_arquivos_de_votacao_somem(ambiente):
    """`leg.voto` é refeito a cada fusão; se o arquivo de hoje não traz os votos, os de ontem têm de continuar."""
    dados, Sessao = ambiente
    proposicoes_e_votacoes(dados)
    carregar(dados)
    assert escalar(Sessao, "SELECT count(*) FROM leg.voto") == 5
    for nome in (
        "votos_nominais_2023.json",
        "votos_nominais_senado.json",
        "sessoes_votacao_2023.json",
        "sessoes_votacao_senado.json",
    ):
        (dados / nome).unlink()
    carregar(dados)
    assert escalar(Sessao, "SELECT count(*) FROM leg.voto") == 5
    assert escalar(Sessao, "SELECT count(*) FROM leg.votacao") == 2


def _historico(dados, sessoes_extra=None):
    """Um arquivo anual da Câmara com dois deputados e uma sessão; devolve o caminho."""
    (dados / "votacoes").mkdir(exist_ok=True)
    arquivo = {
        "casa": "CAMARA",
        "ano": 2023,
        "fonte": "teste",
        "is_synthetic": False,
        "partidos": ["PL", "PSB"],
        "parlamentares": {
            "1": {"nome": "Eduardo Bolsonaro", "partido": "PL", "uf": "SP", "legislaturas": [57]},
            "777": {"nome": "Novo Deputado", "partido": "PSB", "uf": "BA", "legislaturas": [56, 57]},
        },
        "sessoes": [
            {
                "id": "H-1",
                "data_hora": "2023-04-01T10:00:00",
                "descricao": "Aprovado",
                "aprovada": True,
                "proposicao": {
                    "camara_id": 500,
                    "tipo": "PL",
                    "numero": 4015,
                    "ano": 2023,
                    "titulo": "PL 4015/2023",
                    "ementa": "x",
                },
                "totais": {"SIM": 1, "NAO": 1},
                "votos": [[1, "SIM", 0], [777, "NAO", 1], [888, "SIM", 0]],
            }
        ]
        + (sessoes_extra or []),
    }
    caminho = dados / "votacoes" / "camara_2023.json.gz"
    caminho.write_bytes(gzip.compress(json.dumps(arquivo).encode()))
    return caminho


def test_historico_cria_parlamentar_proposicao_sessao_e_voto(ambiente):
    dados, Sessao = ambiente
    _historico(dados)
    carregar(dados)
    assert pessoa_por(Sessao, "CAMARA_ID", 777)  # o deputado do arquivo que não existia virou pessoa
    assert not pessoa_por(Sessao, "CAMARA_ID", 888)  # voto de quem o arquivo não lista: sem pessoa, o voto fica de fora
    assert escalar(Sessao, "SELECT count(*) FROM leg.votacao WHERE id_externo = 'H-1'") == 1
    assert escalar(Sessao, "SELECT count(*) FROM leg.voto") == 2
    assert escalar(Sessao, "SELECT count(*) FROM leg.proposicao WHERE id_camara = 500") == 1
    mandatos_777 = consulta(
        Sessao,
        "SELECT e.ano FROM core.mandato m JOIN core.pessoa_identificador i ON i.pessoa_id = m.pessoa_id "
        "AND i.tipo = 'CAMARA_ID' AND i.valor = '777' JOIN core.eleicao e ON e.id = m.eleicao_id ORDER BY 1",
    )
    assert mandatos_777 == [(2018,), (2022,)]  # um mandato por legislatura do arquivo
    (status, _, _, lidas, gravadas, rejeitadas) = _execucoes(Sessao, "votacoes_historico")[-1]
    assert (lidas, gravadas, rejeitadas) == (3, 3, 0)
    carregar(dados)  # idempotente
    assert escalar(Sessao, "SELECT count(*) FROM leg.voto") == 2


def test_mandato_preservado_pela_fusao_aparece_no_log(ambiente, monkeypatch, caplog):
    """A 0038 poupa o mandato que algo ainda referencia: a carga avisa quantos ficaram, para não ser silencioso."""
    dados, Sessao = ambiente
    carregar(dados)
    monkeypatch.setattr("app.services.staging_merge.merge_staging", lambda _sessao, **_: {"rejeitos": 0})
    carga = carga_cadastro.CargaCadastro(data_dir=dados, engine=Sessao.engine)

    monkeypatch.setattr(carga_cadastro.CargaCadastro, "_mandatos_preservados", staticmethod(lambda _s: 2))
    monkeypatch.setattr(carga_cadastro.CargaCadastro, "_verificar_fusao", staticmethod(lambda _s, _e: None))
    with caplog.at_level("WARNING", logger="CargaCadastro"):
        carga._fundir_staging()
    assert any("2 mandatos da fonte LEGADO" in r.message for r in caplog.records)

    caplog.clear()
    monkeypatch.setattr(carga_cadastro.CargaCadastro, "_mandatos_preservados", staticmethod(lambda _s: 0))
    with caplog.at_level("WARNING", logger="CargaCadastro"):
        carga._fundir_staging()
    assert not caplog.records


def test_consulta_de_mandatos_preservados_conta_so_o_mandato_legado_sem_vinculo(ambiente):
    dados, Sessao = ambiente
    carregar(dados)  # aplica as migrações e deixa a fusão normal: nenhum mandato poupado
    with Sessao() as s:
        assert carga_cadastro.CargaCadastro._mandatos_preservados(s) == 0
        fonte = s.execute(text("SELECT id FROM etl.fonte WHERE codigo = 'LEGADO'")).scalar_one()
        pessoa = s.execute(
            text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Zt Preservado') RETURNING id")
        ).scalar()

        def mandato(cargo, inicio, fonte_id, numero=1):
            return s.execute(
                text(
                    "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio, fonte_id, numero_mandato) "
                    "VALUES (:p, (SELECT id FROM ref.cargo WHERE codigo = :c), "
                    "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), :i, :f, :n) RETURNING id"
                ),
                {"p": pessoa, "c": cargo, "i": inicio, "f": fonte_id, "n": numero},
            ).scalar_one()

        vinculado = mandato("DEPUTADO_FEDERAL", "2003-02-01", fonte)
        solto = mandato("SENADOR", "2007-02-01", fonte)
        mandato("SENADOR", "2011-02-01", None, numero=2)  # de outra fonte (ou sem fonte): não é do LEGADO
        ligar = text(
            "INSERT INTO core.mandato_legado (legado_id, tabela, mandato_id) VALUES (gen_random_uuid(), 'mandatos', :m)"
        )
        s.execute(ligar, {"m": vinculado})
        # só o `solto`, da fonte LEGADO e sem vínculo
        assert carga_cadastro.CargaCadastro._mandatos_preservados(s) == 1
        s.execute(ligar, {"m": solto})
        assert carga_cadastro.CargaCadastro._mandatos_preservados(s) == 0  # vinculado, deixa de contar
        s.execute(text("DELETE FROM core.mandato_legado WHERE mandato_id IN (:a, :b)"), {"a": vinculado, "b": solto})
        s.execute(text("DELETE FROM core.mandato WHERE pessoa_id = :p"), {"p": pessoa})
        s.execute(text("DELETE FROM core.pessoa WHERE id = :p"), {"p": pessoa})


def test_arquivo_de_votos_so_com_um_dos_lados_deixa_a_execucao_em_alerta(ambiente):
    """Sessões sem os votos (ou o contrário): o par é ignorado e nenhuma contagem acusa; a execução não pode sair OK."""
    dados, Sessao = ambiente
    escrever(dados, "sessoes_votacao_2023.json", [])  # sem votos_nominais_2023.json
    carregar(dados)
    (status, _, erro, lidas, gravadas, rejeitadas) = _execucoes(Sessao, "votacoes_plenario")[-1]
    assert (lidas, gravadas, rejeitadas) == (0, 0, 0) and erro is None  # as contagens fecham
    assert status == "COM_ALERTA"


def test_historico_ilegivel_deixa_a_execucao_em_alerta(ambiente):
    dados, Sessao = ambiente
    (dados / "votacoes").mkdir()
    (dados / "votacoes" / "camara_2023.json.gz").write_bytes(b"isto nao e gzip")
    carregar(dados)
    (status, *_) = _execucoes(Sessao, "votacoes_historico")[-1]
    assert status == "COM_ALERTA"
