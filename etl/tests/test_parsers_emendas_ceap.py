"""Testes dos parsers puros (stdlib apenas: não importam pandas, requests nem o backend).

Rodar a partir da raiz do repositório:
    python -m unittest discover -s etl/tests -t .
"""

import csv
import io
import unittest
from datetime import date
from decimal import Decimal

from etl.parsers.ceap import chave_camara, normalizar_item_senado, normalizar_linha_camara, parse_data
from etl.parsers.emendas import (
    ENCODING_EMENDAS_CSV,
    autor_identificado,
    eh_emenda_individual,
    filtrar_linhas,
    validar_cabecalho,
)
from etl.parsers.nomes import (
    casar_nome,
    destinos_por_autor,
    indexar_parlamentares,
    normalizar_nome,
    propor_mapa,
    resolver_mapa,
    sigla_uf,
    uf_predominante,
    ufs_parlamentares,
)
from etl.parsers.valores import parse_valor_br, parse_valor_ponto, texto_ou_none, truncar

# Trecho no formato real do EmendasParlamentares.csv (cabeçalho completo, linhas
# reduzidas a exemplos de cada tipo observado no arquivo de 07/10/2026).
CABECALHO = (
    '"Código da Emenda";"Ano da Emenda";"Tipo de Emenda";"Código do Autor da Emenda";'
    '"Nome do Autor da Emenda";"Número da emenda";"Localidade de aplicação do recurso";'
    '"Código Município IBGE";"Município";"Código UF IBGE";"UF";"Região";"Código Função";'
    '"Nome Função";"Código Subfunção";"Nome Subfunção";"Código Programa";"Nome Programa";'
    '"Código Ação";"Nome Ação";"Código Plano Orçamentário";"Nome Plano Orçamentário";'
    '"Valor Empenhado";"Valor Liquidado";"Valor Pago";"Valor Restos A Pagar Inscritos";'
    '"Valor Restos A Pagar Cancelados";"Valor Restos A Pagar Pagos"'
)


def _linha(codigo, ano, tipo, cod_autor, autor, local, ibge, uf, funcao, emp, liq, pago):
    campos = [codigo, ano, tipo, cod_autor, autor, "0001", local, ibge, "X", "35", uf, "Sudeste",
              "10", funcao, "301", "Atenção básica", "5019", "P", "2E89", "A", "0000", "PO", emp, liq, pago,
              "0,00", "0,00", "0,00"]
    return ";".join(f'"{c}"' for c in campos)


FIXTURE_CSV = "\r\n".join([
    CABECALHO,
    _linha("202412340001", "2024", "Emenda Individual - Transferências com Finalidade Definida", "1234",
           "FULANO DE TAL", "SÃO PAULO - SP", "3550308", "SÃO PAULO", "Saúde", "1.234.567,89", "1.000,00", "999,99"),
    _linha("202412340002", "2024", "Emenda Individual - Transferências Especiais", "1234",
           "FULANO DE TAL", "MÚLTIPLO", "Sem informação", "SÃO PAULO", "Encargos especiais", "500000,00", "0,00", "0,00"),
    _linha("Sem informação", "2016", "Emenda de Bancada", "S/I", "Sem informação",
           "LAGES - SC", "4209300", "SANTA CATARINA", "Educação", "160000,00", "0,00", "0,00"),
    _linha("Sem informação", "2016", "Emenda de Comissão", "-99", "RELATOR GERAL",
           "QUADRA - SP", "3541653", "SÃO PAULO", "Educação", "230210,00", "230210,00", "230210,00"),
    _linha("Sem informação", "2016", "Emenda de Relator", "S/I", "Sem informação",
           "PARANÁ (UF)", "Sem informação", "PARANÁ", "Saúde", "146035380,00", "146035380,00", "146035380,00"),
    _linha("Sem informação", "2014", "Emenda Individual - Transferências com Finalidade Definida", "S/I",
           "Sem informação", "SELVÍRIA - MS", "5007802", "MATO GROSSO DO SUL", "Saúde", "149600,00", "0,00", "0,00"),
]) + "\r\n"


def _ler_fixture():
    # Simula a leitura do arquivo real: bytes latin-1 -> texto
    bruto = FIXTURE_CSV.encode(ENCODING_EMENDAS_CSV)
    return list(csv.DictReader(io.StringIO(bruto.decode(ENCODING_EMENDAS_CSV)), delimiter=";"))


class TestValoresBR(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(parse_valor_br("149600,00"), Decimal("149600.00"))
        self.assertEqual(parse_valor_br("1.234.567,89"), Decimal("1234567.89"))
        self.assertEqual(parse_valor_br("R$ 1.000,5"), Decimal("1000.5"))
        self.assertEqual(parse_valor_br("-90,10"), Decimal("-90.10"))
        self.assertEqual(parse_valor_br("1.234.567"), Decimal("1234567"))
        self.assertEqual(parse_valor_br("0,00"), Decimal("0"))

    def test_ausente_nao_vira_zero(self):
        for v in ("", "Sem informação", "S/I", None, float("nan")):
            self.assertIsNone(parse_valor_br(v))

    def test_invalido_levanta(self):
        with self.assertRaises(ValueError):
            parse_valor_br("abc")

    def test_ponto_decimal(self):
        self.assertEqual(parse_valor_ponto("1148.7"), Decimal("1148.7"))
        self.assertEqual(parse_valor_ponto(266.64), Decimal("266.64"))
        self.assertEqual(parse_valor_ponto(1500), Decimal(1500))
        self.assertIsNone(parse_valor_ponto(""))

    def test_texto_e_truncar(self):
        self.assertIsNone(texto_ou_none("  Sem informação "))
        self.assertEqual(texto_ou_none(" X "), "X")
        self.assertEqual(truncar("abcdef", 4), "abc…")
        self.assertEqual(len(truncar("a" * 200, 150)), 150)
        self.assertEqual(truncar("abc", 4), "abc")
        self.assertIsNone(truncar(None, 4))


class TestFiltroEmendas(unittest.TestCase):
    def test_tipos(self):
        self.assertTrue(eh_emenda_individual("Emenda Individual - Transferências Especiais"))
        self.assertTrue(eh_emenda_individual("Emenda Individual - Transferências com Finalidade Definida"))
        for t in ("Emenda de Bancada", "Emenda de Comissão", "Emenda de Relator", "", None):
            self.assertFalse(eh_emenda_individual(t))

    def test_autor(self):
        self.assertTrue(autor_identificado("1234", "FULANO"))
        self.assertFalse(autor_identificado("S/I", "Sem informação"))
        self.assertFalse(autor_identificado("-99", "RELATOR GERAL"))
        self.assertFalse(autor_identificado("1234", "Sem informação"))

    def test_fixture_so_individuais_com_autor(self):
        linhas = _ler_fixture()
        self.assertEqual(validar_cabecalho(list(linhas[0].keys())), [])
        regs = list(filtrar_linhas(linhas))
        self.assertEqual(len(regs), 2)
        self.assertEqual({r["codigo_emenda"] for r in regs}, {"202412340001", "202412340002"})
        r = regs[0]
        self.assertEqual(r["valor_empenhado"], "1234567.89")
        self.assertEqual(r["valor_liquidado"], "1000.00")
        self.assertEqual(r["valor_pago"], "999.99")
        self.assertEqual(r["municipio_ibge"], "3550308")
        self.assertEqual(r["localidade_destino"], "SÃO PAULO - SP")
        self.assertEqual(r["uf"], "SÃO PAULO")
        self.assertEqual(r["ano"], 2024)
        self.assertTrue(r["fonte_url"].startswith("https://portaldatransparencia.gov.br/"))
        self.assertIsNone(regs[1]["municipio_ibge"])  # "Sem informação" -> None

    def test_cabecalho_faltando(self):
        self.assertIn("Valor Pago", validar_cabecalho(["Código da Emenda", "Ano da Emenda"]))


DEPUTADOS = [
    {"camara_id": 1, "nome_eleitoral": "Fulano de Tal", "nome_civil": "Fulano de Tal Silva", "uf": "SP"},
    {"camara_id": 2, "nome_eleitoral": "José Silva", "nome_civil": "José da Silva", "uf": "MG"},
    {"camara_id": 3, "nome_eleitoral": "Jose Silva", "nome_civil": "José Silva Neto", "uf": "BA"},  # homônimo
    {"camara_id": 4, "nome_eleitoral": "Dr. Beltrano", "nome_civil": "Beltrano Souza", "uf": "RJ"},
    {"camara_id": 4, "nome_eleitoral": "Dr. Beltrano", "nome_civil": "Beltrano Souza", "uf": "RJ"},  # repetido no JSON
    {"camara_id": 5, "nome_eleitoral": "Maria Lima", "nome_civil": "Maria Lima", "uf": "MA"},
]
SENADORES = [
    {"senado_id": 900, "nome_eleitoral": "Ciclano", "nome_civil": "Ciclano Pereira", "uf": "AP"},
    {"senado_id": 901, "nome_eleitoral": "Maria Lima", "nome_civil": "Maria Lima", "uf": "PI"},  # homônimo entre casas
]


class TestMatcherNomes(unittest.TestCase):
    def setUp(self):
        self.indice = indexar_parlamentares(DEPUTADOS, SENADORES)
        self.ufs = ufs_parlamentares(DEPUTADOS, SENADORES)

    def test_normalizacao(self):
        self.assertEqual(normalizar_nome("  José  da Silva "), "JOSE DA SILVA")
        self.assertEqual(normalizar_nome("ABEL MESQUITA JR."), "ABEL MESQUITA JR")
        self.assertEqual(normalizar_nome("Dr. Beltrano"), "DR BELTRANO")

    def test_exato_unico(self):
        self.assertEqual(casar_nome("FULANO DE TAL", self.indice), ("camara", 1))
        self.assertEqual(casar_nome("FULANO DE TAL SILVA", self.indice), ("camara", 1))
        self.assertEqual(casar_nome("CICLANO PEREIRA", self.indice), ("senado", 900))
        # Mesmo id repetido no JSON não é ambiguidade
        self.assertEqual(casar_nome("DR BELTRANO", self.indice), ("camara", 4))

    def test_homonimos_ficam_sem_vinculo(self):
        self.assertIsNone(casar_nome("JOSE SILVA", self.indice))   # 2 e 3
        self.assertIsNone(casar_nome("MARIA LIMA", self.indice))   # deputada e senadora

    def test_sem_substring_nem_titulo(self):
        self.assertIsNone(casar_nome("FULANO", self.indice))
        self.assertIsNone(casar_nome("BELTRANO", self.indice))  # não remove "Dr."
        self.assertIsNone(casar_nome("FULANO DE TAL SILVA JUNIOR", self.indice))

    def test_uf(self):
        self.assertEqual(sigla_uf("SÃO PAULO"), "SP")
        self.assertEqual(sigla_uf("Múltiplo"), None)
        self.assertEqual(sigla_uf("Sem informação"), None)
        self.assertEqual(uf_predominante(["SÃO PAULO", "SÃO PAULO", "BAHIA", "Múltiplo"]), "SP")
        self.assertIsNone(uf_predominante(["SÃO PAULO", "BAHIA"]))  # empate

    def test_propor_e_resolver(self):
        autores = [("1", "FULANO DE TAL"), ("2", "JOSE SILVA"), ("3", "CICLANO"), ("4", "NINGUEM")]
        destinos = {("1", "FULANO DE TAL"): "SP", ("3", "CICLANO"): "BA"}  # Ciclano é do AP
        linhas = propor_mapa(autores, self.indice, self.ufs, destinos)
        por_nome = {l["nome_autor"]: l for l in linhas}
        self.assertEqual(por_nome["FULANO DE TAL"]["camara_id"], "1")
        self.assertEqual(por_nome["JOSE SILVA"]["observacao"], "ambiguo")
        self.assertEqual(por_nome["CICLANO"]["observacao"], "uf_divergente")
        self.assertEqual(por_nome["CICLANO"]["senado_id"], "")
        self.assertEqual(por_nome["NINGUEM"]["observacao"], "sem_correspondencia")
        self.assertTrue(all(l["revisado"] == "nao" for l in linhas))

        usar, stats = resolver_mapa(linhas, self.indice, self.ufs, destinos)
        self.assertEqual(usar, {("1", "FULANO DE TAL"): ("camara", 1)})
        self.assertEqual(stats["automatico"], 1)
        self.assertEqual(stats["sem_vinculo"], 3)

    def test_resolver_respeita_revisao(self):
        linhas = [
            # editado à mão sem revisar: id não confere com o casamento exato -> ignorado
            {"codigo_autor_siafi": "9", "nome_autor": "FULANO DE TAL", "camara_id": "2", "senado_id": "", "revisado": "nao"},
            # homônimo resolvido por uma pessoa -> usado
            {"codigo_autor_siafi": "8", "nome_autor": "JOSE SILVA", "camara_id": "3", "senado_id": "", "revisado": "sim"},
            # rejeitado explicitamente
            {"codigo_autor_siafi": "7", "nome_autor": "CICLANO", "camara_id": "", "senado_id": "900", "revisado": "rejeitado"},
            # os dois ids preenchidos -> inválido
            {"codigo_autor_siafi": "6", "nome_autor": "X", "camara_id": "1", "senado_id": "900", "revisado": "sim"},
        ]
        usar, stats = resolver_mapa(linhas, self.indice, self.ufs)
        self.assertEqual(usar, {("8", "JOSE SILVA"): ("camara", 3)})
        self.assertEqual(stats["divergente"], 1)
        self.assertEqual(stats["rejeitado"], 1)
        self.assertEqual(stats["sem_vinculo"], 1)

    def test_destinos_por_autor(self):
        regs = list(filtrar_linhas(_ler_fixture()))
        self.assertEqual(destinos_por_autor(regs), {("1234", "FULANO DE TAL"): "SP"})


class TestCeap(unittest.TestCase):
    CAB = ["txNomeParlamentar", "cpf", "ideCadastro", "numAno", "numMes", "txtDescricao", "txtFornecedor",
           "txtCNPJCPF", "datEmissao", "vlrLiquido", "numParcela", "txtPassageiro", "txtTrecho",
           "ideDocumento", "urlDocumento"]

    def _linha(self, **kw):
        base = dict.fromkeys(self.CAB, "")
        base.update(kw)
        return base

    def test_linha_deputado(self):
        ln = self._linha(ideCadastro="204554", numAno="2024", numMes="2", txtDescricao="COMBUSTÍVEIS",
                         txtFornecedor="POSTO X", txtCNPJCPF="00.000.000/0001-00", datEmissao="2024-02-07T00:00:00",
                         vlrLiquido="1148.7", numParcela="0", ideDocumento="7696122",
                         urlDocumento="https://www.camara.leg.br/cota-parlamentar/documentos/publ/1/2024/7696122.pdf")
        r = normalizar_linha_camara(ln, "https://www.camara.leg.br/cotas/Ano-2024.csv.zip")
        self.assertEqual(r["parlamentar_id"], 204554)
        self.assertEqual(r["valor_liquido"], Decimal("1148.7"))
        self.assertEqual(r["data_emissao"], date(2024, 2, 7))
        self.assertEqual(r["mes"], 2)
        self.assertTrue(r["url_documento"].endswith("7696122.pdf"))
        self.assertEqual(r["chave"][:2], ("camara", "7696122"))

    def test_lideranca_ignorada(self):
        ln = self._linha(txNomeParlamentar="LID.GOV-CD", ideCadastro="", numAno="2024", vlrLiquido="10")
        self.assertIsNone(normalizar_linha_camara(ln, "u"))

    def test_chave_distingue_bilhetes_do_mesmo_documento(self):
        a = self._linha(ideDocumento="1", txtPassageiro="A", txtTrecho="BSB/GRU", vlrLiquido="100")
        b = self._linha(ideDocumento="1", txtPassageiro="B", txtTrecho="BSB/GRU", vlrLiquido="100")
        self.assertNotEqual(chave_camara(a), chave_camara(b))
        self.assertEqual(chave_camara(a), chave_camara(dict(a)))
        self.assertIsNone(chave_camara(self._linha(ideDocumento="")))

    def test_senado(self):
        item = {"id": 2234156, "tipoDocumento": "Nota Fiscal Eletrônica", "ano": 2024, "mes": 7, "codSenador": 5990,
                "nomeSenador": "X", "tipoDespesa": "Aluguel", "cpfCnpj": "06.981.180/0001-16",
                "fornecedor": "CEMIG", "documento": "1", "data": "2024-07-23", "detalhamento": None,
                "valorReembolsado": 266.64}
        r = normalizar_item_senado(item, "u")
        self.assertEqual(r["parlamentar_id"], 5990)
        self.assertEqual(r["valor_liquido"], Decimal("266.64"))
        self.assertEqual(r["chave"], ("senado", "2234156"))
        self.assertIsNone(r["url_documento"])
        self.assertEqual(r["data_emissao"], date(2024, 7, 23))

    def test_data_implausivel_descartada(self):
        self.assertIsNone(parse_data("0204-05-10"))  # visto na API do Senado (2024)
        self.assertIsNone(parse_data(""))
        self.assertEqual(parse_data("10/05/2024"), date(2024, 5, 10))


class TestSemDependenciasPesadas(unittest.TestCase):
    def test_parsers_nao_importam_pandas(self):
        import sys
        import etl.parsers.ceap, etl.parsers.emendas, etl.parsers.nomes, etl.parsers.valores  # noqa: E401,F401
        self.assertNotIn("pandas", sys.modules)


if __name__ == "__main__":
    unittest.main()
