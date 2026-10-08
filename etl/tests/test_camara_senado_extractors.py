"""Regras puras dos extractors da Câmara e do Senado (sem rede)."""

from etl.extractors.camara_extractor import (
    CamaraExtractor,
    chave_materia,
    classificar_voto,
    deduplicar_deputados,
    interpretar_aprovacao,
)
from etl.extractors.senado_extractor import (
    classificar_voto_senado,
    extrair_mandato,
    interpretar_resultado,
)


def test_deduplicar_deputados_um_por_camara_id_preservando_campos():
    brutos = [
        {"camara_id": 1, "nome_eleitoral": "A", "email": None},
        {"camara_id": 1, "nome_eleitoral": "A", "email": "a@x.leg.br"},
        {"camara_id": 2, "nome_eleitoral": "B"},
        {"camara_id": 1, "nome_eleitoral": "A", "partido_sigla": "PT"},
        {"nome_eleitoral": "sem id"},
    ]
    saida = {d["camara_id"]: d for d in deduplicar_deputados(brutos)}
    assert set(saida) == {1, 2}
    assert saida[1]["email"] == "a@x.leg.br" and saida[1]["partido_sigla"] == "PT"


def test_chave_materia_normaliza():
    assert chave_materia("pl", "93", 2023) == ("PL", 93, 2023)
    assert chave_materia(None, "x", None) == ("", 0, 0)
    # número igual com tipo/ano diferentes NÃO é a mesma matéria
    assert chave_materia("PLP", 93, 2023) != chave_materia("PL", 93, 2005)


def test_interpretar_aprovacao():
    assert interpretar_aprovacao({"aprovacao": 1}) is True
    assert interpretar_aprovacao({"aprovacao": 0, "descricao": "Aprovado o requerimento"}) is False
    assert interpretar_aprovacao({"descricao": "Requerimento aprovado"}) is None  # não presume
    assert interpretar_aprovacao({"descricao": "Aprovada a Medida Provisória"}) is True
    assert interpretar_aprovacao({"descricao": "Rejeitada a emenda"}) is None
    assert interpretar_aprovacao({"descricao": "Rejeitado o projeto"}) is False
    assert interpretar_aprovacao({}) is None


def test_classificar_voto_camara():
    assert classificar_voto("Sim") == "SIM"
    assert classificar_voto("Não") == "NAO"
    assert classificar_voto("Abstenção") == "ABSTENCAO"
    assert classificar_voto("Obstrução") == "OBSTRUCAO"
    assert classificar_voto("Artigo 17") == "ARTIGO_17"
    assert classificar_voto("Art. 17") == "ARTIGO_17"
    assert classificar_voto("") == "AUSENTE"
    assert classificar_voto("Valor Novo Desconhecido") is None


def test_classificar_voto_senado_nao_infla_abstencao():
    assert classificar_voto_senado("Sim") == "SIM"
    assert classificar_voto_senado("Não") == "NAO"
    assert classificar_voto_senado("Abstenção") == "ABSTENCAO"
    for ausente in ("P-NRV", "NCom", "Licença", "Presidente (art. 51 RISF)", None):
        assert classificar_voto_senado(ausente) == "AUSENTE"


def test_interpretar_resultado_senado():
    assert interpretar_resultado("Aprovada") is True
    assert interpretar_resultado("Rejeitada") is False
    assert interpretar_resultado("") is None
    assert interpretar_resultado(None) is None


def test_extrair_mandato_tolera_ausencia():
    assert extrair_mandato({})["mandato_inicio"] is None
    m = extrair_mandato(
        {
            "Mandato": {
                "PrimeiraLegislaturaDoMandato": {"NumeroLegislatura": "56", "DataInicio": "2019-02-01"},
                "SegundaLegislaturaDoMandato": {"NumeroLegislatura": "57", "DataFim": "2027-01-31"},
            }
        }
    )
    assert m["mandato_inicio"] == "2019-02-01" and m["mandato_fim"] == "2027-01-31"
    assert (m["legislatura_inicio"], m["legislatura_fim"]) == ("56", "57")


class HttpFalso:
    def __init__(self, resposta):
        self.resposta = resposta

    def get_json(self, url, **_):
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta


def test_autoria_falha_da_api_nao_vira_poder_executivo():
    from etl.utils.http_client import HttpError

    ext = CamaraExtractor(http=HttpFalso(HttpError("u", 429, "limite")))
    r = ext.fetch_autores_proposicao(1)
    assert r["autor_nome"] is None and r["falha_api"] is True


def test_autoria_vazia_nao_e_presumida():
    ext = CamaraExtractor(http=HttpFalso({"dados": []}))
    r = ext.fetch_autores_proposicao(1)
    assert r["autor_nome"] is None and r["falha_api"] is False


def test_autoria_primeiro_autor_deputado():
    ext = CamaraExtractor(
        http=HttpFalso(
            {
                "dados": [
                    {"nome": "Fulano", "uri": "https://x/api/v2/deputados/123", "siglaPartido": "PT"},
                    {"nome": "Outro"},
                ]
            }
        )
    )
    r = ext.fetch_autores_proposicao(1)
    assert (r["autor_nome"], r["autor_camara_id"], r["autor_partido"]) == ("Fulano", 123, "PT")


def test_telefone_do_senado_vem_da_api():
    from etl.extractors.senado_extractor import formatar_telefone_senado

    assert formatar_telefone_senado({"Telefones": {"Telefone": [{"NumeroTelefone": "33036333"}]}}) == "(61) 3303-6333"
    assert formatar_telefone_senado({"Telefones": {"Telefone": {"NumeroTelefone": "33036333"}}}) == "(61) 3303-6333"
    assert formatar_telefone_senado({"Telefones": {"Telefone": [{"NumeroTelefone": "123"}]}}) is None
    assert formatar_telefone_senado({}) is None


VOTACOES_PLP_93 = [  # recorte de /proposicoes/2357053/votacoes (API real da Câmara)
    {
        "id": "2357053-8",
        "siglaOrgao": "MESA",
        "dataHoraRegistro": "2023-05-12T15:49:27",
        "aprovacao": 1,
        "descricao": "Retirado o REQ n.1241/2023, em razão do deferimento do Requerimento",
    },
    {
        "id": "2362292-8",
        "siglaOrgao": "PLEN",
        "dataHoraRegistro": "2023-05-17T18:21:32",
        "aprovacao": 1,
        "descricao": "Aprovado o Requerimento de Urgência (Art. 155 do RICD). Sim: 367; não: 102; total: 470.",
    },
    {
        "id": "2357053-65",
        "siglaOrgao": "PLEN",
        "dataHoraRegistro": "2023-05-24T19:53:19",
        "aprovacao": None,
        "descricao": "Mantido o texto. Sim: 306; não: 170; total: 476.",
    },
    {
        "id": "2357053-47",
        "siglaOrgao": "PLEN",
        "dataHoraRegistro": "2023-05-23T23:31:18",
        "aprovacao": 1,
        "descricao": "Aprovado o Substitutivo ao Projeto de Lei Complementar nº 93, de 2023, ressalvados os destaques. Sim: 372; não: 108.",
    },
    {
        "id": "2357053-72",
        "siglaOrgao": "PLEN",
        "dataHoraRegistro": "2023-05-24T20:18:06",
        "aprovacao": 1,
        "descricao": "Aprovada a Redação Final assinada pelo Relator.",
    },
    {
        "id": "2357053-108",
        "siglaOrgao": "PLEN",
        "dataHoraRegistro": "2023-08-22T19:57:51",
        "aprovacao": 1,
        "descricao": "Aprovadas as Emendas do Senado Federal ao Projeto de Lei Complementar nº 93-B, de 2023, ressalvados os destaques.",
    },
]


def test_votacao_de_merito_nao_e_destaque_requerimento_nem_redacao_final():
    ordenadas = CamaraExtractor(http=HttpFalso(None))._escolher_votacao_de_merito(VOTACOES_PLP_93)
    assert ordenadas[0]["id"] == "2357053-47"  # o Substitutivo, não "Mantido o texto" (destaque)
    assert ordenadas[-1]["id"] == "2357053-8"  # MESA por último
    assert interpretar_aprovacao({"descricao": "Mantido o texto. Sim: 306; não: 170."}) is None


def test_descricao_de_merito_com_ressalva_de_destaques_ainda_e_merito():
    assert interpretar_aprovacao({"descricao": "Aprovado o Substitutivo ... ressalvados os destaques."}) is True
    assert interpretar_aprovacao({"descricao": "Rejeitado o Projeto de Lei nº 1."}) is False
