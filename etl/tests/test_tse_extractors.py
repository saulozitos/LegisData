"""Extratores e cargas do TSE: fixtures sintéticas pequenas (nenhum microdado real é usado)."""

import csv
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

from etl.extractors import (
    tse_candidaturas_extractor,
    tse_core,
    tse_doacoes_extractor,
    tse_eleicoes_extractor,
    tse_patrimonio_extractor,
)
from etl.extractors.tse_core import Politico, casar_candidatos, escolher_membros, ler_candidatos, parse_brl
from etl.tests.sinteticos import CPF_B, formatado
from etl.utils.identidades import IdentidadesParlamentares, parse_date, valid_cpf
from etl.utils.provenance import is_trusted

CAND_COLS = [
    "ANO_ELEICAO",
    "SG_UF",
    "SG_UE",
    "DS_CARGO",
    "SQ_CANDIDATO",
    "NM_CANDIDATO",
    "NM_URNA_CANDIDATO",
    "NR_CPF_CANDIDATO",
    "DT_NASCIMENTO",
    "DS_SITUACAO_CANDIDATURA",
    "DS_DETALHE_SITUACAO_CAND",
    "DS_SIT_TOT_TURNO",
    "NR_TURNO",
    "NR_PROCESSO",
]


def zip_csv(path: Path, membros: dict, sep: str = ";") -> Path:
    """Cria um zip com CSVs latin-1. `membros`: nome -> (colunas, linhas)."""
    with zipfile.ZipFile(path, "w") as zf:
        for nome, (colunas, linhas) in membros.items():
            buf = io.StringIO()
            w = csv.writer(buf, delimiter=sep, quoting=csv.QUOTE_ALL, lineterminator="\n")
            w.writerow(colunas)
            w.writerows(linhas)
            zf.writestr(nome, buf.getvalue().encode("latin-1"))
    return path


def cand_row(sq, nome, urna, uf="SP", cargo="DEPUTADO FEDERAL", cpf="", nasc="", **extra):
    row = {c: "" for c in CAND_COLS}
    row.update(
        ANO_ELEICAO="2022",
        SG_UF=uf,
        SG_UE=uf,
        DS_CARGO=cargo,
        SQ_CANDIDATO=str(sq),
        NM_CANDIDATO=nome,
        NM_URNA_CANDIDATO=urna,
        NR_CPF_CANDIDATO=cpf,
        DT_NASCIMENTO=nasc,
        NR_TURNO="1",
    )
    row.update(extra)
    return [row[c] for c in CAND_COLS]


def politico(chave, civil, eleitoral, uf="SP", cargo="DEPUTADO_FEDERAL", cpf=None, nasc=None, **ids):
    return Politico(
        chave=chave, nome_civil=civil, nome_eleitoral=eleitoral, uf=uf, cargo=cargo, cpf=cpf, nascimento=nasc, **ids
    )


def candidatos_df(tmp_path, linhas, ano=2022):
    zip_path = zip_csv(tmp_path / f"consulta_cand_{ano}.zip", {f"consulta_cand_{ano}_BRASIL.csv": (CAND_COLS, linhas)})
    return ler_candidatos(zip_path)


# ----------------------------------------------------------------------------------------------------------
# utilidades
# ----------------------------------------------------------------------------------------------------------
def test_parse_brl_e_marcadores_do_tse():
    assert parse_brl("15000,00") == 15000.0
    assert parse_brl("1.234,50") == 1234.5
    assert parse_brl("96") == 96.0
    assert parse_brl("#NE") is None and parse_brl("#NULO") is None and parse_brl("") is None and parse_brl(None) is None
    assert parse_brl("abc") is None


def test_valid_cpf_rejeita_mascara_do_tse_e_digitos_repetidos():
    assert valid_cpf(formatado(CPF_B)) == CPF_B
    assert valid_cpf("-4") is None and valid_cpf("00000000000") is None and valid_cpf(None) is None


def test_parse_date_aceita_iso_e_br():
    assert parse_date("1945-10-27") == date(1945, 10, 27)
    assert parse_date("06/10/1945") == date(1945, 10, 6)
    assert parse_date("#NULO#") is None and parse_date("31/02/2000") is None


def test_escolher_membros_prefere_consolidado_sem_duplicar_o_br():
    nomes = ["x_SP.csv", "x_BR.csv", "x_BRASIL.csv", "leiame.pdf"]
    assert escolher_membros(nomes) == ["x_BRASIL.csv"]
    assert escolher_membros(["x_SP.csv", "x_RJ.csv"]) == ["x_SP.csv", "x_RJ.csv"]


def test_ler_candidatos_deduplica_candidato_por_turno(tmp_path):
    df = candidatos_df(
        tmp_path,
        [
            cand_row(1, "Fulano da Silva", "Fulano", uf="BR", cargo="PRESIDENTE"),
            cand_row(1, "Fulano da Silva", "Fulano", uf="BR", cargo="PRESIDENTE", NR_TURNO="2"),
        ],
    )
    assert len(df) == 1


# ----------------------------------------------------------------------------------------------------------
# casamento candidato -> político
# ----------------------------------------------------------------------------------------------------------
def test_casamento_por_cpf_ignora_nome_e_uf(tmp_path):
    df = candidatos_df(tmp_path, [cand_row(1, "Nome Totalmente Outro", "Outro", uf="RJ", cpf=CPF_B)])
    res = casar_candidatos([politico("c:1", "Fulano", "Fulano", cpf=CPF_B)], df)
    assert res.casados == {"c:1": 0} and res.motivo["c:1"] == "cpf"


def test_casamento_por_nome_e_nascimento_aceita_uf_diferente(tmp_path):
    df = candidatos_df(tmp_path, [cand_row(1, "Maria de Souza", "Maria", uf="RJ", nasc="01/02/1970")])
    p = politico("c:1", "Maria de Souza", "Maria", uf="SP", nasc=date(1970, 2, 1))
    assert casar_candidatos([p], df).motivo == {"c:1": "nascimento"}


def test_nascimento_diferente_rejeita_homonimo(tmp_path):
    df = candidatos_df(tmp_path, [cand_row(1, "Maria de Souza", "Maria", nasc="01/02/1990")])
    p = politico("c:1", "Maria de Souza", "Maria", nasc=date(1970, 2, 1))
    assert casar_candidatos([p], df).casados == {}


def test_homonimos_na_mesma_uf_sem_data_de_nascimento_sao_ambiguos(tmp_path):
    df = candidatos_df(tmp_path, [cand_row(1, "João Silva", "João"), cand_row(2, "João Silva", "João Silva Jr")])
    res = casar_candidatos([politico("c:1", "João Silva", "João Silva")], df)
    assert res.casados == {} and res.ambiguos == 1


def test_nunca_casa_por_substring(tmp_path):
    df = candidatos_df(tmp_path, [cand_row(1, "Lula da Fonte Neto", "Lula da Fonte")])
    assert casar_candidatos([politico("c:1", "Lula", "Lula")], df).casados == {}


def test_presidente_com_nascimento_divergente_no_tse_casa_por_candidatura_nacional(tmp_path):
    df = candidatos_df(
        tmp_path,
        [cand_row(1, "Luiz Inácio Lula da Silva", "Lula", uf="BR", cargo="PRESIDENTE", nasc="06/10/1945")],
    )
    p = politico("presidente:lula", "Luiz Inácio Lula da Silva", "Lula", uf="BR", cargo="PRESIDENTE")
    p.nascimento = date(1945, 10, 27)
    res = casar_candidatos([p], df)
    assert res.motivo == {"presidente:lula": "nome+cargo_nacional"}


def test_candidato_reivindicado_por_dois_politicos_sem_evidencia_forte_e_descartado(tmp_path):
    df = candidatos_df(tmp_path, [cand_row(1, "Ana Costa", "Ana")])
    res = casar_candidatos([politico("c:1", "Ana Costa", "Ana"), politico("s:2", "Ana Costa", "Ana")], df)
    assert res.casados == {}


# ----------------------------------------------------------------------------------------------------------
# patrimônio
# ----------------------------------------------------------------------------------------------------------
BEM_COLS = ["SG_UE", "SQ_CANDIDATO", "VR_BEM_CANDIDATO", "DS_TIPO_BEM_CANDIDATO", "DS_BEM_CANDIDATO"]


def fake_baixar(tmp_path, mapa):
    def _baixar(dataset, arquivo, raw_dir=None, force=False):
        return mapa.get(arquivo)

    return _baixar


def test_patrimonio_soma_bens_do_candidato_casado(tmp_path, monkeypatch):
    cand = zip_csv(
        tmp_path / "consulta_cand_2022.zip",
        {
            "consulta_cand_2022_BRASIL.csv": (
                CAND_COLS,
                [
                    cand_row(10, "Fulano de Tal", "Fulano", nasc="01/01/1980"),
                    cand_row(11, "Beltrano Qualquer", "Beltrano", nasc="02/02/1975"),
                ],
            )
        },
    )
    bem = zip_csv(
        tmp_path / "bem_candidato_2022.zip",
        {
            "bem_candidato_2022_BRASIL.csv": (
                BEM_COLS,
                [
                    ["SP", "10", "100000,00", "Casa", "x"],
                    ["SP", "10", "50000,50", "Veículo", "y"],
                    ["SP", "10", "#NE", "Outros", "sem valor"],
                    ["SP", "99", "7,00", "Casa", "de outro candidato"],
                ],
            )
        },
    )
    monkeypatch.setattr(
        tse_patrimonio_extractor,
        "baixar",
        fake_baixar(tmp_path, {"consulta_cand_2022.zip": cand, "bem_candidato_2022.zip": bem}),
    )
    universo = [
        politico("camara:1", "Fulano de Tal", "Fulano", nasc=date(1980, 1, 1), camara_id=1),
        politico("camara:2", "Beltrano Qualquer", "Beltrano", nasc=date(1975, 2, 2), camara_id=2),  # sem bens
    ]
    saida = tmp_path / "processed"
    saida.mkdir()
    registros = tse_patrimonio_extractor.TSEPatrimonioExtractor(processed_dir=saida, raw_dir=tmp_path).run(
        anos=[2022], universo=universo
    )
    assert len(registros) == 1
    r = registros[0]
    assert r["camara_id"] == 1 and r["ano_eleicao"] == 2022
    assert r["valor_declarado_brl"] == 150000.5 and r["quantidade_bens"] == 2
    assert "Casa (R$ 100.000,00)" in r["detalhes_bens"] and "2 bens declarados" in r["detalhes_bens"]
    assert is_trusted(r) and "bem_candidato_2022.zip" in r["fonte"]
    assert json.loads((saida / "declaracoes_patrimonio.json").read_text(encoding="utf-8")) == registros


def test_patrimonio_ano_sem_arquivo_no_tse_e_ignorado(tmp_path, monkeypatch):
    monkeypatch.setattr(tse_patrimonio_extractor, "baixar", fake_baixar(tmp_path, {}))
    saida = tmp_path / "processed"
    saida.mkdir()
    ext = tse_patrimonio_extractor.TSEPatrimonioExtractor(processed_dir=saida, raw_dir=tmp_path)
    assert ext.run(anos=[2002], universo=[politico("c:1", "A B", "A")]) == []
    assert not (saida / "declaracoes_patrimonio.json").exists()


def test_resumir_bens_limita_tipos():
    texto = tse_patrimonio_extractor.resumir_bens({f"Tipo {i}": 100.0 + i for i in range(9)}, 12)
    assert texto.count("R$") == tse_patrimonio_extractor.TOP_TIPOS and "outros 3 tipos" in texto
    assert texto.endswith("12 bens declarados")


# ----------------------------------------------------------------------------------------------------------
# doações
# ----------------------------------------------------------------------------------------------------------
def test_mascarar_documento():
    mascarar = tse_doacoes_extractor.mascarar_documento
    assert mascarar(formatado(CPF_B)) == "***.456.789-**"
    assert mascarar("12345678000195") == "12.345.678/0001-95"
    assert mascarar("#NULO#") is None and mascarar("-1") is None and mascarar("123") is None
    # "000"+CPF é um CPF com enchimento, mesmo formatado como CNPJ: nunca sai do extrator (decisão D3)
    mascara = f"000{CPF_B}"
    assert mascarar(mascara) is None
    assert mascarar(f"{mascara[:2]}.{mascara[2:5]}.{mascara[5:8]}/{mascara[8:12]}-{mascara[12:]}") is None
    banco = "00000000000191"  # o CNPJ conhecido do Banco do Brasil continua íntegro
    assert mascarar(banco) == f"{banco[:2]}.{banco[2:5]}.{banco[5:8]}/{banco[8:12]}-{banco[12:]}"


RECEITA_2022 = ["SQ_CANDIDATO", "SG_UE", "NR_CPF_CNPJ_DOADOR", "NM_DOADOR", "VR_RECEITA", "DS_ORIGEM_RECEITA"]


def test_doacoes_agrega_top_doadores_e_preserva_total(tmp_path, monkeypatch):
    cand = zip_csv(
        tmp_path / "consulta_cand_2022.zip",
        {"consulta_cand_2022_BRASIL.csv": (CAND_COLS, [cand_row(10, "Fulano de Tal", "Fulano", nasc="01/01/1980")])},
    )
    linhas = [["10", "SP", CPF_B, f"Pessoa {i}", f"{100 + i},00", "Recursos de pessoas físicas"] for i in range(5)]
    linhas.append(["10", "SP", "12345678000195", "Empresa X", "1000,00", "Recursos de pessoas jurídicas"])
    linhas.append(["10", "SP", CPF_B, "Pessoa 0", "50,00", "Recursos de pessoas físicas"])  # mesmo doador
    linhas.append(["77", "SP", "1", "De outro candidato", "9999,00", "Outros"])
    contas = zip_csv(tmp_path / "contas_2022.zip", {"receitas_candidatos_2022_SP.csv": (RECEITA_2022, linhas)})
    monkeypatch.setattr(
        tse_doacoes_extractor,
        "baixar",
        fake_baixar(
            tmp_path, {"consulta_cand_2022.zip": cand, "prestacao_de_contas_eleitorais_candidatos_2022.zip": contas}
        ),
    )
    monkeypatch.setattr(tse_doacoes_extractor, "TOP_DOADORES", 3)
    universo = [politico("camara:1", "Fulano de Tal", "Fulano", nasc=date(1980, 1, 1), camara_id=1)]
    saida = tmp_path / "processed"
    saida.mkdir()
    registros = tse_doacoes_extractor.TseDoacoesExtractor(processed_dir=saida, raw_dir=tmp_path).run(
        anos=[2022], universo=universo
    )
    assert len(registros) == 1
    r = registros[0]
    total = 100 + 101 + 102 + 103 + 104 + 1000 + 50
    assert r["total_arrecadado"] == total and r["quantidade_receitas"] == 7
    assert sum(d["valor_doado"] for d in r["doadores"]) == total  # a linha agregada preserva o total
    assert r["doadores"][0]["nome_doador"] == "Empresa X"
    assert r["doadores"][0]["cpf_cnpj_doador"] == "12.345.678/0001-95"
    pf = [d for d in r["doadores"] if d["nome_doador"].startswith("Pessoa")]
    assert all(d["cpf_cnpj_doador"] == "***.456.789-**" for d in pf)  # CPF nunca é gravado inteiro
    assert r["doadores"][-1]["nome_doador"].startswith("Demais doadores")
    assert CPF_B not in (saida / "tse_doacoes_campanha.json").read_text(encoding="utf-8")


def test_layout_2014_e_normalizado(tmp_path):
    cols = {
        "Sequencial Candidato": "5",
        "UF": "AL",
        "CPF/CNPJ do doador": "12345678000195",
        "Nome do doador": "ACME",
        "Valor receita": "20000",
        "Tipo receita": "Recursos de pessoas jurídicas",
    }
    zip_path = zip_csv(tmp_path / "f.zip", {"receitas_candidatos_2014_AL.txt": (list(cols), [list(cols.values())])})
    blocos = list(tse_doacoes_extractor.ler_receitas(zip_path, tse_doacoes_extractor.LAYOUTS[2014]))
    assert blocos[0].iloc[0].to_dict() == {
        "sq": "5",
        "uf": "AL",
        "doc": "12345678000195",
        "nome": "ACME",
        "valor": "20000",
        "origem": "Recursos de pessoas jurídicas",
    }


def test_receita_liga_por_uf_e_sq_sem_colidir_entre_estados():
    import pandas as pd

    bloco = pd.DataFrame(
        [
            {"sq": "1", "uf": "SP", "doc": "", "nome": "A", "valor": "10", "origem": ""},
            {"sq": "1", "uf": "RJ", "doc": "", "nome": "B", "valor": "20", "origem": ""},
        ]
    )
    res = tse_doacoes_extractor.agregar_receitas([bloco], {}, {"SP|1": "SP|1"})
    assert set(res) == {"SP|1"} and res["SP|1"]["total"] == 10


# ----------------------------------------------------------------------------------------------------------
# eleições presidenciais por UF
# ----------------------------------------------------------------------------------------------------------
VOT_COLS = [
    "SG_UF",
    "NR_TURNO",
    "DS_CARGO",
    "NM_CANDIDATO",
    "SG_PARTIDO",
    "QT_VOTOS_NOMINAIS",
    "QT_VOTOS_NOMINAIS_VALIDOS",
]


def test_nome_proprio_e_mandato_por_ano():
    assert tse_eleicoes_extractor.nome_proprio("LUIZ INÁCIO LULA DA SILVA") == "Luiz Inácio Lula da Silva"
    refs = tse_eleicoes_extractor.mandato_por_ano(
        [
            {"id_referencia": "temer-2016", "ano_eleicao": 2014, "data_inicio": "2016-08-31"},
            {"id_referencia": "dilma-2015", "ano_eleicao": 2014, "data_inicio": "2015-01-01"},
            {"id_referencia": "lula-2023", "ano_eleicao": 2022, "data_inicio": "2023-01-01"},
        ]
    )
    assert refs == {2014: "dilma-2015", 2022: "lula-2023"}


def test_resultados_usam_turno_decisivo_e_percentual_sobre_validos(tmp_path):
    linhas = [
        ["SP", "1", "Presidente", "AAA", "P1", "60", "60"],
        ["SP", "1", "Presidente", "BBB", "P2", "30", "30"],
        ["SP", "1", "Presidente", "CCC", "P3", "10", "10"],
        ["SP", "2", "Presidente", "AAA", "P1", "70", "70"],
        ["SP", "2", "Presidente", "BBB", "P2", "30", "30"],
        ["SP", "2", "Governador", "ZZZ", "P9", "999", "999"],  # outro cargo é ignorado
        ["ZZ", "2", "Presidente", "AAA", "P1", "5", "5"],  # exterior não vira UF
    ]
    zip_path = zip_csv(tmp_path / "v.zip", {"votacao_candidato_munzona_2022_BR.csv": (VOT_COLS, linhas)})
    votos = tse_eleicoes_extractor.somar_votos(zip_path)
    res = tse_eleicoes_extractor.resultados_por_uf(votos, 2022, "lula-2023", "fonte x")
    assert len(res) == 1
    r = res[0]
    assert r["uf"] == "SP" and r["turno"] == 2 and r["total_votos_validos"] == 100
    assert (r["candidato_vencedor_nome"], r["votos_vencedor_pct"]) == ("Aaa", 70.0)
    assert (r["candidato_segundo_nome"], r["votos_segundo_pct"]) == ("Bbb", 30.0)
    assert r["verificado"] is True and r["is_synthetic"] is False and r["mandato_id_ref"] == "lula-2023"


def test_eleicoes_extractor_grava_csv_e_ignora_ano_sem_mandato(tmp_path, monkeypatch):
    zip_path = zip_csv(
        tmp_path / "v.zip",
        {
            "votacao_candidato_munzona_2022_BR.csv": (
                VOT_COLS,
                [["MG", "1", "Presidente", "A", "P1", "6", "6"], ["MG", "1", "Presidente", "B", "P2", "4", "4"]],
            )
        },
    )
    monkeypatch.setattr(
        tse_eleicoes_extractor, "baixar", fake_baixar(tmp_path, {"votacao_candidato_munzona_2022.zip": zip_path})
    )
    saida = tmp_path / "processed"
    saida.mkdir()
    (saida / "presidentes_historico.json").write_text(
        json.dumps([{"id_referencia": "lula-2023", "ano_eleicao": 2022, "data_inicio": "2023-01-01"}]), encoding="utf-8"
    )
    ext = tse_eleicoes_extractor.TSEEleicoesExtractor(processed_dir=saida, raw_dir=tmp_path)
    assert ext.run(anos=[1989, 2022])  # 1989 sem mandato: ignorado
    linhas = list(csv.DictReader((saida / "eleicoes_presidenciais_uf_tse.csv").open(encoding="utf-8")))
    assert [(x["ano_eleicao"], x["uf"], x["votos_vencedor_pct"]) for x in linhas] == [("2022", "MG", "60.0")]


# ----------------------------------------------------------------------------------------------------------
# situação do registro de candidatura
# ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "detalhe,total,situacao,esperado",
    [
        ("INDEFERIDO", "", "INAPTO", "indeferido"),
        ("", "REGISTRO NEGADO ANTES DA ELEIÇÃO", "", "indeferido"),
        ("INDEFERIDO COM RECURSO", "", "APTO", "indeferido"),
        ("CANCELADO", "", "INAPTO", "cancelado"),
        ("", "CASSADO", "", "cassado"),
        ("RENÚNCIA", "", "INAPTO", None),
        ("DEFERIDO", "ELEITO", "APTO", None),
        ("", "", "INAPTO", None),  # INAPTO sem motivo publicado não prova nada
    ],
)
def test_classificar_so_ocorrencias_adversas_explicitas(detalhe, total, situacao, esperado):
    assert tse_candidaturas_extractor.classificar(detalhe, total, situacao) == esperado


def test_candidaturas_so_registra_ocorrencia_adversa(tmp_path, monkeypatch):
    cand = zip_csv(
        tmp_path / "consulta_cand_2010.zip",
        {
            "consulta_cand_2010_BRASIL.csv": (
                CAND_COLS,
                [
                    cand_row(1, "Ana Indeferida", "Ana", DS_DETALHE_SITUACAO_CAND="INDEFERIDO", NR_PROCESSO="123"),
                    cand_row(2, "Bia Deferida", "Bia", DS_DETALHE_SITUACAO_CAND="DEFERIDO", DS_SIT_TOT_TURNO="ELEITO"),
                ],
            )
        },
    )
    monkeypatch.setattr(tse_candidaturas_extractor, "baixar", fake_baixar(tmp_path, {"consulta_cand_2010.zip": cand}))
    saida = tmp_path / "processed"
    saida.mkdir()
    universo = [
        politico("camara:1", "Ana Indeferida", "Ana", camara_id=1),
        politico("camara:2", "Bia Deferida", "Bia", camara_id=2),
    ]
    ext = tse_candidaturas_extractor.TSECandidaturasExtractor(processed_dir=saida, raw_dir=tmp_path)
    registros = ext.run(anos=[2010], universo=universo)
    assert [r["camara_id"] for r in registros] == [1]
    r = registros[0]
    assert r["status_ficha"] == "Declarada: registro indeferido" and r["numero_processo"] == "123"
    assert "Nada Consta" not in json.dumps(registros, ensure_ascii=False)
    assert len(r["tipo_certidao"]) <= 50 and is_trusted(r)


# ----------------------------------------------------------------------------------------------------------
# identidades (cache bruto; CPF nunca vai para os processados)
# ----------------------------------------------------------------------------------------------------------
class HttpFalso:
    def __init__(self):
        self.chamadas = []

    def get_json(self, url, **_):
        self.chamadas.append(url)
        if "camara" in url:
            return {
                "dados": {
                    "nomeCivil": "FULANO DE TAL",
                    "cpf": CPF_B,
                    "dataNascimento": "1980-01-01",
                    "ufNascimento": "SP",
                }
            }
        return {
            "DetalheParlamentar": {
                "Parlamentar": {
                    "IdentificacaoParlamentar": {"NomeCompletoParlamentar": "Sena Dor"},
                    "DadosBasicosParlamentar": {"DataNascimento": "1970-05-05", "UfNaturalidade": "AC"},
                }
            }
        }


def test_identidades_busca_uma_vez_e_usa_cache(tmp_path):
    http = HttpFalso()
    ident = IdentidadesParlamentares(raw_dir=tmp_path, http=http)
    assert ident.enrich([1], [2]) == 2
    assert ident.get("camara:1")["cpf"] == CPF_B and ident.get("senado:2")["cpf"] is None
    assert ident.get("senado:2")["data_nascimento"] == "1970-05-05"
    outra = IdentidadesParlamentares(raw_dir=tmp_path, http=HttpFalso())
    assert outra.enrich([1], [2]) == 0 and outra.http.chamadas == []


def test_carregar_universo_enriquece_e_deduplica_presidentes(tmp_path):
    (tmp_path / "deputados_camara.json").write_text(
        json.dumps([{"camara_id": 1, "nome_eleitoral": "Fulano", "uf": "sp"}] * 2), encoding="utf-8"
    )
    (tmp_path / "senadores_senado.json").write_text(
        json.dumps([{"senado_id": 2, "nome_eleitoral": "Sena", "uf": "AC"}]), encoding="utf-8"
    )
    (tmp_path / "presidentes_historico.json").write_text(
        json.dumps(
            [
                {"nome_civil": "Pres Idente", "nome_eleitoral": "Pres 1", "data_nascimento": "1950-01-01"},
                {"nome_civil": "Pres Idente", "nome_eleitoral": "Pres 2", "data_nascimento": "1950-01-01"},
            ]
        ),
        encoding="utf-8",
    )
    ident = IdentidadesParlamentares(raw_dir=tmp_path, http=HttpFalso())
    universo = tse_core.carregar_universo(tmp_path, ident)
    assert [p.chave for p in universo] == ["camara:1", "senado:2", "presidente:pres idente"]
    dep = universo[0]
    assert dep.nome_civil == "FULANO DE TAL" and dep.cpf == CPF_B and dep.uf == "SP"
    assert dep.nascimento == date(1980, 1, 1) and "cpf" not in dep.identificadores()
