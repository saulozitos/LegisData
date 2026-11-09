"""
A carga direta (`etl.carga`): arquivo -> `core`/`leg`, sem staging. Cada teste monta uma pasta de dados pequena, roda a carga
no Postgres de teste e confere o banco; rodar duas vezes não pode mudar nenhuma contagem (idempotência) nem duplicar pessoa.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import pytest
from sqlalchemy import text

from etl.carga.base import Resultado, avancar_corte, data_de_corte, rodar
from etl.carga.orquestra import Carga
from etl.utils.execucao import Contagem

TABELAS = "core.pessoa, core.partido, core.midia, core.eleicao, leg.proposicao, leg.votacao, etl.corte, etl.rejeito"  # CASCADE leva mandato, filiação, autoria, voto, orientação...


@pytest.fixture()
def banco(pg_engine):
    def limpar():
        with pg_engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {TABELAS} RESTART IDENTITY CASCADE"))

    limpar()
    yield pg_engine
    limpar()


def escrever(pasta: Path, nome: str, dados: Any) -> None:
    caminho = pasta / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados), encoding="utf-8")


def consulta(engine, sql: str, **parametros) -> List[tuple]:
    with engine.connect() as conn:
        return [tuple(linha) for linha in conn.execute(text(sql), parametros).all()]


def deputado(camara_id: int, nome: str, **extra) -> Dict[str, Any]:
    return {
        "camara_id": camara_id,
        "nome_eleitoral": nome,
        "nome_civil": nome.upper(),
        "partido_sigla": "PT",
        "uf": "SP",
        "id_legislatura": 57,
        "foto_url": f"https://exemplo/{camara_id}.jpg",
        **extra,
    }


def senador(senado_id: int, nome: str, **extra) -> Dict[str, Any]:
    return {
        "senado_id": senado_id,
        "nome_eleitoral": nome,
        "nome_civil": nome,
        "partido_sigla": "PSD",
        "uf": "MG",
        "mandato_inicio": "2019-02-01",
        "mandato_fim": "2027-01-31",
        **extra,
    }


def carga(engine, pasta: Path, **kw) -> Carga:
    return Carga(engine=engine, data_dir=pasta, **kw)


# ── partidos ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_partidos_do_catalogo_e_sigla_desconhecida_entra_fora_do_catalogo(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana", partido_sigla="XYZW")])
    carga(banco, tmp_path).carregar(["partidos"])
    assert consulta(banco, "SELECT catalogo, nome FROM core.partido WHERE sigla = 'PT'")[0][0] is True
    assert consulta(banco, "SELECT catalogo, nome FROM core.partido WHERE sigla = 'XYZW'") == [(False, "XYZW")]
    antes = consulta(banco, "SELECT count(*) FROM core.partido")
    carga(banco, tmp_path).carregar(["partidos"])
    assert consulta(banco, "SELECT count(*) FROM core.partido") == antes


# ── pessoas ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_pessoa_nova_pelo_id_oficial_e_rodar_de_novo_nao_duplica_nem_muda_o_uid(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana"), deputado(2, "Beto")])
    escrever(tmp_path, "senadores_senado.json", [senador(9, "Carla")])
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    uids = consulta(banco, "SELECT uid::text, nome_exibicao FROM core.pessoa ORDER BY nome_exibicao")
    assert [n for _, n in uids] == ["Ana", "Beto", "Carla"]
    assert consulta(banco, "SELECT tipo, valor FROM core.pessoa_identificador ORDER BY valor") == [
        ("CAMARA_ID", "1"),
        ("CAMARA_ID", "2"),
        ("SENADO_ID", "9"),
    ]
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT uid::text, nome_exibicao FROM core.pessoa ORDER BY nome_exibicao") == uids


def test_mesmo_nome_civil_e_mesmo_nascimento_e_uma_pessoa_so_com_os_dois_ids(banco, tmp_path):
    """Quem foi deputado e depois senador: nome civil completo + data de nascimento iguais = a mesma pessoa."""
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana Souza", data_nascimento="1970-05-01")])
    escrever(
        tmp_path,
        "senadores_senado.json",
        [senador(9, "Ana Souza", nome_civil="ANA SOUZA", data_nascimento="1970-05-01")],
    )
    for _ in range(2):  # a segunda carga não cria nem une mais nada
        carga(banco, tmp_path).carregar(["partidos", "pessoas"])
        assert consulta(banco, "SELECT count(*) FROM core.pessoa") == [(1,)]
    assert consulta(banco, "SELECT tipo, valor FROM core.pessoa_identificador ORDER BY tipo") == [
        ("CAMARA_ID", "1"),
        ("SENADO_ID", "9"),
    ]
    assert consulta(banco, "SELECT count(DISTINCT m.cargo_id) FROM core.mandato m") == [
        (2,)
    ]  # os dois cargos na mesma pessoa
    assert consulta(banco, "SELECT count(*) FROM core.pessoa_candidata_duplicidade") == [(0,)]


def test_mesmo_cpf_hmac_une_a_pessoa_mesmo_com_nome_e_nascimento_diferentes_e_nenhum_cpf_e_gravado(banco, tmp_path):
    h = "ab" * 32  # HMAC já calculado pelo extrator; o carregador nunca vê o CPF
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana Souza", data_nascimento="1970-05-01")])
    escrever(tmp_path, "senadores_senado.json", [senador(9, "Ana de Souza Lima", nome_civil="ANA DE SOUZA LIMA")])
    escrever(
        tmp_path,
        "cpf_identificadores.json",
        [
            {"id_tipo": "CAMARA_ID", "id_valor": "1", "cpf_hmac": h, "origem": "CAMARA_API"},
            {"id_tipo": "SENADO_ID", "id_valor": "9", "cpf_hmac": h, "origem": "TSE"},
        ],
    )
    for _ in range(2):
        carga(banco, tmp_path).carregar(["partidos", "pessoas"])
        assert consulta(banco, "SELECT count(*) FROM core.pessoa") == [(1,)]
    assert consulta(banco, "SELECT tipo FROM core.pessoa_identificador ORDER BY tipo, fonte_id") == [
        ("CAMARA_ID",),
        ("CPF_HMAC",),
        ("CPF_HMAC",),
        ("SENADO_ID",),
    ]  # o mesmo HMAC por duas fontes (Câmara e TSE), cada uma com a sua linha
    assert consulta(banco, "SELECT count(DISTINCT valor) FROM core.pessoa_identificador WHERE tipo = 'CPF_HMAC'") == [
        (1,)
    ]


def test_cpf_hmac_ja_gravado_liga_o_id_novo_a_pessoa_existente(banco, tmp_path):
    h = "cd" * 32
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana Souza")])
    escrever(
        tmp_path,
        "cpf_identificadores.json",
        [{"id_tipo": "CAMARA_ID", "id_valor": "1", "cpf_hmac": h, "origem": "TSE"}],
    )
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana Souza")])
    escrever(tmp_path, "senadores_senado.json", [senador(9, "Outro Nome Qualquer")])
    escrever(
        tmp_path,
        "cpf_identificadores.json",
        [
            {"id_tipo": "CAMARA_ID", "id_valor": "1", "cpf_hmac": h, "origem": "TSE"},
            {"id_tipo": "SENADO_ID", "id_valor": "9", "cpf_hmac": h, "origem": "TSE"},
        ],
    )
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT count(*) FROM core.pessoa") == [(1,)]


def test_nascimento_que_chega_depois_une_as_duas_pessoas_ja_gravadas(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana Souza", data_nascimento="1970-05-01")])
    escrever(tmp_path, "senadores_senado.json", [senador(9, "Ana Souza", nome_civil="ANA SOUZA")])  # sem nascimento
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT count(*) FROM core.pessoa") == [(2,)]
    escrever(
        tmp_path,
        "senadores_senado.json",
        [senador(9, "Ana Souza", nome_civil="ANA SOUZA", data_nascimento="1970-05-01")],
    )
    for _ in range(2):
        carga(banco, tmp_path).carregar(["partidos", "pessoas"])
        assert consulta(banco, "SELECT count(*) FROM core.pessoa") == [(1,)]
    assert consulta(banco, "SELECT count(*) FROM core.pessoa_identificador") == [(2,)]
    assert consulta(banco, "SELECT count(*) FROM core.mandato") == [(2,)]


def test_homonimo_de_outra_data_de_nascimento_ou_sem_data_nao_se_une_e_vira_candidata(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana Souza", data_nascimento="1970-05-01")])
    escrever(tmp_path, "senadores_senado.json", [senador(9, "Ana Souza", nome_civil="ANA SOUZA")])  # sem nascimento
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT count(*) FROM core.pessoa") == [(2,)]
    assert consulta(banco, "SELECT motivo FROM core.pessoa_candidata_duplicidade") == [("NOME_NORMALIZADO_IGUAL",)]
    escrever(
        tmp_path,
        "senadores_senado.json",
        [senador(9, "Ana Souza", nome_civil="ANA SOUZA", data_nascimento="1980-01-01")],
    )
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT count(*) FROM core.pessoa") == [(2,)]


def test_a_fonte_atual_corrige_o_dado_e_a_historica_so_preenche_o_vazio(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana", email="velho@camara.leg.br")])
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana", email="novo@camara.leg.br")])
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT email FROM core.pessoa") == [("novo@camara.leg.br",)]
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana")])  # sem e-mail: não apaga o que já está
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT email FROM core.pessoa") == [("novo@camara.leg.br",)]


def test_mandato_de_senador_segue_o_arquivo_e_sem_data_de_inicio_nao_ha_mandato(banco, tmp_path):
    sem_data = senador(10, "Sem Data")
    sem_data.pop("mandato_inicio")
    sem_data.pop("mandato_fim")
    escrever(tmp_path, "senadores_senado.json", [senador(9, "Carla"), sem_data])
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(
        banco,
        "SELECT pe.nome_exibicao, m.inicio::text, m.fim::text, m.condicao, e.ano FROM core.mandato m "
        "JOIN core.pessoa pe ON pe.id = m.pessoa_id JOIN core.eleicao e ON e.id = m.eleicao_id",
    ) == [("Carla", "2019-02-01", "2027-01-31", "TITULAR", 2018)]
    # a data do arquivo muda: o mandato do senador é corrigido, não duplicado
    escrever(tmp_path, "senadores_senado.json", [senador(9, "Carla", mandato_fim="2026-12-31")])
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT fim::text FROM core.mandato") == [("2026-12-31",)]


def test_mandato_de_deputado_nao_sobrescreve_o_que_o_historico_da_camara_gravou(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana")])
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    with banco.begin() as conn:  # o histórico por deputado refinou o fim do mandato
        conn.execute(text("UPDATE core.mandato SET fim = '2024-06-30', motivo_encerramento = 'RENUNCIA'"))
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT fim::text, motivo_encerramento FROM core.mandato") == [("2024-06-30", "RENUNCIA")]


def test_deputado_sem_uf_tem_mandato_rejeitado_com_motivo_e_nao_inventa_circunscricao(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana", uf=None)])
    resultado = carga(banco, tmp_path).carregar(["partidos", "pessoas"])["pessoas"]
    assert consulta(banco, "SELECT count(*) FROM core.mandato") == [(0,)]
    assert resultado.contagem.motivos == {"MANDATO_SEM_UF": 1}
    assert (resultado.contagem.lidas, resultado.contagem.gravadas, resultado.contagem.rejeitadas) == (1, 0, 1)


def _fhc() -> List[Dict[str, Any]]:
    """Os dois mandatos de FHC no arquivo curado, com o mesmo ministro da Fazenda nos dois."""
    presidente = {
        "id_referencia": "fhc-1995",
        "nome_civil": "Fernando Henrique Cardoso",
        "nome_eleitoral": "Fernando Henrique Cardoso",
        "cpf": "00000000000",
        "partido_sigla": "PSDB",
        "mandato_numero": 1,
        "ano_eleicao": 1994,
        "data_inicio": "1995-01-01",
        "data_fim": "1999-01-01",
        "status_mandato": "CONCLUIDO",
        "rotulo_mandato": "FHC 1",
        "ministros_fazenda_chave": [{"nome": "Pedro Malan", "inicio": "1995-01-01", "fim": "1998-12-31"}],
    }
    segundo = {
        **presidente,
        "id_referencia": "fhc-1999",
        "mandato_numero": 2,
        "ano_eleicao": 1998,
        "data_inicio": "1999-01-01",
        "data_fim": "2003-01-01",
        "rotulo_mandato": "FHC 2",
        "ministros_fazenda_chave": [{"nome": "Pedro Malan", "inicio": "1999-01-01", "fim": "2002-12-31"}],
    }
    return [presidente, segundo]


def test_presidente_e_ministro_da_fazenda_sao_pessoas_curadas_e_o_ministro_aponta_para_o_mandato_do_presidente(
    banco, tmp_path
):
    escrever(tmp_path, "presidentes_historico.json", _fhc())
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT count(*) FROM core.pessoa WHERE nome_exibicao = 'Fernando Henrique Cardoso'") == [
        (1,)
    ]
    assert consulta(
        banco,
        "SELECT c.codigo, m.numero_mandato, m.condicao FROM core.mandato m JOIN ref.cargo c ON c.id = m.cargo_id "
        "WHERE c.codigo = 'PRESIDENTE' ORDER BY m.numero_mandato",
    ) == [("PRESIDENTE", 1, "TITULAR"), ("PRESIDENTE", 2, "TITULAR")]
    assert consulta(
        banco,
        "SELECT pe.nome_exibicao, m.orgao_nome, m.funcao_destaque, pm.numero_mandato FROM core.mandato m "
        "JOIN core.pessoa pe ON pe.id = m.pessoa_id JOIN core.mandato pm ON pm.id = m.nomeado_por_mandato_id "
        "WHERE m.condicao = 'NOMEADO' ORDER BY pm.numero_mandato",
    ) == [
        ("Pedro Malan", "Ministério da Fazenda", "ECONOMIA", 1),
        ("Pedro Malan", "Ministério da Fazenda", "ECONOMIA", 2),
    ]  # o mesmo ministro nos dois mandatos é uma pessoa só, com dois mandatos NOMEADO, cada um ligado ao seu presidente
    assert consulta(banco, "SELECT count(*) FROM core.pessoa WHERE nome_exibicao = 'Pedro Malan'") == [(1,)]


def test_mandato_presidencial_liga_pelo_slug_e_rodar_de_novo_nao_muda_nada(banco, tmp_path):
    escrever(tmp_path, "presidentes_historico.json", _fhc())
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    # a economia, o território e a composição ligam o mandato do presidente pelo slug
    leitura = (
        "SELECT mp.slug, mp.rotulo, m.numero_mandato FROM core.mandato_presidencial mp "
        "JOIN core.mandato m ON m.id = mp.mandato_id ORDER BY m.numero_mandato"
    )
    esperado = [("fhc-1995", "FHC 1", 1), ("fhc-1999", "FHC 2", 2)]
    assert consulta(banco, leitura) == esperado
    antes = consulta(banco, "SELECT count(*) FROM core.mandato")
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, leitura) == esperado
    assert consulta(banco, "SELECT count(*) FROM core.mandato") == antes


def test_o_cpf_do_arquivo_curado_nao_chega_ao_banco_decisao_d3(banco, tmp_path):
    escrever(tmp_path, "presidentes_historico.json", _fhc())  # o arquivo traz o campo `cpf`
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(
        banco,
        "SELECT count(*) FROM information_schema.columns WHERE column_name ILIKE '%cpf%' AND table_schema IN ('core','leg')",
    ) == [(0,)]
    assert consulta(banco, "SELECT count(*) FROM core.pessoa_identificador WHERE valor = '00000000000'") == [(0,)]


def test_situacao_do_mandato_do_titular_exclui_o_periodo_em_que_foi_ministro(banco, tmp_path):
    presidente = {
        "id_referencia": "x-2003", "nome_civil": "Presidente X", "nome_eleitoral": "Presidente X", "partido_sigla": "PT",
        "mandato_numero": 1, "ano_eleicao": 2002, "data_inicio": "2003-01-01", "data_fim": "2007-01-01",
        "status_mandato": "CONCLUIDO", "ministros_fazenda_chave": [],
    }  # fmt: skip
    escrever(tmp_path, "presidentes_historico.json", [presidente])
    escrever(tmp_path, "senadores_senado.json", [senador(9, "Carla")])
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    situacoes = consulta(
        banco,
        "SELECT s.situacao, lower(s.periodo)::text, upper(s.periodo)::text FROM core.mandato_situacao s "
        "JOIN core.mandato m ON m.id = s.mandato_id JOIN core.pessoa pe ON pe.id = m.pessoa_id WHERE pe.nome_exibicao = 'Carla'",
    )
    assert situacoes == [("EXERCICIO", "2019-02-01", "2027-02-01")]


# ── filiações (derivadas dos períodos de partido dos mandatos) ─────────────────────────────────────────────────────
def test_filiacao_vem_do_partido_do_mandato_e_dos_periodos_exatos_sem_duplicar(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana")])
    escrever(tmp_path, "senadores_senado.json", [senador(9, "Beto")])
    carga(banco, tmp_path).carregar(["partidos", "pessoas", "filiacoes"])
    leitura = (
        "SELECT pe.nome_exibicao, pa.sigla, lower(f.periodo)::text, coalesce(upper(f.periodo)::text, 'aberta') "
        "FROM core.filiacao f JOIN core.partido pa ON pa.id = f.partido_id JOIN core.pessoa pe ON pe.id = f.pessoa_id "
        "ORDER BY 1, lower(f.periodo)"
    )
    # sem períodos exatos, vale o partido na posse, durante o mandato
    assert consulta(banco, leitura) == [
        ("Ana", "PT", "2023-02-01", "2027-02-01"),
        ("Beto", "PSD", "2019-02-01", "2027-02-01"),
    ]
    # a Câmara informa trocas dentro do mandato: os períodos exatos passam na frente; dois trechos seguidos do mesmo
    # partido viram uma filiação só
    with banco.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO core.mandato_partido (mandato_id, partido_id, periodo) "
                "SELECT m.id, p.id, v.periodo::daterange FROM core.mandato m JOIN core.pessoa pe ON pe.id = m.pessoa_id, "
                "(VALUES ('PSB', '[2023-02-01,2024-01-01)'), ('PL', '[2024-01-01,2025-01-01)'), "
                "        ('PL', '[2025-01-01,2027-02-01)')) AS v(sigla, periodo) "
                "JOIN core.partido p ON p.sigla = v.sigla WHERE pe.nome_exibicao = 'Ana'"
            )
        )
    for _ in range(2):
        resultado = carga(banco, tmp_path).carregar(["filiacoes"])["filiacoes"]
        assert consulta(banco, leitura) == [
            ("Ana", "PSB", "2023-02-01", "2024-01-01"),
            ("Ana", "PL", "2024-01-01", "2027-02-01"),
            ("Beto", "PSD", "2019-02-01", "2027-02-01"),
        ]
    assert resultado.contagem.motivos == {"UNIDO_AO_TRECHO_SEGUIDO_DO_MESMO_PARTIDO": 1}
    assert resultado.contagem.lidas == resultado.contagem.gravadas + resultado.contagem.rejeitadas
    assert (
        resultado.contagem.gravadas == consulta(banco, "SELECT count(*) FROM core.filiacao")[0][0]
    )  # medida, não derivada


def test_filiacao_de_quem_foi_deputado_e_senador_fica_numa_pessoa_so_sem_sobrepor(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana Souza", data_nascimento="1970-05-01")])
    escrever(
        tmp_path, "senadores_senado.json",
        [senador(9, "Ana Souza", nome_civil="ANA SOUZA", data_nascimento="1970-05-01", partido_sigla="PL")],
    )  # fmt: skip
    carga(banco, tmp_path).carregar(["partidos", "pessoas", "filiacoes"])
    assert consulta(
        banco,
        "SELECT pa.sigla, lower(f.periodo)::text, coalesce(upper(f.periodo)::text, 'aberta') FROM core.filiacao f "
        "JOIN core.partido pa ON pa.id = f.partido_id ORDER BY lower(f.periodo)",
    ) == [("PL", "2019-02-01", "2023-02-01"), ("PT", "2023-02-01", "2027-02-01")]


# ── proposições ────────────────────────────────────────────────────────────────────────────────────────────────────
def proposicao_camara(camara_id: int, numero: int, **extra) -> Dict[str, Any]:
    return {
        "camara_id": camara_id, "tipo": "PL", "numero": numero, "ano": 2023, "titulo": f"PL {numero}/2023",
        "ementa": "Ementa", "area_tematica": "Economia & Finanças", "data_apresentacao": "2023-03-01",
        "is_reforma_estrutural": False, "iniciativa_executivo": False, "autor_nome": "Ana", "autor_camara_id": 1,
        "autor_fonte": "API Dados Abertos da Câmara", "url_oficial": "https://exemplo", **extra,
    }  # fmt: skip


def test_proposicao_do_arquivo_entra_sem_situacao_inventada_e_a_autoria_so_vale_com_fonte(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana")])
    escrever(
        tmp_path,
        "proposicoes_2023.json",
        [proposicao_camara(100, 1), proposicao_camara(101, 2, autor_fonte=None, autor_nome="Quem?", autor_camara_id=1)],
    )
    carga(banco, tmp_path).carregar(["partidos", "pessoas", "proposicoes"])
    assert consulta(banco, "SELECT id_camara, status_codigo, autor_nome FROM leg.proposicao ORDER BY id_camara") == [
        (100, "SEM_INFORMACAO", "Ana"),
        (101, "SEM_INFORMACAO", None),
    ]
    assert consulta(
        banco,
        "SELECT p.id_camara, pe.nome_exibicao FROM leg.autoria a JOIN leg.proposicao p ON p.id = a.proposicao_id JOIN core.pessoa pe ON pe.id = a.pessoa_id",
    ) == [(100, "Ana")]


def test_proposicao_do_senado_adota_a_da_camara_com_a_mesma_numeracao_unica(banco, tmp_path):
    escrever(tmp_path, "proposicoes_2023.json", [proposicao_camara(100, 7, autor_nome=None, autor_camara_id=None)])
    escrever(
        tmp_path,
        "proposicoes_senado.json",
        [
            {
                "senado_id": 500,
                "tipo": "PL",
                "numero": 7,
                "ano": 2023,
                "titulo": "PL 7/2023",
                "ementa": "x",
                "data_apresentacao": "2023-03-01",
                "autor_nome": "Senador A",
                "autor_fonte": "API",
            },
            {
                "senado_id": 501,
                "tipo": "PL",
                "numero": 8,
                "ano": 2023,
                "titulo": "PL 8/2023",
                "ementa": "y",
                "data_apresentacao": "2023-03-02",
                "autor_nome": "Senador B",
                "autor_fonte": "API",
            },
            {
                "senado_id": 502,
                "tipo": "PL",
                "numero": 9,
                "ano": 1990,
                "titulo": "velha",
                "ementa": "z",
                "data_apresentacao": "1990-01-01",
            },
            [1, 2],
        ],
    )
    resultado = carga(banco, tmp_path).carregar(["partidos", "pessoas", "proposicoes"])["proposicoes"]
    assert consulta(banco, "SELECT numero, id_camara, id_senado FROM leg.proposicao ORDER BY numero") == [
        (7, 100, 500),
        (8, None, 501),
    ]
    assert resultado.contagem.motivos == {"FORA_DA_JANELA_1995": 1, "SEM_ID_OU_FORMATO_LEGADO": 1}
    antes = consulta(banco, "SELECT count(*) FROM leg.proposicao")
    carga(banco, tmp_path).carregar(["proposicoes"])
    assert consulta(banco, "SELECT count(*) FROM leg.proposicao") == antes


def test_duas_materias_do_senado_com_a_mesma_numeracao_nao_dependem_da_ordem_nem_duplicam_ao_repetir(banco, tmp_path):
    escrever(tmp_path, "proposicoes_2023.json", [proposicao_camara(100, 7, autor_nome=None, autor_camara_id=None)])
    materia = {"tipo": "PEC", "numero": 7, "ano": 2023, "ementa": "x", "data_apresentacao": "2023-03-01"}
    escrever(
        tmp_path,
        "proposicoes_senado.json",
        [{**materia, "senado_id": 900, "tipo": "PL"}, {**materia, "senado_id": 500, "tipo": "PL"}],
    )
    for _ in range(3):
        carga(banco, tmp_path).carregar(["partidos", "pessoas", "proposicoes"])
        assert consulta(banco, "SELECT id_camara, id_senado FROM leg.proposicao ORDER BY id_senado NULLS LAST") == [
            (100, 500),
            (None, 900),
        ]  # a de menor id adota a da Câmara; a outra fica como proposição própria


# ── votações ───────────────────────────────────────────────────────────────────────────────────────────────────────
def sessao_camara(id_externo: str, camara_id: int, **extra) -> Dict[str, Any]:
    return {
        "sessao_externa_id": id_externo, "proposicao_camara_id": camara_id, "proposicao_tipo": "PL", "proposicao_numero": 1,
        "proposicao_ano": 2023, "data_hora": "2023-05-10T19:00:00", "titulo_pauta": "Votação", "descricao": "Aprovado.",
        "aprovada": True, "total_sim": 1, "total_nao": 0, "total_abstencao": 0, "total_obstrucao": 0, **extra,
    }  # fmt: skip


def voto(id_externo: str, deputado_id: Any, opcao: Any, partido: str = "PT") -> Dict[str, Any]:
    return {"sessao_externa_id": id_externo, "deputado_camara_id": deputado_id, "voto": opcao, "partido_sigla": partido}


def test_votacao_de_plenario_liga_sessao_voto_e_parlamentar_e_rejeita_com_motivo(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana"), deputado(2, "Beto")])
    escrever(tmp_path, "proposicoes_2023.json", [proposicao_camara(100, 1, autor_nome=None, autor_camara_id=None)])
    escrever(
        tmp_path,
        "sessoes_votacao_2023.json",
        [
            sessao_camara("S1", 100),
            sessao_camara("S2", 999),  # proposição que não existe
            sessao_camara(
                "S3", 100, aprovada=None, descricao="Sem resultado claro na ementa."
            ),  # resultado desconhecido
        ],
    )
    escrever(
        tmp_path,
        "votos_nominais_2023.json",
        [
            voto("S1", 1, "SIM"),
            voto("S1", 2, "NAO", partido="PL"),
            voto("S1", 77, "SIM"),  # parlamentar que ninguém cadastrou
            voto("S1", 1, "TALVEZ"),  # opção desconhecida
            voto("S2", 1, "SIM"),
        ],
    )
    resultado = carga(banco, tmp_path).carregar(["partidos", "pessoas", "proposicoes", "votacoes"])["votacoes"]
    # resultado que a fonte não informa fica NULL (não vira "rejeitada") e a sessão entra do mesmo jeito
    assert consulta(
        banco, "SELECT v.id_externo, v.aprovada, v.tipo_deliberacao, v.total_sim_fonte FROM leg.votacao v ORDER BY 1"
    ) == [("S1", True, "NOMINAL", 1), ("S3", None, "NOMINAL", 1)]
    assert consulta(
        banco,
        "SELECT pe.nome_exibicao, vt.opcao_codigo, pa.sigla FROM leg.voto vt JOIN core.pessoa pe ON pe.id = vt.pessoa_id "
        "JOIN core.partido pa ON pa.id = vt.partido_id ORDER BY 1",
    ) == [("Ana", "SIM", "PT"), ("Beto", "NAO", "PL")]
    assert resultado.contagem.motivos["SEM_PROPOSICAO"] == 1
    assert resultado.contagem.motivos["VOTO_COM_OPCAO_INVALIDA"] == 1
    assert resultado.contagem.motivos["VOTO_DE_PARLAMENTAR_SEM_CADASTRO"] == 1
    assert resultado.contagem.motivos["VOTO_DE_SESSAO_REJEITADA"] == 1
    # as gravadas são medidas no banco (sessões que ficaram + votos que entraram), então a conferência é de verdade
    contagem = resultado.contagem
    assert contagem.lidas == contagem.gravadas + contagem.rejeitadas
    assert (
        contagem.gravadas
        == consulta(banco, "SELECT (SELECT count(*) FROM leg.votacao) + (SELECT count(*) FROM leg.voto)")[0][0]
    )
    votos = consulta(banco, "SELECT count(*) FROM leg.voto")
    carga(banco, tmp_path).carregar(["votacoes"])
    assert consulta(banco, "SELECT count(*) FROM leg.voto") == votos
    assert consulta(banco, "SELECT count(*) FROM leg.votacao") == [(2,)]


def test_votacao_anual_cria_a_proposicao_que_falta_e_o_parlamentar_que_so_votou_e_grava_a_orientacao(banco, tmp_path):
    import gzip

    arquivo = {
        "casa": "CAMARA", "ano": 2022, "fonte": "Câmara — Dados Abertos", "is_synthetic": False, "partidos": ["PT", "PL"],
        "parlamentares": {"700": {"nome": "Ex Deputado", "partido": "PL", "uf": "RJ", "legislaturas": [56]}},
        "sessoes": [
            {
                "id": "V1", "data_hora": "2022-03-01T19:00:00", "descricao": "Aprovado.", "aprovada": True,
                "proposicao": {"camara_id": 4000, "tipo": "PL", "numero": 5, "ano": 2022, "titulo": "PL 5/2022", "ementa": "Ementa", "data_apresentacao": "2022-01-10"},
                "orientacao_governo": "SIM", "orientacoes": {"PT": "SIM", "Oposição": "LIBERADO", "X": "VALOR_ESTRANHO"},
                "totais": {"SIM": 1}, "votos": [[700, "SIM", 1]],
            }
        ],
    }  # fmt: skip
    pasta = tmp_path / "votacoes"
    pasta.mkdir()
    (pasta / "camara_2022.json.gz").write_bytes(gzip.compress(json.dumps(arquivo).encode()))
    carga(banco, tmp_path).carregar(["partidos", "pessoas", "votacoes"])
    assert consulta(banco, "SELECT id_camara, status_codigo FROM leg.proposicao") == [(4000, "SEM_INFORMACAO")]
    assert consulta(
        banco,
        "SELECT pe.nome_exibicao, m.inicio::text, m.fim::text FROM core.mandato m JOIN core.pessoa pe ON pe.id = m.pessoa_id",
    ) == [("Ex Deputado", "2019-02-01", "2023-01-31")]
    assert consulta(
        banco, "SELECT vt.opcao_codigo, pa.sigla FROM leg.voto vt JOIN core.partido pa ON pa.id = vt.partido_id"
    ) == [("SIM", "PL")]
    assert consulta(banco, "SELECT bancada, orientacao FROM leg.orientacao ORDER BY bancada") == [
        ("Oposição", "LIBERADO"),
        ("PT", "SIM"),
    ]
    assert consulta(banco, "SELECT orientacao_governo, total_sim_fonte, total_nao_fonte FROM leg.votacao") == [
        ("SIM", 1, None)
    ]


def test_carga_incremental_de_votacoes_pula_os_arquivos_de_anos_anteriores(banco, tmp_path):
    import gzip

    def arquivo(ano, camara_id, id_sessao):
        return {
            "casa": "CAMARA", "ano": ano, "fonte": "Câmara — Dados Abertos", "is_synthetic": False, "partidos": ["PT"],
            "parlamentares": {"700": {"nome": "Ex Deputado", "partido": "PT", "uf": "RJ", "legislaturas": [56]}},
            "sessoes": [
                {
                    "id": id_sessao, "data_hora": f"{ano}-03-01T19:00:00", "descricao": "Aprovado.", "aprovada": True,
                    "proposicao": {"camara_id": camara_id, "tipo": "PL", "numero": camara_id, "ano": ano, "titulo": "PL", "ementa": "E", "data_apresentacao": f"{ano}-01-10"},
                    "votos": [[700, "SIM", 0]],
                }
            ],
        }  # fmt: skip

    pasta = tmp_path / "votacoes"
    pasta.mkdir()
    for ano, camara_id, sessao in ((2020, 20, "V20"), (2023, 23, "V23")):
        (pasta / f"camara_{ano}.json.gz").write_bytes(
            gzip.compress(json.dumps(arquivo(ano, camara_id, sessao)).encode())
        )
    carga(banco, tmp_path, votacoes_ano_inicio=2023).carregar(["partidos", "pessoas", "votacoes"])
    assert consulta(banco, "SELECT id_externo FROM leg.votacao") == [("V23",)]
    assert data_de_corte(banco, "CAMARA_API", "votacoes") == date(2023, 3, 1)  # o corte é a última sessão carregada


def test_hora_da_votacao_sem_fuso_e_a_de_brasilia(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana")])
    escrever(tmp_path, "proposicoes_2023.json", [proposicao_camara(100, 1, autor_nome=None, autor_camara_id=None)])
    escrever(tmp_path, "sessoes_votacao_2023.json", [sessao_camara("S1", 100, data_hora="2023-05-10T19:00:00")])
    escrever(tmp_path, "votos_nominais_2023.json", [voto("S1", 1, "SIM")])
    carga(banco, tmp_path).carregar(["partidos", "pessoas", "proposicoes", "votacoes"])
    assert consulta(banco, "SELECT (data_hora AT TIME ZONE 'UTC')::text FROM leg.votacao") == [("2023-05-10 22:00:00",)]


# ── corte e execução ───────────────────────────────────────────────────────────────────────────────────────────────
def test_o_corte_so_avanca_quando_a_carga_confirma_e_nunca_volta(banco):
    assert data_de_corte(banco, "CAMARA_API", "x") is None
    rodar(banco, "CAMARA_API", "x", lambda cursor, execucao: Resultado(Contagem(), ate=date(2024, 5, 1)))
    assert data_de_corte(banco, "CAMARA_API", "x") == date(2024, 5, 1)
    rodar(banco, "CAMARA_API", "x", lambda cursor, execucao: Resultado(Contagem(), ate=date(2023, 1, 1)))
    assert data_de_corte(banco, "CAMARA_API", "x") == date(2024, 5, 1)

    def falha(cursor, execucao):
        avancar_corte(cursor, "CAMARA_API", "x", date(2030, 1, 1), execucao.id)
        raise RuntimeError("caiu no meio")

    with pytest.raises(RuntimeError):
        rodar(banco, "CAMARA_API", "x", falha)
    assert data_de_corte(banco, "CAMARA_API", "x") == date(2024, 5, 1)  # a transação desfez o avanço
    assert consulta(
        banco, "SELECT status FROM etl.execucao WHERE parametros->>'recurso' = 'x' ORDER BY id DESC LIMIT 1"
    ) == [("ERRO",)]


def test_recurso_desconhecido_e_recusado(banco, tmp_path):
    with pytest.raises(ValueError, match="recurso desconhecido"):
        carga(banco, tmp_path).carregar(["staging"])


# ── identidade: prioridade da fonte atual, CPF diferente nunca une, CPF igual que chega depois funde ──────────────────
def test_quem_foi_deputado_e_e_senador_fica_com_os_dados_da_fonte_atual_seja_qual_for_o_id_que_vem_primeiro(
    banco, tmp_path
):
    h = "ef" * 32
    escrever(
        tmp_path,
        "parlamentares_legislaturas_anteriores.json",
        {
            "fonte": "Câmara — Dados Abertos",
            "is_synthetic": False,
            "deputados": [
                {
                    "camara_id": 5,
                    "nome": "Ana Velha",
                    "nome_civil": "ANA SOUZA",
                    "partido": "PT",
                    "uf": "SP",
                    "legislaturas": [55],
                }
            ],
            "senadores": [],
        },
    )
    escrever(
        tmp_path,
        "senadores_senado.json",
        [senador(9, "Ana Senadora", nome_civil="ANA SOUZA", email="ana@senado.leg.br", gabinete_sala="Ala 2")],
    )
    escrever(
        tmp_path,
        "cpf_identificadores.json",
        [
            {"id_tipo": "CAMARA_ID", "id_valor": "5", "cpf_hmac": h, "origem": "CAMARA_API"},
            {"id_tipo": "SENADO_ID", "id_valor": "9", "cpf_hmac": h, "origem": "TSE"},
        ],
    )
    for _ in range(2):
        carga(banco, tmp_path).carregar(["partidos", "pessoas"])
        # a linha do senador (fonte atual, prioridade 1) vale; a do ex-deputado (prioridade 0) só entra onde nada se sabe
        assert consulta(banco, "SELECT nome_exibicao, email, gabinete_sala, biografia FROM core.pessoa") == [
            ("Ana Senadora", "ana@senado.leg.br", "Ala 2", "Senador Federal pela UF MG (PSD).")
        ]


def test_cpf_hmac_diferente_nunca_une_por_nome_civil_e_nascimento_e_nao_vira_candidata(banco, tmp_path):
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana Souza", data_nascimento="1970-05-01")])
    escrever(
        tmp_path,
        "senadores_senado.json",
        [senador(9, "Ana Souza", nome_civil="ANA SOUZA", data_nascimento="1970-05-01")],
    )
    escrever(
        tmp_path,
        "cpf_identificadores.json",
        [
            {"id_tipo": "CAMARA_ID", "id_valor": "1", "cpf_hmac": "ab" * 32, "origem": "CAMARA_API"},
            {"id_tipo": "SENADO_ID", "id_valor": "9", "cpf_hmac": "cd" * 32, "origem": "TSE"},
        ],
    )
    for _ in range(2):
        carga(banco, tmp_path).carregar(["partidos", "pessoas"])
        assert consulta(banco, "SELECT count(*) FROM core.pessoa") == [
            (2,)
        ]  # homônimos de mesmo nascimento, CPFs distintos
        assert consulta(banco, "SELECT count(*) FROM core.pessoa_candidata_duplicidade") == [(0,)]
    # o mesmo vale quando um dos dois já estava gravado com o CPF e o outro chega depois (primeira visita do id)
    escrever(
        tmp_path,
        "cpf_identificadores.json",
        [{"id_tipo": "CAMARA_ID", "id_valor": "1", "cpf_hmac": "ab" * 32, "origem": "CAMARA_API"}],
    )
    with banco.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABELAS} RESTART IDENTITY CASCADE"))
    escrever(tmp_path, "senadores_senado.json", [])
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    escrever(
        tmp_path,
        "senadores_senado.json",
        [senador(9, "Ana Souza", nome_civil="ANA SOUZA", data_nascimento="1970-05-01")],
    )
    escrever(
        tmp_path,
        "cpf_identificadores.json",
        [
            {"id_tipo": "CAMARA_ID", "id_valor": "1", "cpf_hmac": "ab" * 32, "origem": "CAMARA_API"},
            {"id_tipo": "SENADO_ID", "id_valor": "9", "cpf_hmac": "cd" * 32, "origem": "TSE"},
        ],
    )
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT count(*) FROM core.pessoa") == [(2,)]


def test_mesmo_cpf_hmac_que_chega_depois_funde_duas_pessoas_ja_gravadas_mesmo_da_mesma_fonte(banco, tmp_path):
    h = "12" * 32
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana Souza")])
    escrever(tmp_path, "senadores_senado.json", [senador(9, "Outro Nome Qualquer")])
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])  # sem CPF: duas pessoas
    assert consulta(banco, "SELECT count(*) FROM core.pessoa") == [(2,)]
    menor = consulta(banco, "SELECT min(id) FROM core.pessoa")[0][0]
    uid = consulta(banco, f"SELECT uid::text FROM core.pessoa WHERE id = {menor}")[0][0]
    # o mesmo HMAC, pela mesma fonte, nos dois ids: o identificador é único por fonte, então a segunda pessoa não o recebe
    escrever(
        tmp_path,
        "cpf_identificadores.json",
        [
            {"id_tipo": "CAMARA_ID", "id_valor": "1", "cpf_hmac": h, "origem": "TSE"},
            {"id_tipo": "SENADO_ID", "id_valor": "9", "cpf_hmac": h, "origem": "TSE"},
        ],
    )
    for _ in range(2):
        carga(banco, tmp_path).carregar(["partidos", "pessoas"])
        assert consulta(banco, "SELECT count(*) FROM core.pessoa") == [(1,)]
        assert consulta(banco, "SELECT uid::text FROM core.pessoa") == [(uid,)]  # fica a de menor id
        assert consulta(banco, "SELECT tipo, valor FROM core.pessoa_identificador ORDER BY tipo") == [
            ("CAMARA_ID", "1"),
            ("CPF_HMAC", h),
            ("SENADO_ID", "9"),
        ]
        assert consulta(banco, "SELECT count(*) FROM core.pessoa_candidata_duplicidade") == [(0,)]
        assert consulta(banco, "SELECT count(*) FROM core.mandato") == [(2,)]


# ── senador: o partido de cada período vem das filiações do Senado, não da lista ────────────────────────────────────────
def test_filiacao_do_senador_segue_os_periodos_do_senado_e_nao_o_partido_atual_da_lista(banco, tmp_path):
    escrever(
        tmp_path, "senadores_senado.json", [senador(9, "Carla", partido_sigla="PL")]
    )  # mandato 2019-02-01..2027-01-31
    escrever(
        tmp_path,
        "senadores_filiacoes.json",
        {
            "fonte": "Senado — Dados Abertos",
            "is_synthetic": False,
            "senadores": [
                {
                    "senado_id": 9,
                    "filiacoes": [
                        {"sigla": "PL", "inicio": "2021-04-08", "fim": None},
                        {"sigla": "PODE", "inicio": "2017-07-04", "fim": "2021-04-08"},  # repete o dia da troca
                        {
                            "sigla": "S/Partido",
                            "inicio": "2013-08-20",
                            "fim": "2013-10-01",
                        },  # sem partido não é partido
                    ],
                }
            ],
        },
    )
    consulta_periodos = (
        "SELECT pa.sigla, lower(mp.periodo)::text, upper(mp.periodo)::text FROM core.mandato_partido mp "
        "JOIN core.partido pa ON pa.id = mp.partido_id ORDER BY 2"
    )
    for _ in range(2):
        carga(banco, tmp_path).carregar(["partidos", "pessoas", "filiacoes"])
        assert consulta(banco, consulta_periodos) == [
            ("PODE", "2019-02-01", "2021-04-08"),
            ("PL", "2021-04-08", "2027-02-01"),
        ]
        assert consulta(
            banco,
            "SELECT pa.sigla, lower(f.periodo)::text, upper(f.periodo)::text FROM core.filiacao f "
            "JOIN core.partido pa ON pa.id = f.partido_id ORDER BY 2",
        ) == [("PODE", "2019-02-01", "2021-04-08"), ("PL", "2021-04-08", "2027-02-01")]
    # sem o arquivo de filiações o período do mandato inteiro volta a ser o do partido que a lista informa
    (tmp_path / "senadores_filiacoes.json").unlink()
    with banco.begin() as conn:
        conn.execute(text("DELETE FROM core.mandato_partido"))
    carga(banco, tmp_path).carregar(["partidos", "pessoas", "filiacoes"])
    assert consulta(banco, "SELECT pa.sigla FROM core.filiacao f JOIN core.partido pa ON pa.id = f.partido_id") == [
        ("PL",)
    ]


# ── Câmara: histórico por deputado (eventos) e lote de CSV ──────────────────────────────────────────────────────────────
def _evento(id_deputado: int, quando: str, status: str, **extra) -> Dict[str, Any]:
    return {
        "id": id_deputado,
        "idLegislatura": 57,
        "dataHora": quando,
        "descricaoStatus": status,
        "nomeEleitoral": f"Dep {id_deputado}",
        "siglaUf": "SP",
        "siglaPartido": "PT",
        "condicaoEleitoral": "Titular",
        "situacao": "Exercício",
        **extra,
    }


def test_historico_da_camara_grava_mandato_situacao_e_partido_por_periodo_e_rejeita_sem_uf(banco, tmp_path):
    pasta = tmp_path / "historico"
    escrever(pasta, "_legislaturas.json", [{"id": 57, "dataInicio": "2023-02-01", "dataFim": "2027-01-31"}])
    escrever(
        pasta,
        "100.json",
        [
            _evento(100, "2023-02-01T10:00:00", "Entrada - Posse"),
            _evento(100, "2023-09-10T10:00:00", "Alteração de partido", siglaPartido="PSB"),
            _evento(100, "2024-06-30T10:00:00", "Saída - Renúncia"),
        ],
    )
    escrever(
        pasta, "101.json", [_evento(101, "2023-02-01T10:00:00", "Entrada - Posse")]
    )  # segue até o fim da legislatura
    escrever(pasta, "102.json", [_evento(102, "2023-02-01T10:00:00", "Entrada - Posse", siglaUf="")])  # sem UF
    for _ in range(2):
        resultado = carga(banco, tmp_path, historico_dir=pasta).carregar(["partidos", "camara_historico"])[
            "camara_historico"
        ]
        assert consulta(
            banco,
            "SELECT i.valor, m.inicio::text, m.fim::text, m.motivo_encerramento, ci.uf FROM core.mandato m "
            "JOIN core.pessoa_identificador i ON i.pessoa_id = m.pessoa_id AND i.tipo = 'CAMARA_ID' "
            "JOIN ref.circunscricao ci ON ci.id = m.circunscricao_id ORDER BY i.valor",
        ) == [
            ("100", "2023-02-01", "2024-06-29", "RENUNCIA", "SP"),
            ("101", "2023-02-01", "2027-01-31", None, "SP"),
        ]
        assert consulta(
            banco,
            "SELECT pa.sigla, lower(mp.periodo)::text, upper(mp.periodo)::text FROM core.mandato_partido mp "
            "JOIN core.partido pa ON pa.id = mp.partido_id JOIN core.mandato m ON m.id = mp.mandato_id "
            "JOIN core.pessoa_identificador i ON i.pessoa_id = m.pessoa_id AND i.valor = '100' ORDER BY 2",
        ) == [("PT", "2023-02-01", "2023-09-10"), ("PSB", "2023-09-10", "2024-06-30")]
        assert consulta(banco, "SELECT count(*) FROM core.mandato_situacao") == [(2,)]
        assert resultado.contagem.motivos == {"MANDATO_SEM_UF": 1}  # a circunscrição nacional não é inventada


class _ArquivoDoLote:
    def __init__(self, recurso: str, ano: int, caminho: Path):
        self.recurso, self.ano, self.caminho = recurso, ano, caminho
        self.url, self.sha256, self.bytes = (
            f"https://exemplo/{caminho.name}",
            f"{recurso}{ano}".ljust(64, "0"),
            caminho.stat().st_size,
        )


def _csv(pasta: Path, nome: str, cabecalho: List[str], linhas: List[List[str]]) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    caminho.write_text("\n".join(";".join(linha) for linha in [cabecalho] + linhas) + "\n", encoding="utf-8")
    return caminho


CABECALHO_PROPOSICAO = [
    "id", "siglaTipo", "numero", "ano", "ementa", "dataApresentacao", "urlInteiroTeor", "ultimoStatus_descricaoSituacao",
    "ultimoStatus_dataHora",
]  # fmt: skip
CABECALHO_AUTOR = [
    "idProposicao", "idDeputadoAutor", "tipoAutor", "nomeAutor", "siglaPartidoAutor", "siglaUFAutor", "ordemAssinatura",
    "proponente",
]  # fmt: skip


def test_lote_de_csv_da_camara_grava_proposicao_e_autoria_rejeita_fora_do_escopo_e_para_se_o_layout_mudar(
    banco, tmp_path
):
    pasta = tmp_path / "csv"
    proposicoes = _csv(
        pasta, "proposicoes-2023.csv", CABECALHO_PROPOSICAO,
        [
            ["900", "PL", "10", "2023", "Ementa um", "2023-03-01T10:00", "http://x/900", "Arquivada", "2023-05-01T10:00:00"],
            ["901", "XYZ", "11", "2023", "Tipo sem peso", "2023-03-02T10:00", "", "Arquivada", "2023-05-01T10:00:00"],
        ],
    )  # fmt: skip
    autores = _csv(
        pasta, "proposicoesAutores-2023.csv", CABECALHO_AUTOR,
        [
            ["900", "55", "Deputado(a)", "Beto", "PT", "SP", "1", "1"],
            ["900", "", "Órgão do Poder Executivo", "Poder Executivo", "", "", "2", "0"],
        ],
    )  # fmt: skip
    arquivos = [_ArquivoDoLote("proposicoes", 2023, proposicoes), _ArquivoDoLote("proposicoesAutores", 2023, autores)]
    for _ in range(2):
        resultado = carga(banco, tmp_path, lote_arquivos=arquivos).carregar(["partidos", "camara_lote"])["camara_lote"]
        assert consulta(banco, "SELECT id_camara, tipo_codigo, status_codigo FROM leg.proposicao") == [
            (900, "PL", "ARQUIVADA")
        ]
        assert consulta(banco, "SELECT tipo_codigo, nome_autor FROM leg.autoria ORDER BY ordem") == [
            ("AUTOR_PRINCIPAL", "Beto"),
            ("INSTITUCIONAL", "Poder Executivo"),
        ]
        assert resultado.contagem.motivos == {"TIPO_FORA_DO_ESCOPO": 1}
    quebrado = _csv(pasta, "proposicoes-2024.csv", [c for c in CABECALHO_PROPOSICAO if c != "ementa"], [])
    with pytest.raises(ValueError, match="layout da fonte mudou"):
        carga(banco, tmp_path, lote_arquivos=[_ArquivoDoLote("proposicoes", 2024, quebrado)]).carregar(["camara_lote"])


# ── texto desconhecido é NULL, registro sem id é rejeitado com motivo, eleição do suplente e janela de 1995 ──────────────
def test_biografia_so_leva_o_que_a_fonte_informa_e_nunca_o_texto_none(banco, tmp_path):
    escrever(
        tmp_path,
        "deputados_camara.json",
        [
            deputado(1, "Ana", uf=None),
            deputado(2, "Beto", partido_sigla=None),
            deputado(3, "Caio", uf=None, partido_sigla=None),
        ],
    )
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT nome_exibicao, biografia FROM core.pessoa ORDER BY nome_exibicao") == [
        ("Ana", "Deputado Federal (PT)."),
        ("Beto", "Deputado Federal pela UF SP."),
        ("Caio", None),
    ]


def test_registro_sem_identificador_e_rejeitado_com_motivo_e_a_conta_fecha_com_o_que_foi_gravado(banco, tmp_path):
    sem_id = {"nome_eleitoral": "Sem Id", "uf": "SP", "id_legislatura": 57}
    escrever(tmp_path, "deputados_camara.json", [deputado(1, "Ana"), sem_id])
    escrever(
        tmp_path,
        "senadores_senado.json",
        [senador(9, "Carla"), {"nome_eleitoral": "Sem Codigo", "mandato_inicio": "2019-02-01"}],
    )
    escrever(
        tmp_path,
        "presidentes_historico.json",
        [{"id_referencia": "x", "ano_eleicao": 2018, "data_inicio": "2019-01-01"}],
    )
    contagem = carga(banco, tmp_path).carregar(["partidos", "pessoas"])["pessoas"].contagem
    assert contagem.motivos == {"SEM_IDENTIFICADOR": 3}  # deputado, senador e presidente sem nome civil
    assert (contagem.lidas, contagem.gravadas, contagem.rejeitadas) == (5, 2, 3)
    assert consulta(banco, "SELECT count(*) FROM core.mandato") == [(2,)]
    # nenhuma verificação da execução reprovou, em particular `contagens` (lidas == gravadas + rejeitadas, com gravadas medida)
    assert (
        consulta(
            banco,
            "SELECT nome FROM etl.verificacao WHERE NOT passou AND execucao_id = "
            "(SELECT max(id) FROM etl.execucao WHERE parametros->>'recurso' = 'pessoas')",
        )
        == []
    )


def test_suplente_que_assume_no_meio_do_mandato_herda_a_eleicao_do_titular_e_as_suplencias_nao_colidem():
    from etl.carga.pessoas import Lote, parlamentar_do_senado

    lote = Lote()
    mandatos = [
        {"uf": "MG", "inicio": "2021-05-10", "fim": "2021-12-31", "participacao": "Suplente"},
        {"uf": "MG", "inicio": "2022-03-01", "fim": "2022-08-31", "participacao": "Suplente"},
    ]
    parlamentar_do_senado(lote, 77, {"nome": "Suplente", "partido_sigla": "PSD"}, mandatos, "SENADO_API", 0, {77})
    chaves = sorted((m["ano_eleicao"], m["numero_mandato"]) for m in lote.mandatos.values())
    assert chaves == [(2018, 1), (2018, 2)]  # a eleição do titular (e não 2020/2021), e as duas suplências não colidem
    # suplente que nunca votou não tem atuação a registrar
    vazio = Lote()
    parlamentar_do_senado(vazio, 77, {"nome": "Suplente"}, mandatos, "SENADO_API", 0, set())
    assert not vazio.mandatos and not vazio.pessoas


def test_mandato_que_chega_a_1995_nao_deixa_a_carga_com_alerta(banco, tmp_path):
    """A legislatura 49 termina em 1995-01-31: entra (sobrepõe a janela) e a verificação mede o fim, não o início."""
    escrever(
        tmp_path,
        "parlamentares_legislaturas_anteriores.json",
        {
            "fonte": "Câmara — Dados Abertos",
            "is_synthetic": False,
            "deputados": [
                {
                    "camara_id": 5,
                    "nome": "Ana",
                    "nome_civil": "ANA",
                    "partido": "PT",
                    "uf": "SP",
                    "legislaturas": [49, 50],
                }
            ],
            "senadores": [],
        },
    )
    carga(banco, tmp_path).carregar(["partidos", "pessoas"])
    assert consulta(banco, "SELECT min(inicio)::text FROM core.mandato") == [("1991-02-01",)]
    assert consulta(
        banco, "SELECT status FROM etl.execucao WHERE parametros->>'recurso' = 'pessoas' ORDER BY id DESC LIMIT 1"
    ) == [("OK",)]
