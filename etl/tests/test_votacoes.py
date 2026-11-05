"""Extração das votações nominais (Câmara/Senado) com orientação do governo; a carga está em `test_planas` e `test_preparar_sql`."""

import json
import os
from datetime import date

import pytest

from etl.extractors import votacoes_extractor as ve  # noqa: E402


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


def test_senado_completa_a_lista_anual_com_as_votacoes_do_plenario(tmp_path, monkeypatch):
    lista = [_votacao_senado(10, 100, votos=[_voto(1, "Sim")])]

    def plenario(codigo, materia, votos):
        return {
            "CodigoSessaoVotacao": str(codigo),
            "DataSessao": "2023-10-14",
            "HoraInicio": "14:00",
            "Secreta": "N",
            "DescricaoVotacao": "Votação nominal da PEC 221/2019, em primeiro turno.",
            "Resultado": "A",
            "CodigoMateria": "174386",
            "SiglaMateria": materia,
            "NumeroMateria": "221",
            "AnoMateria": "2019",
            "Votos": {"VotoParlamentar": votos},
        }

    voto = lambda cod, v: {  # noqa: E731
        "CodigoParlamentar": str(cod),
        "NomeParlamentar": f"Sen {cod}",
        "SiglaPartido": "PL",
        "SiglaUF": "BA",
        "Voto": v,
    }
    mensal = {
        "ListaVotacoes": {
            "Votacoes": {
                "Votacao": [
                    plenario(10, "PEC", [voto(1, "Sim")]),  # já veio na lista anual: não duplica
                    plenario(7106, "PEC", [voto(1, "Sim"), voto(2, "NCom"), voto(3, "Não")]),
                    plenario(7108, "MSF", [voto(1, "Sim")]),  # tipo não suportado
                ]
            }
        }
    }

    def falso(self, url, nome, ano, force):
        if nome == "votacao":
            return lista
        return mensal if nome == "plenario_lista_10" else {}

    monkeypatch.setattr(ve.VotacoesSenadoExtractor, "_json_com_cache", falso)
    ext = ve.VotacoesSenadoExtractor(raw_dir=tmp_path, processed_dir=tmp_path / "p", http=object())
    ids = [s["id"] for s in ext.extrair_ano(2023)["sessoes"]]
    assert ids == ["SEN-10", "SEN-7106"]
    nova = ext.extrair_ano(2023)["sessoes"][1]
    assert nova["data_hora"] == "2023-10-14T14:00:00" and nova["aprovada"] is True
    assert [v[:2] for v in nova["votos"]] == [[1, "SIM"], [2, "AUSENTE"], [3, "NAO"]]
    assert nova["proposicao"]["titulo"] == "PEC 221/2019" and nova["proposicao"]["senado_id"] == 174386


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


# ---------------------------------------------------------------------------------- plenário por mês (Senado)
def _plenario_item(codigo, *, secreta=False, votos=None, **extra):
    item = {
        "CodigoSessaoVotacao": str(codigo) if codigo is not None else "",
        "DataSessao": "2025-03-05",
        "HoraInicio": "14:00",
        "Secreta": "S" if secreta else "N",
        "DescricaoVotacao": "Votação nominal.",
        "Resultado": "A",
        "CodigoMateria": "169690",
        "SiglaMateria": "PEC",
        "NumeroMateria": "10",
        "AnoMateria": "2024",
        "Votos": {"VotoParlamentar": votos or []},
    }
    item.update(extra)
    return item


def _extrator_com_plenario(tmp_path, monkeypatch, mensal, hoje=date(2025, 3, 10)):
    """Extrator do Senado cuja consulta do plenário devolve `mensal[nome do cache]` (None = falha de rede)."""
    chamadas = []

    def falso(self, url, nome, ano, force):
        chamadas.append(url)
        if nome in ("votacao", "orientacoes"):
            return [] if nome == "votacao" else {}
        return mensal.get(nome, {})

    monkeypatch.setattr(ve.VotacoesSenadoExtractor, "_json_com_cache", falso)
    ext = ve.VotacoesSenadoExtractor(raw_dir=tmp_path, processed_dir=tmp_path / "p", http=object(), hoje=hoje)
    return ext, chamadas


def test_plenario_corta_a_janela_em_hoje(tmp_path, monkeypatch):
    ext, chamadas = _extrator_com_plenario(tmp_path, monkeypatch, {}, hoje=date(2025, 3, 10))
    ext._sessoes_plenario(2025, False, {}, {})
    assert [u.rsplit("/", 2)[-2:] for u in chamadas] == [
        ["20250101", "20250131"],
        ["20250201", "20250228"],
        ["20250301", "20250310"],
    ]


def test_plenario_mes_com_falha_e_reportado_e_nao_e_mes_vazio(tmp_path, monkeypatch):
    mensal = {"plenario_lista_01": None, "plenario_lista_02": {}}  # janeiro falhou; fevereiro veio vazio
    ext, _ = _extrator_com_plenario(tmp_path, monkeypatch, mensal, hoje=date(2025, 2, 20))
    sessoes, falhas = ext._sessoes_plenario(2025, False, {}, {})
    assert sessoes == [] and falhas == ["2025-01"]


def test_run_nao_regrava_o_ano_quando_um_mes_do_plenario_falha(tmp_path, monkeypatch):
    voto = {"CodigoParlamentar": "1", "NomeParlamentar": "Sen 1", "SiglaPartido": "PL", "SiglaUF": "BA", "Voto": "Sim"}
    mensal = {"plenario_lista_01": None, "plenario_lista_03": {"ListaVotacoes": {"Votacoes": {"Votacao": [
        _plenario_item(500, votos=[voto])]}}}}  # fmt: skip
    ext, _ = _extrator_com_plenario(tmp_path, monkeypatch, mensal)
    resumo = ext.run([2025])
    assert resumo["anos"] == {} and resumo["falhas"] == ["2025-01"]
    assert not (tmp_path / "p" / "votacoes" / "senado_2025.json.gz").exists()  # arquivo existente seria preservado


def test_plenario_votacao_secreta_usa_os_totais_publicados(tmp_path, monkeypatch):
    item = _plenario_item(7053, secreta=True, TotalVotosSim="43", TotalVotosNao="2", TotalVotosAbstencao="1")
    mensal = {"plenario_lista_03": {"ListaVotacoes": {"Votacoes": {"Votacao": [item]}}}}
    ext, _ = _extrator_com_plenario(tmp_path, monkeypatch, mensal)
    (sessao,) = ext.extrair_ano(2025)["sessoes"]
    assert sessao["secreta"] is True and sessao["votos"] == []
    assert sessao["totais"] == {"SIM": 43, "NAO": 2, "ABSTENCAO": 1, "OBSTRUCAO": 0}


def test_plenario_descarta_item_sem_codigo_de_sessao(tmp_path, monkeypatch, caplog):
    voto = {"CodigoParlamentar": "1", "NomeParlamentar": "Sen 1", "SiglaPartido": "PL", "SiglaUF": "BA", "Voto": "Sim"}
    itens = [_plenario_item(None, votos=[voto]), _plenario_item(None, votos=[voto]), _plenario_item(9, votos=[voto])]
    mensal = {"plenario_lista_03": {"ListaVotacoes": {"Votacoes": {"Votacao": itens}}}}
    ext, _ = _extrator_com_plenario(tmp_path, monkeypatch, mensal)
    with caplog.at_level("WARNING"):
        sessoes = ext.extrair_ano(2025)["sessoes"]
    assert [s["id"] for s in sessoes] == ["SEN-9"]  # sem a guarda viraria "SEN-None" e esconderia as outras sessões
    assert "sem CodigoSessaoVotacao" in caplog.text


@pytest.mark.parametrize(
    "hoje, ano, expira",
    [
        (date(2026, 2, 28), 2025, True),  # ano anterior ainda em acerto, antes de 1º de março
        (date(2026, 3, 1), 2025, False),
        (date(2026, 10, 1), 2025, False),
        (date(2026, 10, 1), 2026, True),
        (date(2026, 2, 28), 2024, False),
    ],
)
def test_ttl_do_cache_cobre_o_ano_anterior_ate_marco(tmp_path, hoje, ano, expira):
    ext = ve.VotacoesSenadoExtractor(raw_dir=tmp_path, http=object(), hoje=hoje)
    assert ext._ano_em_andamento(ano) is expira


def test_cache_do_ano_anterior_expirado_e_refeito_antes_de_marco(tmp_path):
    class Http:
        chamadas = 0

        def get_json(self, url, **_):
            Http.chamadas += 1
            return [{"x": Http.chamadas}]

    ext = ve.VotacoesSenadoExtractor(raw_dir=tmp_path, http=Http(), hoje=date(2026, 2, 10))
    ext._json_com_cache("u", "votacao", 2025, False)
    arquivo = tmp_path / "senado" / "votacao-2025.json"
    velho = arquivo.stat().st_mtime - 2 * 24 * 3600
    os.utime(arquivo, (velho, velho))  # cache de dois dias
    assert ext._json_com_cache("u", "votacao", 2025, False) == [{"x": 2}]  # refeito: o ano anterior ainda expira
    ext_depois = ve.VotacoesSenadoExtractor(raw_dir=tmp_path, http=Http(), hoje=date(2026, 4, 1))
    os.utime(arquivo, (velho, velho))
    assert ext_depois._json_com_cache("u", "votacao", 2025, False) == [{"x": 2}]  # depois de março, cache eterno


def _atualizar_com_dublês(monkeypatch, sincronizar):
    from unittest.mock import MagicMock

    from etl.pipelines import votacoes_atualizacao as va

    chamadas = []
    monkeypatch.setattr(va, "run_votacoes", lambda anos, force: {})

    class CargaFalsa:
        contagens = {}
        resumo_fusao = {}

        def __init__(self, data_dir, engine):
            pass

        def load_all(self, recursos, fundir, migrar):
            # os mapas saem do staging: partidos e políticos entram antes das votações; o cron não migra o schema
            assert recursos == ["partidos", "politicos", "votacoes_historico"] and migrar is False
            chamadas.append("carga")
            if fundir:
                chamadas.append("merge")

    monkeypatch.setattr(va, "CargaCadastro", CargaFalsa)
    monkeypatch.setattr(va, "posprocessar_carga", lambda motor: chamadas.append("pos") if motor is va.engine else None)
    va.engine = MagicMock() if va.engine is None else va.engine
    va.atualizar(sincronizar=sincronizar)
    return chamadas


def test_atualizacao_de_votacoes_funde_e_depois_posprocessa(monkeypatch):
    assert _atualizar_com_dublês(monkeypatch, sincronizar=True) == ["carga", "merge", "pos"]


def test_atualizacao_sem_fusao_deixa_o_posprocessamento_a_quem_chamou(monkeypatch):
    assert _atualizar_com_dublês(monkeypatch, sincronizar=False) == ["carga"]
