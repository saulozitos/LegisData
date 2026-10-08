"""Testes das funções puras do extrator oficial do TSE (somente stdlib)."""
import importlib.util
import io
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path

# Evita depender de etl.config (que cria diretórios) e de etl/extractors/__init__.py
# (que importa pandas): carrega o módulo diretamente pelo caminho do arquivo.
_cfg = types.ModuleType("etl.config")
_cfg.DEFAULT_USER_AGENT = "LegisDataBot/1.0 (testes)"
_cfg.PROCESSED_DATA_DIR = Path(".")
_cfg.RAW_DATA_DIR = Path(".")
sys.modules.setdefault("etl", types.ModuleType("etl"))
sys.modules["etl.config"] = _cfg

_MOD = Path(__file__).resolve().parents[1] / "extractors" / "tse_oficial_extractor.py"
_spec = importlib.util.spec_from_file_location("tse_oficial_extractor", _MOD)
tse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tse)

documento_publicavel = tse.documento_publicavel
indexar_unicos = tse.indexar_unicos
ler_csv_tse = tse.ler_csv_tse
limpar = tse.limpar
normalizar_nome = tse.normalizar_nome
valor_br = tse.valor_br


class TestNormalizacao(unittest.TestCase):
    def test_nome_sem_acento_e_espacos(self):
        self.assertEqual(normalizar_nome("  Flávio  Nantes Bolsonaro "), "FLAVIO NANTES BOLSONARO")
        self.assertEqual(normalizar_nome("José Renan Vasconcelos Calheiros"), "JOSE RENAN VASCONCELOS CALHEIROS")
        self.assertEqual(normalizar_nome(None), "")

    def test_valor_br(self):
        self.assertEqual(valor_br("1.234.567,89"), Decimal("1234567.89"))
        self.assertEqual(valor_br("194,65"), Decimal("194.65"))
        self.assertIsNone(valor_br("#NULO"))
        self.assertIsNone(valor_br("#NULO#"))
        self.assertIsNone(valor_br("-1"))
        self.assertIsNone(valor_br("abc"))

    def test_limpar_nulos_do_tse(self):
        self.assertIsNone(limpar("#NULO"))
        self.assertIsNone(limpar("#NE"))
        self.assertEqual(limpar(" APTO "), "APTO")


class TestPrivacidade(unittest.TestCase):
    def test_cpf_de_pessoa_fisica_nao_e_publicado(self):
        self.assertIsNone(documento_publicavel("123.456.789-09"))
        self.assertIsNone(documento_publicavel("12345678909"))

    def test_cnpj_e_mantido(self):
        self.assertEqual(documento_publicavel("47.536.544/0001-36"), "47536544000136")


class TestVinculo(unittest.TestCase):
    def test_chaves_ambiguas_sao_descartadas(self):
        idx = indexar_unicos([
            (("PEDRO DA SILVA", "SP", "5"), "1"),
            (("PEDRO DA SILVA", "SP", "5"), "2"),   # homônimo -> descartado
            (("MARIA SOUZA", "RJ", "5"), "3"),
            (("MARIA SOUZA", "RJ", "5"), "3"),     # repetição do mesmo valor é ok
        ])
        self.assertNotIn(("PEDRO DA SILVA", "SP", "5"), idx)
        self.assertEqual(idx[("MARIA SOUZA", "RJ", "5")], "3")


class TestCsv(unittest.TestCase):
    def test_leitura_latin1_ponto_e_virgula(self):
        conteudo = (
            '"SQ_CANDIDATO";"NM_CANDIDATO";"VR_RECEITA";"TP_PRESTACAO_CONTAS"\r\n'
            '"10001";"CONCEIÇÃO ARAÚJO";"1.000,50";"FINAL"\r\n'
        ).encode("latin-1")
        linhas = list(ler_csv_tse(io.BytesIO(conteudo)))
        self.assertEqual(linhas[0]["NM_CANDIDATO"], "CONCEIÇÃO ARAÚJO")
        self.assertEqual(valor_br(linhas[0]["VR_RECEITA"]), Decimal("1000.50"))


if __name__ == "__main__":
    unittest.main()
