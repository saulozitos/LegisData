"""Testes (somente stdlib) do extrator de presença/participação.

Rodar: python -m unittest discover -s etl/tests -t .
"""

import importlib.util
import sys
import unittest
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _carregar(nome, caminho):
    # Carrega pelo caminho para não executar etl/extractors/__init__.py,
    # que importa extratores dependentes de pandas.
    spec = importlib.util.spec_from_file_location(nome, ROOT / caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pe = _carregar("presenca_extractor", "etl/extractors/presenca_extractor.py")

# Trecho reduzido de uma resposta REAL de ListarPresencasDia (dia 10/06/2025),
# com os 4 rótulos observados. Quebras de linha CRLF e campos com espaços como no original.
XML_PRESENCAS_DIA = (
    '<?xml version="1.0" encoding="utf-8"?>\r\n<dia>\r\n'
    "  <data>10/06/2025 11:40:02</data>\r\n  <qtdeSessoesDia>1</qtdeSessoesDia>\r\n"
    "  <legislatura>57</legislatura>\r\n  <parlamentares>\r\n"
    "    <parlamentar>\r\n      <carteiraParlamentar>10</carteiraParlamentar>\r\n"
    "      <nomeParlamentar>Acácio Favacho-MDB/AP</nomeParlamentar>\r\n"
    "      <siglaPartido>MDB       </siglaPartido>\r\n      <siglaUF>AP</siglaUF>\r\n"
    "      <descricaoFrequenciaDia>Presença</descricaoFrequenciaDia>\r\n"
    "      <justificativa>\r\n      </justificativa>\r\n      <presencaExterna>0</presencaExterna>\r\n"
    "      <sessoesDia>\r\n        <sessaoDia>\r\n          <inicio>10/06/2025 11:55:00</inicio>\r\n"
    "          <descricao>EXTRAORDINÁRIA Nº 101 - 10/06/2025</descricao>\r\n"
    "          <frequencia>Presença</frequencia>\r\n        </sessaoDia>\r\n      </sessoesDia>\r\n"
    "    </parlamentar>\r\n"
    "    <parlamentar>\r\n      <carteiraParlamentar>519</carteiraParlamentar>\r\n"
    "      <nomeParlamentar>Adilson Barroso-PL/SP</nomeParlamentar>\r\n"
    "      <siglaPartido>PL        </siglaPartido>\r\n      <siglaUF>SP</siglaUF>\r\n"
    "      <descricaoFrequenciaDia>Ausência justificada</descricaoFrequenciaDia>\r\n"
    "      <justificativa>Missão Autorizada</justificativa>\r\n      <presencaExterna>0</presencaExterna>\r\n"
    "      <sessoesDia>\r\n        <sessaoDia>\r\n          <inicio>10/06/2025 11:55:00</inicio>\r\n"
    "          <descricao>EXTRAORDINÁRIA Nº 101 - 10/06/2025</descricao>\r\n"
    "          <frequencia>Ausência</frequencia>\r\n        </sessaoDia>\r\n      </sessoesDia>\r\n"
    "    </parlamentar>\r\n"
    "    <parlamentar>\r\n      <carteiraParlamentar>68</carteiraParlamentar>\r\n"
    "      <nomeParlamentar>Aluisio Mendes-Republican/MA</nomeParlamentar>\r\n"
    "      <siglaPartido>Republican</siglaPartido>\r\n      <siglaUF>MA</siglaUF>\r\n"
    "      <descricaoFrequenciaDia>Ausência justificada</descricaoFrequenciaDia>\r\n"
    "      <justificativa>Licença para Tratamento de Saúde</justificativa>\r\n"
    "      <presencaExterna>0</presencaExterna>\r\n      <sessoesDia>\r\n        <sessaoDia>\r\n"
    "          <inicio>10/06/2025 11:55:00</inicio>\r\n"
    "          <descricao>EXTRAORDINÁRIA Nº 101 - 10/06/2025</descricao>\r\n"
    "          <frequencia>Ausência</frequencia>\r\n        </sessaoDia>\r\n      </sessoesDia>\r\n"
    "    </parlamentar>\r\n"
    "    <parlamentar>\r\n      <carteiraParlamentar>71</carteiraParlamentar>\r\n"
    "      <nomeParlamentar>Amanda Gentil-PP/MA</nomeParlamentar>\r\n"
    "      <siglaPartido>PP        </siglaPartido>\r\n      <siglaUF>MA</siglaUF>\r\n"
    "      <descricaoFrequenciaDia>Ausência justificada</descricaoFrequenciaDia>\r\n"
    "      <justificativa>Decisão da Mesa</justificativa>\r\n      <presencaExterna>0</presencaExterna>\r\n"
    "      <sessoesDia>\r\n        <sessaoDia>\r\n          <inicio>10/06/2025 11:55:00</inicio>\r\n"
    "          <descricao>EXTRAORDINÁRIA Nº 101 - 10/06/2025</descricao>\r\n"
    "          <frequencia>Ausência</frequencia>\r\n        </sessaoDia>\r\n      </sessoesDia>\r\n"
    "    </parlamentar>\r\n"
    "    <parlamentar>\r\n      <carteiraParlamentar>493</carteiraParlamentar>\r\n"
    "      <nomeParlamentar>Covatti Filho-PP/RS</nomeParlamentar>\r\n"
    "      <siglaPartido>PP        </siglaPartido>\r\n      <siglaUF>RS</siglaUF>\r\n"
    "      <descricaoFrequenciaDia>Ausência</descricaoFrequenciaDia>\r\n"
    "      <justificativa>\r\n      </justificativa>\r\n      <presencaExterna>0</presencaExterna>\r\n"
    "      <sessoesDia>\r\n        <sessaoDia>\r\n          <inicio>10/06/2025 11:55:00</inicio>\r\n"
    "          <descricao>EXTRAORDINÁRIA Nº 101 - 10/06/2025</descricao>\r\n"
    "          <frequencia>Ausência</frequencia>\r\n        </sessaoDia>\r\n      </sessoesDia>\r\n"
    "    </parlamentar>\r\n"
    "  </parlamentares>\r\n</dia>"
).encode("utf-8")

# Trecho real (estrutura) de ObterDeputados: matricula == carteiraParlamentar.
XML_OBTER_DEPUTADOS = (
    '<?xml version="1.0" encoding="utf-8"?>\r\n<deputados>\r\n'
    "  <deputado>\r\n    <ideCadastro>204379</ideCadastro>\r\n    <codOrcamento>3897</codOrcamento>\r\n"
    "    <condicao>Titular</condicao>\r\n    <matricula>10</matricula>\r\n"
    "    <idParlamentar>1661281</idParlamentar>\r\n    <nome>NOME CIVIL</nome>\r\n"
    "    <nomeParlamentar>Acácio Favacho</nomeParlamentar>\r\n    <uf>AP</uf>\r\n"
    "    <partido>MDB</partido>\r\n  </deputado>\r\n"
    "  <deputado>\r\n    <ideCadastro>221328</ideCadastro>\r\n    <codOrcamento></codOrcamento>\r\n"
    "    <matricula>519</matricula>\r\n    <nomeParlamentar>Adilson Barroso</nomeParlamentar>\r\n"
    "    <uf>SP</uf>\r\n  </deputado>\r\n"
    "  <deputado>\r\n    <ideCadastro></ideCadastro>\r\n    <matricula>999</matricula>\r\n"
    "    <uf>SP</uf>\r\n  </deputado>\r\n"
    "</deputados>"
).encode("utf-8")


class TestXmlCamara(unittest.TestCase):
    def test_parse_presencas_dia(self):
        legislatura, regs = pe.parse_presencas_dia_xml(XML_PRESENCAS_DIA)
        self.assertEqual(legislatura, "57")
        self.assertEqual(len(regs), 5)
        primeiro = regs[0]
        self.assertEqual(primeiro["carteira"], "10")
        self.assertEqual(primeiro["nome_parlamentar"], "Acácio Favacho")
        self.assertEqual(primeiro["sigla_partido"], "MDB")  # espaços à direita removidos
        self.assertEqual(primeiro["uf"], "AP")
        self.assertIsNone(primeiro["justificativa"])  # só espaços/quebra -> None
        self.assertEqual(primeiro["sessoes"][0]["frequencia"], "Presença")
        self.assertEqual(regs[1]["justificativa"], "Missão Autorizada")

    def test_nome_com_hifen_no_nome(self):
        xml = ("<dia><parlamentares><parlamentar><carteiraParlamentar>1</carteiraParlamentar>"
               "<nomeParlamentar>Ana Maria-Silva-PT/SP</nomeParlamentar>"
               "<descricaoFrequenciaDia>Presença</descricaoFrequenciaDia>"
               "</parlamentar></parlamentares></dia>").encode("utf-8")
        _, regs = pe.parse_presencas_dia_xml(xml)
        self.assertEqual(regs[0]["nome_parlamentar"], "Ana Maria-Silva")

    def test_parse_obter_deputados(self):
        mapa = pe.parse_obter_deputados_xml(XML_OBTER_DEPUTADOS)
        self.assertEqual(mapa["10"]["camara_id"], 204379)
        self.assertEqual(mapa["519"]["uf"], "SP")
        self.assertNotIn("999", mapa)  # sem ideCadastro -> ignorado

    def test_dias_com_sessao(self):
        eventos = [
            {"dataHoraInicio": "2025-06-10T13:55", "situacao": "Encerrada", "orgaos": [{"sigla": "PLEN"}]},
            {"dataHoraInicio": "2025-06-10T18:00", "situacao": "Encerrada", "orgaos": [{"sigla": "PLEN"}]},
            {"dataHoraInicio": "2025-06-11T14:07", "situacao": "Cancelada", "orgaos": [{"sigla": "PLEN"}]},
            {"dataHoraInicio": "2025-06-12T09:11", "situacao": "Encerrada", "orgaos": [{"sigla": "CCJC"}]},
        ]
        self.assertEqual(pe.dias_com_sessao_deliberativa(eventos), [date(2025, 6, 10)])


class TestMapeamentoStatus(unittest.TestCase):
    def test_camara_rotulos_observados(self):
        _, regs = pe.parse_presencas_dia_xml(XML_PRESENCAS_DIA)
        obtidos = [pe.mapear_status_camara(r["descricao_frequencia"], r["justificativa"]) for r in regs]
        self.assertEqual(obtidos, [
            pe.PRESENTE, pe.MISSAO_OFICIAL, pe.LICENCA_MEDICA,
            pe.AUSENCIA_JUSTIFICADA, pe.AUSENCIA_NAO_JUSTIFICADA,
        ])

    def test_camara_rotulo_desconhecido(self):
        self.assertIsNone(pe.mapear_status_camara("Qualquer outra coisa", None))
        self.assertIsNone(pe.mapear_status_camara("", None))

    def test_camara_sem_acento_e_caixa(self):
        self.assertEqual(pe.mapear_status_camara("PRESENCA", None), pe.PRESENTE)
        self.assertEqual(pe.mapear_status_camara("ausencia", ""), pe.AUSENCIA_NAO_JUSTIFICADA)

    def test_senado_siglas(self):
        casos = {
            "Sim": pe.PARTICIPOU_VOTACAO, "Não": pe.PARTICIPOU_VOTACAO, "Abstenção": pe.PARTICIPOU_VOTACAO,
            "Votou": pe.PARTICIPOU_VOTACAO,
            "P-NRV": pe.PRESENTE_SEM_VOTO, "Presidente (art. 51 RISF)": pe.PRESENTE_SEM_VOTO,
            "MIS": pe.MISSAO_OFICIAL, "LS": pe.LICENCA_MEDICA,
            "AP": pe.AUSENCIA_JUSTIFICADA, "LP": pe.AUSENCIA_JUSTIFICADA,
            "NCom": pe.AUSENCIA_NAO_JUSTIFICADA,
            "AFO": None, "NH": None, None: None, "XYZ": None,
        }
        for sigla, esperado in casos.items():
            with self.subTest(sigla=sigla):
                self.assertEqual(pe.mapear_voto_senado(sigla), esperado)


class TestAgregacaoSenado(unittest.TestCase):
    def test_uma_linha_por_senador_e_sessao(self):
        votacoes = [
            {"codigoSessao": 1, "dataSessao": "2025-06-10", "votos": [
                {"codigoParlamentar": 10, "siglaVotoParlamentar": "Votou", "nomeParlamentar": "A"},
                {"codigoParlamentar": 20, "siglaVotoParlamentar": "MIS",
                 "descricaoVotoParlamentar": "Missão da Casa no País/exterior"},
                {"codigoParlamentar": 30, "siglaVotoParlamentar": "P-NRV"},
                {"codigoParlamentar": 40, "siglaVotoParlamentar": "AFO"},
            ]},
            {"codigoSessao": 1, "dataSessao": "2025-06-10", "votos": [
                {"codigoParlamentar": 10, "siglaVotoParlamentar": "NCom"},
                {"codigoParlamentar": 20, "siglaVotoParlamentar": "MIS",
                 "descricaoVotoParlamentar": "Missão da Casa no País/exterior"},
                {"codigoParlamentar": 30, "siglaVotoParlamentar": "Sim"},
            ]},
            {"codigoSessao": 2, "dataSessao": "2025-06-11", "votos": [
                {"codigoParlamentar": 10, "siglaVotoParlamentar": "NCom",
                 "descricaoVotoParlamentar": "Não Compareceu"},
            ]},
        ]
        regs, descartes = pe.agregar_votacoes_senado(votacoes)
        por = {(r["senado_id"], r["codigo_sessao"]): r for r in regs}
        self.assertEqual(len(regs), 4)
        self.assertEqual(por[(10, 1)]["status"], pe.PARTICIPOU_VOTACAO)  # votou em ao menos uma
        self.assertEqual(por[(10, 1)]["votacoes_nominais"], 2)
        self.assertEqual(por[(10, 1)]["votos_registrados"], 1)
        self.assertEqual(por[(20, 1)]["status"], pe.MISSAO_OFICIAL)
        self.assertEqual(por[(20, 1)]["justificativa"], "Missão da Casa no País/exterior (MIS)")
        self.assertEqual(por[(30, 1)]["status"], pe.PARTICIPOU_VOTACAO)
        self.assertEqual(por[(10, 2)]["status"], pe.AUSENCIA_NAO_JUSTIFICADA)
        self.assertEqual(descartes, Counter({"AFO": 1}))

    def test_licencas_objeto_unico(self):
        payload = {"LicencaParlamentar": {"Parlamentar": {"Codigo": "5672", "Licencas": {"Licenca": {
            "DataInicio": "2025-10-20", "DataFim": "2025-10-20",
            "SiglaTipoAfastamento": "LICENCA_ATIVIDADE_PARLAMENTAR",
            "DescricaoTipoAfastamento": "Missão política ou cultural de interesse parlamentar"}}}}}
        lic = pe.parse_licencas_senado(payload)
        self.assertEqual(len(lic), 1)
        self.assertEqual(lic[0]["senado_id"], 5672)


if __name__ == "__main__":
    unittest.main()
