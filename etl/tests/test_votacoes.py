"""Extração e carga das votações nominais (Câmara/Senado) com orientação do governo."""

import json
from datetime import date

import pytest
from app.models import (  # noqa: E402
    CargoPoliticoEnum,
    Mandate,
    ParliamentaryVote,
    PoliticalParty,
    Politician,
    Proposition,
    StatusMandatoEnum,
    VotingSession,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from etl.extractors import votacoes_extractor as ve  # noqa: E402
from etl.pipelines import votacoes_loader as vl  # noqa: E402


# ---------------------------------------------------------------------------------------------- utilidades de parsing
def test_normalizar_orientacao_cobre_camara_e_senado():
    n = ve.normalizar_orientacao
    assert [n(x) for x in ("Sim", "SIM", "Não", "NÃO", "nao", "Liberado", "LIVRE", "Abstenção", "OBSTRUÇÃO")] == [
        "SIM",
        "SIM",
        "NAO",
        "NAO",
        "NAO",
        "LIBERADO",
        "LIBERADO",
        "ABSTENCAO",
        "OBSTRUCAO",
    ]
    assert n("Art. 17") == "ARTIGO_17"
    assert n("") is None and n(None) is None and n("Talvez") is None


def test_classificar_voto_senado_nao_presume_voto_secreto_nem_do_presidente():
    c = ve.classificar_voto_senado
    assert [c(x) for x in ("Sim", "Não", "Abstenção", "Obstrução")] == ["SIM", "NAO", "ABSTENCAO", "OBSTRUCAO"]
    assert [c(x) for x in ("AP", "LS", "MIS", "P-NRV", "NCom")] == ["AUSENTE"] * 5
    assert c("Votou") is None  # voto secreto
    assert c("Presidente (art. 51 RISF)") is None
    assert c("???") is None and c(None) is None


def test_status_da_situacao():
    assert ve._status_da_situacao("Transformado em Norma Jurídica") == "APROVADA_E_SANCIONADA"
    assert ve._status_da_situacao("Arquivada") == "ARQUIVADA"
    assert ve._status_da_situacao("Aguardando Designação de Relator") == "EM_TRAMITACAO"
    assert ve._status_da_situacao(None) == "EM_TRAMITACAO"


def test_gravacao_gz_roundtrip_e_listagem(tmp_path):
    ve.gravar_json_gz(tmp_path / "votacoes" / "camara_2020.json.gz", {"a": "ç"})
    ve.gravar_json_gz(tmp_path / "votacoes" / "camara_2019.json.gz", {"a": 1})
    assert ve.ler_json_gz(tmp_path / "votacoes" / "camara_2020.json.gz") == {"a": "ç"}
    assert [p.name for p in ve.listar_arquivos_processados(tmp_path, "camara")] == [
        "camara_2019.json.gz",
        "camara_2020.json.gz",
    ]
    assert ve.listar_arquivos_processados(tmp_path / "nao_existe", "camara") == []


# ---------------------------------------------------------------------------------------------- Câmara
def _csv(caminho, cabecalho, linhas):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    corpo = [";".join(f'"{c}"' for c in cabecalho)] + [";".join(f'"{v}"' for v in linha) for linha in linhas]
    caminho.write_text("\n".join(corpo) + "\n", encoding="utf-8-sig")


@pytest.fixture
def extrator_camara(tmp_path):
    raw = tmp_path / "raw"
    cam = raw / "camara"
    _csv(
        cam / "votacoes-2023.csv",
        [
            "id",
            "data",
            "dataHoraRegistro",
            "siglaOrgao",
            "aprovacao",
            "descricao",
            "ultimaApresentacaoProposicao_idProposicao",
        ],
        [
            ["V1", "2023-03-01", "2023-03-01T19:00:00", "PLEN", "1", "Aprovado o PL.", "1000"],
            ["V2", "2023-03-02", "2023-03-02T19:00:00", "PLEN", "", "Aprovada a matéria.", "1001"],
            ["V3", "2023-03-03", "2023-03-03T19:00:00", "PLEN", "1", "Aprovado o requerimento.", ""],
            ["V4", "2023-03-04", "2023-03-04T19:00:00", "CCJC", "1", "Em comissão.", ""],
            ["V5", "2023-03-05", "2023-03-05T19:00:00", "PLEN", "1", "Simbólica, sem voto nominal.", ""],
        ],
    )
    cab_voto = [
        "idVotacao",
        "dataHoraVoto",
        "voto",
        "deputado_id",
        "deputado_nome",
        "deputado_siglaPartido",
        "deputado_siglaUf",
        "deputado_idLegislatura",
        "deputado_urlFoto",
    ]
    _csv(
        cam / "votacoesVotos-2023.csv",
        cab_voto,
        [
            ["V1", "", "Sim", "1", "Ana", "PT", "SP", "57", "http://f/1"],
            ["V1", "", "Não", "2", "Beto", "PL", "RJ", "57", ""],
            ["V1", "", "Obstrução", "3", "Cida", "PL", "MG", "57", ""],
            ["V1", "", "Valor estranho", "4", "Dedé", "PT", "BA", "57", ""],
            ["V2", "", "Sim", "1", "Ana", "PT", "SP", "56", ""],
            ["V3", "", "Sim", "1", "Ana", "PT", "SP", "57", ""],
            ["V4", "", "Sim", "1", "Ana", "PT", "SP", "57", ""],
        ],
    )
    cab_obj = [
        "idVotacao",
        "proposicao_id",
        "proposicao_ementa",
        "proposicao_siglaTipo",
        "proposicao_numero",
        "proposicao_ano",
    ]
    _csv(cam / "votacoesObjetos-2023.csv", cab_obj, [["V1", "1000", "Ementa do PL 100", "PL", "100", "2023"]])
    _csv(
        cam / "votacoesProposicoes-2023.csv",
        cab_obj,
        [
            ["V1", "1000", "Ementa do PL 100", "PL", "100", "2023"],
            ["V1", "2000", "Requerimento", "REQ", "5", "2023"],
            ["V2", "1000", "Ementa do PL 100", "PL", "100", "2023"],
            ["V2", "1001", "Ementa da PEC", "PEC", "7", "2023"],
            ["V3", "2001", "Outro requerimento", "REQ", "6", "2023"],
        ],
    )
    _csv(
        cam / "votacoesOrientacoes-2023.csv",
        ["idVotacao", "siglaBancada", "orientacao"],
        [
            ["V1", "Governo", "Sim"],
            ["V1", "PL", "Não"],
            ["V1", "Minoria", "Liberado"],
            ["V2", "Governo", "Liberado"],
        ],
    )
    return ve.VotacoesCamaraExtractor(raw_dir=raw, processed_dir=tmp_path / "processed", http=object())


def test_camara_extrai_apenas_plenario_com_voto_nominal_e_proposicao_suportada(extrator_camara):
    dados = extrator_camara.extrair_ano(2023)
    assert dados["casa"] == "CAMARA" and dados["is_synthetic"] is False and dados["fonte"]
    ids = [s["id"] for s in dados["sessoes"]]
    assert ids == ["V1", "V2"]  # V3 só tem requerimento, V4 é comissão, V5 não tem voto nominal
    assert dados["descartes"] == {"sem_proposicao_suportada": 1, "vinculo_ambiguo": 1, "votos_tipo_desconhecido": 1}

    v1, v2 = dados["sessoes"]
    assert v1["proposicao"] == {
        "camara_id": 1000,
        "tipo": "PL",
        "numero": 100,
        "ano": 2023,
        "titulo": "PL 100/2023",
        "ementa": "Ementa do PL 100",
    }
    assert v1["aprovada"] is True and v2["aprovada"] is None
    assert v1["orientacao_governo"] == "SIM"
    assert v1["orientacoes"] == {"Governo": "SIM", "PL": "NAO", "Minoria": "LIBERADO"}
    assert v2["orientacao_governo"] == "LIBERADO"
    assert v1["totais"] == {"SIM": 1, "NAO": 1, "ABSTENCAO": 0, "OBSTRUCAO": 1, "ARTIGO_17": 0}
    assert [v[:2] for v in v1["votos"]] == [[1, "SIM"], [2, "NAO"], [3, "OBSTRUCAO"]]  # voto desconhecido descartado
    assert dados["partidos"][v1["votos"][0][2]] == "PT"


def test_camara_vinculo_ambiguo_prefere_a_ultima_proposicao_apresentada(extrator_camara):
    v2 = extrator_camara.extrair_ano(2023)["sessoes"][1]
    assert v2["proposicao"]["camara_id"] == 1001 and v2["proposicao"]["tipo"] == "PEC"


def test_camara_parlamentares_trazem_legislaturas_sem_duplicar(extrator_camara):
    parl = extrator_camara.extrair_ano(2023)["parlamentares"]
    assert parl["1"]["legislaturas"] == [57, 56] and parl["1"]["partido"] == "PT"
    assert "4" not in parl  # só votou com valor desconhecido: não entra


def test_camara_run_grava_arquivo_e_preserva_existente_quando_nao_ha_dados(extrator_camara, monkeypatch, tmp_path):
    monkeypatch.setattr(ve.VotacoesCamaraExtractor, "enriquecer_proposicoes", lambda self, ids, max_workers=6: {})
    resumo = extrator_camara.run([2023])
    destino = tmp_path / "processed" / "votacoes" / "camara_2023.json.gz"
    assert resumo["anos"][2023]["sessoes"] == 2 and resumo["anos"][2023]["com_orientacao_governo"] == 2
    anterior = destino.read_bytes()

    # ano sem CSVs e sem rede: nada é extraído e o arquivo bom permanece
    monkeypatch.setattr(extrator_camara, "baixar_csv", lambda *a, **k: None)
    falha = extrator_camara.run([2023])
    assert falha["falhas"] == [2023] and destino.read_bytes() == anterior


def test_camara_baixar_csv_rejeita_conteudo_que_nao_e_csv(tmp_path):
    class Http:
        def get_bytes(self, url, **_):
            return b"<html>erro</html>"

    ext = ve.VotacoesCamaraExtractor(raw_dir=tmp_path, http=Http())
    assert ext.baixar_csv("votacoes", 2023) is None
    assert not (tmp_path / "camara" / "votacoes-2023.csv").exists()


def test_camara_baixar_csv_404_e_cache(tmp_path):
    class Http404:
        def get_bytes(self, url, **_):
            raise ve.HttpError(url, 404, "nao existe")

    ext = ve.VotacoesCamaraExtractor(raw_dir=tmp_path, http=Http404())
    assert ext.baixar_csv("votacoes", 2099) is None

    class HttpOk:
        chamadas = 0

        def get_bytes(self, url, **_):
            HttpOk.chamadas += 1
            return b'"id";"x"\n"1";"2"\n'

    ext = ve.VotacoesCamaraExtractor(raw_dir=tmp_path, http=HttpOk())
    primeiro = ext.baixar_csv("votacoes", 2020)
    assert primeiro.exists() and ext.baixar_csv("votacoes", 2020) == primeiro and HttpOk.chamadas == 1
    ext.baixar_csv("votacoes", 2020, force=True)
    assert HttpOk.chamadas == 2


def test_camara_enriquecer_proposicoes_usa_cache(tmp_path):
    class Http:
        def __init__(self):
            self.urls = []

        def get_json(self, url, **_):
            self.urls.append(url)
            if url.endswith("/autores"):
                return {"dados": [{"nome": "Ana", "uri": "https://x/api/v2/deputados/77", "siglaPartido": "PT"}]}
            return {
                "dados": {
                    "dataApresentacao": "2023-02-10T10:00",
                    "ementa": "Ementa",
                    "urlInteiroTeor": "http://t",
                    "statusProposicao": {"descricaoSituacao": "Arquivada"},
                }
            }

    http = Http()
    ext = ve.VotacoesCamaraExtractor(raw_dir=tmp_path, http=http)
    det = ext.enriquecer_proposicoes([5, 5])
    assert det[5]["data_apresentacao"] == "2023-02-10" and det[5]["status"] == "ARQUIVADA"
    assert det[5]["autor_camara_id"] == 77 and det[5]["autor_nome"] == "Ana"
    n = len(http.urls)
    ext.enriquecer_proposicoes([5])
    assert len(http.urls) == n  # segunda chamada vem do cache em disco


def test_camara_enriquecer_proposicoes_tolera_falha(tmp_path):
    class Http:
        def get_json(self, url, **_):
            raise ve.HttpError(url, 500, "falha")

    ext = ve.VotacoesCamaraExtractor(raw_dir=tmp_path, http=Http())
    assert ext.enriquecer_proposicoes([9]) == {}


# ---------------------------------------------------------------------------------------------- Senado
def _votacao_senado(codigo, seq, sigla="PEC", numero="43", ano=2022, secreta="N", votos=None, resultado="A"):
    return {
        "ano": ano,
        "casaSessao": "SF",
        "codigoMateria": 155501,
        "codigoSessaoVotacao": codigo,
        "dataApresentacao": "2022-12-16",
        "dataSessao": "2023-06-06",
        "descricaoVotacao": "Votação nominal",
        "ementa": "Ementa PEC",
        "numero": numero,
        "sigla": sigla,
        "sequencialVotacao": seq,
        "resultadoVotacao": resultado,
        "totalVotosSim": 60,
        "totalVotosNao": 2,
        "totalVotosAbstencao": 1,
        "votacaoSecreta": secreta,
        "votos": votos if votos is not None else [],
    }


def _voto(codigo, voto, partido="PT"):
    return {
        "codigoParlamentar": codigo,
        "nomeParlamentar": f"Sen {codigo}",
        "siglaPartidoParlamentar": partido,
        "siglaUFParlamentar": "BA",
        "siglaVotoParlamentar": voto,
    }


def test_senado_extrai_votos_orientacao_e_voto_secreto(tmp_path, monkeypatch):
    lista = [
        _votacao_senado(10, 100, votos=[_voto(1, "Sim"), _voto(2, "Não", "PL"), _voto(3, "AP"), _voto(4, "Votou")]),
        _votacao_senado(11, 101, sigla="MSF", numero="2"),  # mensagem: tipo não suportado
        _votacao_senado(12, 102, secreta="S", votos=[_voto(1, "Votou")]),
        _votacao_senado(13, 103, votos=[_voto(1, "Votou")]),  # aberta, mas sem voto utilizável -> descartada
        {**_votacao_senado(14, 104), "casaSessao": "CN"},
    ]
    orient = {
        "votacoes": [
            {
                "sequencialVotacao": 100,
                "dataInicioVotacao": "2023-06-06T17:01:19",
                "orientacoesLideranca": [
                    {"partido": "Governo", "voto": "SIM"},
                    {"partido": "PL", "voto": "NÃO"},
                    {"partido": "Minoria", "voto": "LIVRE"},
                ],
            }
        ]
    }

    def falso(self, url, nome, ano, force):
        return lista if nome == "votacao" else orient

    monkeypatch.setattr(ve.VotacoesSenadoExtractor, "_json_com_cache", falso)
    ext = ve.VotacoesSenadoExtractor(raw_dir=tmp_path, processed_dir=tmp_path / "p", http=object())
    dados = ext.extrair_ano(2023)
    assert [s["id"] for s in dados["sessoes"]] == ["SEN-10", "SEN-12"]
    s10, s12 = dados["sessoes"]
    assert s10["orientacao_governo"] == "SIM" and s10["orientacoes"]["Minoria"] == "LIBERADO"
    assert s10["data_hora"] == "2023-06-06T17:01:19" and s10["aprovada"] is True
    assert [v[:2] for v in s10["votos"]] == [[1, "SIM"], [2, "NAO"], [3, "AUSENTE"]]  # voto secreto "Votou" ignorado
    assert s10["totais"]["SIM"] == 1
    assert s12["secreta"] is True and s12["votos"] == [] and s12["totais"]["SIM"] == 60  # totais da fonte
    assert s12["data_hora"] == "2023-06-06T00:00:00" and s12["orientacao_governo"] is None
    assert s10["proposicao"]["senado_id"] == 155501 and s10["proposicao"]["titulo"] == "PEC 43/2022"
    assert dados["descartes"] == {"tipo_nao_suportado": 1, "sem_voto_nominal": 1}

    resumo = ext.run([2023])
    assert resumo["anos"][2023]["sessoes"] == 2 and (tmp_path / "p" / "votacoes" / "senado_2023.json.gz").exists()


def test_senado_falha_de_rede_nao_gera_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(ve.VotacoesSenadoExtractor, "_json_com_cache", lambda *a, **k: None)
    ext = ve.VotacoesSenadoExtractor(raw_dir=tmp_path, processed_dir=tmp_path / "p", http=object())
    assert ext.run([2023])["falhas"] == [2023]
    assert not (tmp_path / "p" / "votacoes").exists()


def test_senado_json_com_cache(tmp_path):
    class Http:
        chamadas = 0

        def get_json(self, url, **_):
            Http.chamadas += 1
            return [{"x": 1}]

    ext = ve.VotacoesSenadoExtractor(raw_dir=tmp_path, http=Http())
    assert ext._json_com_cache("u", "votacao", 2020, False) == [{"x": 1}]
    assert ext._json_com_cache("u", "votacao", 2020, False) == [{"x": 1}] and Http.chamadas == 1

    class HttpErro:
        def get_json(self, url, **_):
            raise ve.HttpError(url, 500, "falha")

    assert (
        ve.VotacoesSenadoExtractor(raw_dir=tmp_path / "outro", http=HttpErro())._json_com_cache("u", "v", 2020, False)
        is None
    )


def test_parlamentares_historicos_extrai_e_preserva(tmp_path, monkeypatch):
    class Http:
        def get_json(self, url, **_):
            if "legislatura/56" in url:
                return {
                    "ListaParlamentarLegislatura": {
                        "Parlamentares": {
                            "Parlamentar": [
                                {
                                    "IdentificacaoParlamentar": {
                                        "CodigoParlamentar": "5573",
                                        "NomeParlamentar": "Abel",
                                        "NomeCompletoParlamentar": "Abel Rebouças",
                                        "SiglaPartidoParlamentar": "PDT",
                                    },
                                    "Mandatos": {
                                        "Mandato": {
                                            "UfParlamentar": "BA",
                                            "PrimeiraLegislaturaDoMandato": {
                                                "DataInicio": "2015-02-01",
                                                "DataFim": "2019-01-31",
                                            },
                                            "SegundaLegislaturaDoMandato": {
                                                "DataInicio": "2019-02-01",
                                                "DataFim": "2023-01-31",
                                            },
                                            "DescricaoParticipacao": "1º Suplente",
                                        }
                                    },
                                }
                            ]
                        }
                    }
                }
            raise ve.HttpError(url, 500, "falha")

    class FakeCamara:
        def __init__(self, http=None):
            pass

        def fetch_deputados(self, legislatura):
            return [
                {
                    "camara_id": 1,
                    "nome_eleitoral": "Ana",
                    "partido_sigla": "PT",
                    "uf": "SP",
                    "id_legislatura": legislatura,
                }
            ]

    import etl.extractors.camara_extractor as cam

    monkeypatch.setattr(cam, "CamaraExtractor", FakeCamara)
    out = ve.extrair_parlamentares_historicos(http=Http(), processed_dir=tmp_path)
    assert out == {"deputados": 1, "senadores": 1}
    dados = json.loads((tmp_path / "parlamentares_legislaturas_anteriores.json").read_text(encoding="utf-8"))
    assert dados["is_synthetic"] is False and dados["deputados"][0]["legislaturas"] == [55, 56]
    sen = dados["senadores"][0]
    assert sen["senado_id"] == 5573 and sen["mandatos"] == [
        {"uf": "BA", "inicio": "2015-02-01", "fim": "2023-01-31", "participacao": "1º Suplente"}
    ]

    class FalhaTotal(Http):
        def get_json(self, url, **_):
            raise ve.HttpError(url, 500, "falha")

    class CamaraVazia(FakeCamara):
        def fetch_deputados(self, legislatura):
            return []

    monkeypatch.setattr(cam, "CamaraExtractor", CamaraVazia)
    assert ve.extrair_parlamentares_historicos(http=FalhaTotal(), processed_dir=tmp_path) == {
        "deputados": 0,
        "senadores": 0,
    }
    assert json.loads((tmp_path / "parlamentares_legislaturas_anteriores.json").read_text(encoding="utf-8"))[
        "deputados"
    ]


def test_run_votacoes_exige_alguma_casa(monkeypatch, tmp_path):
    monkeypatch.setattr(ve.VotacoesCamaraExtractor, "run", lambda self, anos, force: {"anos": {}, "falhas": [2023]})
    monkeypatch.setattr(ve.VotacoesSenadoExtractor, "run", lambda self, anos, force: {"anos": {}, "falhas": [2023]})
    monkeypatch.setattr(ve, "extrair_parlamentares_historicos", lambda **k: {})
    with pytest.raises(RuntimeError):
        ve.run_votacoes([2023], processed_dir=tmp_path)
    monkeypatch.setattr(ve.VotacoesSenadoExtractor, "run", lambda self, anos, force: {"anos": {2023: {}}, "falhas": []})
    assert ve.run_votacoes([2023], processed_dir=tmp_path)["senado"]["anos"] == {2023: {}}


# ---------------------------------------------------------------------------------------------- carga
@pytest.fixture
def banco():
    engine = create_engine("sqlite://")
    from app.models import Base

    Base.metadata.create_all(engine)
    sessao = sessionmaker(bind=engine, expire_on_commit=False)()
    yield sessao
    sessao.close()
    engine.dispose()


@pytest.fixture
def partidos(banco):
    mapa = {}

    def garantir(session, party_map, sigla):
        existente = party_map.get(sigla)
        if existente:
            return existente
        p = PoliticalParty(acronym=sigla, full_name=f"Partido {sigla}")
        session.add(p)
        session.flush()
        party_map[sigla] = p.id
        return p.id

    for sigla in ("PT", "PL", "S.PART."):
        garantir(banco, mapa, sigla)
    return mapa, garantir


def _prop(**kw):
    base = {
        "camara_id": 1000,
        "tipo": "PL",
        "numero": 100,
        "ano": 2023,
        "titulo": "PL 100/2023",
        "ementa": "Altera o imposto sobre a renda.",
        "data_apresentacao": "2023-03-01",
        "status": "ARQUIVADA",
        "autor_nome": "Ana",
        "autor_camara_id": 1,
        "url_inteiro_teor": "http://t",
    }
    base.update(kw)
    return base


def _arquivo_camara(**sobre):
    dados = {
        "casa": "CAMARA",
        "ano": 2023,
        "fonte": "Câmara — Dados Abertos",
        "is_synthetic": False,
        "partidos": ["PT", "PL"],
        "parlamentares": {
            "1": {"nome": "Ana Dep", "partido": "PT", "uf": "SP", "foto_url": None, "legislaturas": [56, 57]},
            "2": {"nome": "Beto Dep", "partido": "PL", "uf": "RJ", "foto_url": None, "legislaturas": [57]},
        },
        "sessoes": [
            {
                "id": "V1",
                "data_hora": "2023-03-01T19:00:00",
                "descricao": "Aprovado.",
                "aprovada": True,
                "proposicao": _prop(),
                "orientacao_governo": "SIM",
                "orientacoes": {"Governo": "SIM", "PL": "NAO"},
                "totais": {"SIM": 1, "NAO": 1, "ABSTENCAO": 0, "OBSTRUCAO": 0},
                "votos": [[1, "SIM", 0], [2, "NAO", 1], [99, "SIM", 0]],  # 99 não existe na base e não tem cadastro
            },
            {
                "id": "V2",
                "data_hora": "2023-03-02T19:00:00",
                "descricao": "Rejeitada a matéria.",
                "aprovada": None,
                "proposicao": _prop(camara_id=2000, tipo="REQ", numero=5),  # tipo não suportado
                "orientacao_governo": None,
                "orientacoes": {},
                "totais": {},
                "votos": [[1, "SIM", 0]],
            },
        ],
    }
    dados.update(sobre)
    return dados


def _carregar(banco, tmp_path, partidos, deputy_map=None, senator_map=None):
    mapa, garantir = partidos
    return vl.carregar_votacoes(
        banco,
        tmp_path,
        deputy_map if deputy_map is not None else {},
        senator_map if senator_map is not None else {},
        mapa,
        garantir,
    )


def test_carga_cria_parlamentares_proposicao_sessao_votos_e_mandatos(banco, partidos, tmp_path):
    ve.gravar_json_gz(tmp_path / "votacoes" / "camara_2023.json.gz", _arquivo_camara())
    deputados = {}
    c = _carregar(banco, tmp_path, partidos, deputados)
    banco.commit()

    assert (c["sessoes_novas"], c["sessoes_descartadas"], c["proposicoes_criadas"]) == (1, 1, 1)
    assert c["politicos_criados"] == 2 and c["mandatos_criados"] == 3  # Ana: 56 e 57; Beto: 57
    sessao = banco.query(VotingSession).one()
    assert sessao.external_id == "V1" and sessao.is_approved is True
    assert sessao.government_orientation == "SIM"
    assert json.loads(sessao.party_orientations) == {"Governo": "SIM", "PL": "NAO"}
    assert (sessao.votes_yes_count, sessao.votes_no_count) == (1, 1)
    assert banco.query(ParliamentaryVote).count() == 2  # deputado 99 sem cadastro é ignorado
    prop = banco.query(Proposition).one()
    assert prop.external_camara_id == 1000 and prop.status.value == "ARQUIVADA" and prop.impact_axis != "(numero+ano)%5"
    assert str(prop.presentation_date) == "2023-03-01" and prop.official_url.endswith("idProposicao=1000")
    ana = banco.query(Politician).filter_by(camara_id=1).one()
    assert prop.author_politician_id == ana.id
    anos = {m.election_year: m for m in banco.query(Mandate).filter_by(politician_id=ana.id)}
    assert set(anos) == {2018, 2022}
    assert anos[2018].end_date == date(2023, 1, 31) and anos[2018].status == StatusMandatoEnum.CONCLUIDO
    assert anos[2018].office == CargoPoliticoEnum.DEPUTADO_FEDERAL


def test_carga_e_idempotente_e_atualiza_orientacao(banco, partidos, tmp_path):
    caminho = tmp_path / "votacoes" / "camara_2023.json.gz"
    ve.gravar_json_gz(caminho, _arquivo_camara())
    deputados = {}
    _carregar(banco, tmp_path, partidos, deputados)
    banco.commit()
    antes = (
        banco.query(VotingSession).count(),
        banco.query(ParliamentaryVote).count(),
        banco.query(Politician).count(),
        banco.query(Mandate).count(),
        banco.query(Proposition).count(),
    )

    dados = _arquivo_camara()
    dados["sessoes"][0]["orientacao_governo"] = "NAO"
    ve.gravar_json_gz(caminho, dados)
    c = _carregar(banco, tmp_path, partidos, deputados)
    banco.commit()
    depois = (
        banco.query(VotingSession).count(),
        banco.query(ParliamentaryVote).count(),
        banco.query(Politician).count(),
        banco.query(Mandate).count(),
        banco.query(Proposition).count(),
    )
    assert antes == depois and c["sessoes_novas"] == 0 and c["sessoes_atualizadas"] == 1
    assert banco.query(VotingSession).one().government_orientation == "NAO"


def test_carga_reaproveita_proposicao_e_politico_existentes(banco, partidos, tmp_path):
    existente = Politician(civil_name="Ana Dep", electoral_name="Ana Dep", camara_id=1)
    prop = Proposition(
        external_camara_id=1000,
        proposition_type=vl.TipoProposicaoEnum.PL,
        number=100,
        year=2023,
        title="PL 100/2023",
        summary="x",
        presentation_date=date(2023, 3, 1),
    )
    banco.add_all([existente, prop])
    banco.flush()
    ve.gravar_json_gz(tmp_path / "votacoes" / "camara_2023.json.gz", _arquivo_camara())
    c = _carregar(banco, tmp_path, partidos, {1: existente.id})
    assert c["proposicoes_criadas"] == 0 and c["politicos_criados"] == 1  # só Beto
    assert banco.query(Proposition).count() == 1


def test_carga_vincula_politico_existente_por_nome_unico(banco, partidos, tmp_path):
    senador = Politician(civil_name="Beto Dep", electoral_name="Beto Dep", senado_id=50)
    banco.add(senador)
    banco.flush()
    ve.gravar_json_gz(tmp_path / "votacoes" / "camara_2023.json.gz", _arquivo_camara())
    deputados = {}
    c = _carregar(banco, tmp_path, partidos, deputados)
    assert c["politicos_vinculados"] == 1 and deputados[2] == senador.id
    assert banco.get(Politician, senador.id).camara_id == 2 and banco.query(Politician).count() == 2


def test_carga_senado_liga_proposicao_da_camara_por_numeracao_unica(banco, partidos, tmp_path):
    ve.gravar_json_gz(tmp_path / "votacoes" / "camara_2023.json.gz", _arquivo_camara())
    senado = {
        "casa": "SENADO",
        "ano": 2023,
        "fonte": "Senado — Dados Abertos",
        "is_synthetic": False,
        "partidos": ["PT"],
        "parlamentares": {"7": {"nome": "Sen Sete", "partido": "PT", "uf": "BA"}},
        "sessoes": [
            {
                "id": "SEN-10",
                "data_hora": "2023-06-06T17:01:19",
                "descricao": "Votação nominal",
                "aprovada": True,
                "secreta": False,
                "proposicao": {
                    "senado_id": 777,
                    "tipo": "PL",
                    "numero": 100,
                    "ano": 2023,
                    "titulo": "PL 100/2023",
                    "ementa": "x",
                    "data_apresentacao": "2023-03-01",
                },
                "orientacao_governo": "SIM",
                "orientacoes": {"Governo": "SIM"},
                "totais": {"SIM": 1, "NAO": 0, "ABSTENCAO": 0, "OBSTRUCAO": 0},
                "votos": [[7, "SIM", 0]],
            },
            {
                "id": "SEN-11",
                "data_hora": "2015-06-06T17:01:19",
                "descricao": "Votação antiga",
                "aprovada": False,
                "secreta": True,
                "proposicao": {
                    "senado_id": 888,
                    "tipo": "PL",
                    "numero": 100,
                    "ano": 2015,
                    "titulo": "PL 100/2015",
                    "ementa": "y",
                },
                "orientacao_governo": None,
                "orientacoes": {},
                "totais": {"SIM": 40, "NAO": 30, "ABSTENCAO": 1},
                "votos": [],
            },
        ],
    }
    ve.gravar_json_gz(tmp_path / "votacoes" / "senado_2023.json.gz", senado)
    senadores = {}
    c = _carregar(banco, tmp_path, partidos, {}, senadores)
    banco.commit()
    prop = banco.query(Proposition).filter_by(external_camara_id=1000).one()
    assert prop.external_senado_id == 777  # numeração única (>= 2019): mesma proposição
    sen11 = banco.query(VotingSession).filter_by(external_id="SEN-11").one()
    assert sen11.is_secret_vote is True and sen11.votes_yes_count == 40 and sen11.proposition_id != prop.id
    assert banco.query(Proposition).count() == 2  # a de 2015 NÃO foi fundida com outra de mesmo número
    assert c["sessoes_novas"] == 3 and 7 in senadores


def test_carga_ignora_arquivo_sem_proveniencia(banco, partidos, tmp_path):
    ve.gravar_json_gz(tmp_path / "votacoes" / "camara_2023.json.gz", _arquivo_camara(fonte=None))
    ve.gravar_json_gz(tmp_path / "votacoes" / "camara_2024.json.gz", _arquivo_camara(is_synthetic=True))
    c = _carregar(banco, tmp_path, partidos)
    assert c["sessoes_novas"] == 0 and banco.query(VotingSession).count() == 0


def test_carga_sem_arquivos_nao_faz_nada(banco, partidos, tmp_path):
    assert _carregar(banco, tmp_path, partidos)["sessoes_novas"] == 0


def test_parlamentares_historicos_criam_ex_deputados_e_senadores_titulares(banco, partidos, tmp_path):
    (tmp_path / vl.ARQUIVO_HISTORICOS).write_text(
        json.dumps(
            {
                "fonte": "oficial",
                "is_synthetic": False,
                "deputados": [
                    {
                        "camara_id": 7,
                        "nome_eleitoral": "Ex Dep",
                        "partido_sigla": "PSL",
                        "uf": "RJ",
                        "legislaturas": [56],
                    }
                ],
                "senadores": [
                    {
                        "senado_id": 9,
                        "nome_eleitoral": "Sen Titular",
                        "partido_sigla": "PT",
                        "mandatos": [
                            {"uf": "BA", "inicio": "2019-02-01", "fim": "2027-01-31", "participacao": "Titular"}
                        ],
                    },
                    {
                        "senado_id": 10,
                        "nome_eleitoral": "Suplente Que Nunca Votou",
                        "partido_sigla": "PT",
                        "mandatos": [
                            {"uf": "BA", "inicio": "2019-02-01", "fim": "2023-01-31", "participacao": "1º Suplente"}
                        ],
                    },
                    {
                        "senado_id": 11,
                        "nome_eleitoral": "Suplente Votante",
                        "partido_sigla": "PT",
                        "mandatos": [
                            {"uf": "SP", "inicio": "2019-02-01", "fim": "2023-01-31", "participacao": "1º Suplente"}
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    ve.gravar_json_gz(
        tmp_path / "votacoes" / "senado_2021.json.gz",
        {"fonte": "x", "is_synthetic": False, "parlamentares": {"11": {"nome": "Suplente Votante"}}, "sessoes": []},
    )
    mapa, garantir = partidos
    deputados, senadores = {}, {}
    r = vl.carregar_parlamentares_historicos(banco, tmp_path, deputados, senadores, mapa, garantir)
    banco.commit()

    assert r == {"politicos_criados": 3, "politicos_vinculados": 0, "mandatos_criados": 3}
    assert 7 in deputados and 9 in senadores and 11 in senadores and 10 not in senadores
    assert banco.query(Politician).filter_by(electoral_name="Suplente Que Nunca Votou").count() == 0
    sup = banco.query(Mandate).filter_by(politician_id=senadores[11]).one()
    assert sup.status == StatusMandatoEnum.SUPLENTE_EM_EXERCICIO and sup.jurisdiction_state == "SP"
    tit = banco.query(Mandate).filter_by(politician_id=senadores[9]).one()
    assert tit.office == CargoPoliticoEnum.SENADOR and tit.election_year == 2018

    # idempotência
    r2 = vl.carregar_parlamentares_historicos(banco, tmp_path, deputados, senadores, mapa, garantir)
    assert r2 == {"politicos_criados": 0, "politicos_vinculados": 0, "mandatos_criados": 0}


def test_parlamentares_historicos_sem_arquivo_confiavel(banco, partidos, tmp_path):
    mapa, garantir = partidos
    assert vl.carregar_parlamentares_historicos(banco, tmp_path, {}, {}, mapa, garantir) == {}
    (tmp_path / vl.ARQUIVO_HISTORICOS).write_text(json.dumps({"deputados": []}), encoding="utf-8")
    assert vl.carregar_parlamentares_historicos(banco, tmp_path, {}, {}, mapa, garantir) == {}


def test_helpers_de_data_e_status():
    assert vl._date("2023-02-01T10:00") == date(2023, 2, 1) and vl._date("xx") is None and vl._date(None) is None
    assert vl._datetime("2023-02-01T10:00:00").hour == 10 and vl._datetime("x") is None and vl._datetime("") is None
    assert vl._status_mandato(date(2000, 1, 1)) == StatusMandatoEnum.CONCLUIDO
    assert vl._status_mandato(date(2999, 1, 1)) == StatusMandatoEnum.TITULAR_ATIVO
    assert vl._status_mandato(None) == StatusMandatoEnum.TITULAR_ATIVO


def test_orientacao_do_governo_aceita_grafias_da_camara_e_recusa_conflito():
    f = ve.orientacao_do_governo
    assert f({"Governo": "Sim"}) == "SIM"
    assert f({"GOV.": "Não"}) == "NAO"
    assert f({"GOV.": "Sim", "Governo": "Sim"}) == "SIM"  # as duas grafias coexistem e concordam
    assert f({"GOV.": "Sim", "Governo": "Não"}) is None  # conflito: não escolhe
    assert f({"PT": "Sim", "Minoria": "Não"}) is None and f({}) is None
    assert f({"Governo": "Talvez"}) is None


def test_camara_extrai_comissoes_quando_solicitado(extrator_camara):
    dados = extrator_camara.extrair_ano(2023, incluir_comissoes=True)
    assert dados["casa"] == "CAMARA"
    # Com incluir_comissoes=True, V4 (CCJC) é avaliado no pipeline em vez de descartado no filtro de órgão
    assert dados["descartes"]["sem_proposicao_suportada"] == 2
