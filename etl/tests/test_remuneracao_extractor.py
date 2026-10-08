"""Testes (somente stdlib) de remuneração, subsídios e vínculos com mandato."""

import importlib.util
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _carregar(nome, caminho):
    spec = importlib.util.spec_from_file_location(nome, ROOT / caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rx = _carregar("remuneracao_extractor", "etl/extractors/remuneracao_extractor.py")
subsidios = _carregar("subsidios", "backend/app/core/subsidios.py")
from etl import vinculos  # noqa: E402


def _linha(nome, seq, folha, **valores):
    base = {c: "0,00" for c in rx.CAMPOS_VALOR}
    base.update({"nome": nome, "sequencial": seq, "ano": 2025, "mes": 12, "tipo_folha": folha})
    base.update(valores)
    return base


class TestValorBR(unittest.TestCase):
    def test_formatos(self):
        casos = {
            "46.366,19": Decimal("46366.19"),
            "-7.600,54": Decimal("-7600.54"),
            "0,00": Decimal("0"),
            "1.234.567,89": Decimal("1234567.89"),
            "R$ 29.013,83": Decimal("29013.83"),
            "(10,50)": Decimal("-10.50"),
            "": Decimal("0"),
            None: Decimal("0"),
            "5": Decimal("5"),
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(rx.parse_valor_br(entrada), esperado)

    def test_invalido(self):
        with self.assertRaises(ValueError):
            rx.parse_valor_br("abc")


class TestAgregacaoFolhasSenado(unittest.TestCase):
    # Valores reais publicados para 12/2025 (folha Normal + Suplementar com 13º).
    LINHAS = [
        _linha("ALAN RICK MIRANDA", 3866394, "Normal", remuneracao_basica="46.366,19",
               previdencia="-7.600,54", imposto_renda="-9.751,82", remuneracao_liquida="29.013,83"),
        _linha("ALAN RICK MIRANDA", 3866394, "Suplementar", gratificacao_natalina="5.830,74",
               remuneracao_liquida="5.830,74", auxilios="100,00"),
        _linha("FULANO HOMONIMO", 1, "Normal", remuneracao_basica="10,00", remuneracao_liquida="10,00"),
        _linha("FULANO HOMONIMO", 2, "Normal", remuneracao_basica="20,00", remuneracao_liquida="20,00"),
        _linha("SERVIDOR QUALQUER", 9, "Normal", remuneracao_basica="1,00", remuneracao_liquida="1,00"),
    ]

    def test_soma_folhas_por_pessoa_mes(self):
        alvo = {"ALAN RICK MIRANDA": 5672, "FULANO HOMONIMO": 1}
        regs, stats = rx.agregar_folhas_senado(self.LINHAS, alvo)
        self.assertEqual(len(regs), 1)
        r = regs[0]
        self.assertEqual(r["senado_id"], 5672)
        self.assertEqual(Decimal(r["salario_bruto"]), Decimal("52196.93"))
        self.assertEqual(Decimal(r["descontos_obrigatorios"]), Decimal("-17352.36"))
        self.assertEqual(Decimal(r["salario_liquido"]), Decimal("34844.57"))
        self.assertEqual(Decimal(r["outros_beneficios"]), Decimal("100.00"))
        self.assertEqual([f["tipo_folha"] for f in r["folhas"]], ["Normal", "Suplementar"])
        self.assertEqual(stats["descartado_homonimo"], 1)
        self.assertNotIn("aviso_liquido_nao_confere", stats)

    def test_vinculo_por_nome_normalizado(self):
        linhas = [_linha("JOSÉ DA SILVA", 7, "Normal", remuneracao_basica="1,00", remuneracao_liquida="1,00")]
        regs, _ = rx.agregar_folhas_senado(linhas, {vinculos.normalizar("José da  Silva"): 99})
        self.assertEqual(regs[0]["senado_id"], 99)

    def test_liquido_confere_com_composicao(self):
        f = rx.resumir_folha(self.LINHAS[0])
        self.assertTrue(f["liquido_confere"])

    def test_meses(self):
        self.assertEqual(rx.meses((2025, 11), (2026, 2)), [(2025, 11), (2025, 12), (2026, 1), (2026, 2)])


class TestSubsidios(unittest.TestCase):
    def test_vigencias_dl_172_2022(self):
        casos = [
            (date(2022, 12, 31), 33763.00),
            (date(2023, 1, 1), 39293.32),
            (date(2023, 3, 31), 39293.32),
            (date(2023, 4, 1), 41650.92),
            (date(2024, 1, 31), 41650.92),
            (date(2024, 2, 1), 44008.52),
            (date(2025, 2, 1), 46366.19),
            (date(2026, 10, 8), 46366.19),
        ]
        for dia, valor in casos:
            with self.subTest(dia=dia):
                self.assertEqual(subsidios.subsidio_vigente("DEPUTADO_FEDERAL", dia)["valor_mensal"], valor)
        self.assertEqual(subsidios.subsidio_vigente("PRESIDENTE", date(2020, 1, 1))["valor_mensal"], 30934.70)
        self.assertIsNone(subsidios.subsidio_vigente("GOVERNADOR", date(2025, 1, 1)))
        s = subsidios.subsidio_vigente("SENADOR", date(2025, 6, 1))
        self.assertIn("Decreto Legislativo nº 172", s["ato_normativo"])
        self.assertTrue(s["fonte_url"].startswith("https://www2.camara.leg.br/legin/"))


class TestVinculoMandato(unittest.TestCase):
    MANDATOS = [
        ("m1", date(2019, 2, 1), date(2023, 1, 31)),
        ("m2", date(2023, 2, 1), date(2027, 1, 31)),
    ]

    def test_mandato_na_data(self):
        self.assertEqual(vinculos.mandato_na_data(self.MANDATOS, date(2023, 1, 31)), "m1")
        self.assertEqual(vinculos.mandato_na_data(self.MANDATOS, date(2023, 2, 1)), "m2")
        self.assertIsNone(vinculos.mandato_na_data(self.MANDATOS, date(2018, 5, 1)))
        self.assertEqual(vinculos.mandato_na_data([("x", date(2023, 2, 1), None)], date(2030, 1, 1)), "x")

    def test_mandato_no_mes(self):
        self.assertEqual(vinculos.mandato_no_mes(self.MANDATOS, 2023, 1), "m1")
        self.assertEqual(vinculos.mandato_no_mes(self.MANDATOS, 2023, 2), "m2")
        self.assertIsNone(vinculos.mandato_no_mes(self.MANDATOS, 2027, 3))

    def test_indice_unico(self):
        idx = vinculos.indice_unico([(("A", "SP"), 1), (("B", "RJ"), 2), (("B", "RJ"), 3), (("A", "SP"), 1)])
        self.assertEqual(idx, {("A", "SP"): 1})


if __name__ == "__main__":
    unittest.main()
