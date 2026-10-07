import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings, PROCESSED_DATA_DIR


class LegisDataAPITestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_root_endpoint(self):
        """Verifica se o endpoint raiz de health check responde 200 OK com metadados corretos."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "online")
        self.assertEqual(data.get("service"), settings.PROJECT_NAME)

    def test_openapi_schema(self):
        """Verifica se o esquema OpenAPI é gerado corretamente sem erros de validação."""
        response = self.client.get(f"{settings.API_V1_STR}/openapi.json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertIn("openapi", schema)
        self.assertIn("paths", schema)
        self.assertIn(f"{settings.API_V1_STR}/politicians/presidents", schema["paths"])
        self.assertIn(f"{settings.API_V1_STR}/analytics/mandates-performance", schema["paths"])
        self.assertIn(f"{settings.API_V1_STR}/economic/annual-summary", schema["paths"])

    def test_data_dir_resolution(self):
        """Verifica se o diretório de dados processados existe e contém arquivos estruturais do ETL."""
        self.assertTrue(PROCESSED_DATA_DIR.exists(), f"Diretório {PROCESSED_DATA_DIR} não existe.")
        essential_files = [
            "presidentes_historico.json",
            "resumo_macroeconomico_anual.csv",
            "indicadores_por_mandato.json"
        ]
        for filename in essential_files:
            file_path = PROCESSED_DATA_DIR / filename
            self.assertTrue(file_path.exists(), f"Arquivo essencial {filename} não encontrado em {PROCESSED_DATA_DIR}.")

    def test_presidents_endpoint(self):
        """Verifica se o catálogo de presidentes históricos retorna lista preenchida e válida."""
        response = self.client.get(f"{settings.API_V1_STR}/politicians/presidents")
        self.assertEqual(response.status_code, 200)
        presidents = response.json()
        self.assertIsInstance(presidents, list)
        self.assertGreater(len(presidents), 0)
        first = presidents[0]
        self.assertIn("id_referencia", first)
        self.assertIn("nome_eleitoral", first)
        self.assertIn("marcos_economicos", first)

    def test_mandates_performance_endpoint(self):
        """Verifica se o endpoint de performance de mandatos retorna os indicadores consolidados."""
        response = self.client.get(f"{settings.API_V1_STR}/analytics/mandates-performance")
        self.assertEqual(response.status_code, 200)
        mandates = response.json()
        self.assertIsInstance(mandates, list)
        self.assertGreater(len(mandates), 0)
        first = mandates[0]
        self.assertIn("id_mandato", first)
        self.assertIn("presidente", first)
        self.assertIn("ipca_acumulado_pct", first)

    def test_annual_macro_summary_endpoint(self):
        """Verifica se a série histórica macroeconômica anual responde com registros históricos."""
        response = self.client.get(f"{settings.API_V1_STR}/economic/annual-summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        first = data[0]
        self.assertIn("ano", first)

    def test_wage_disparity_endpoint(self):
        """Verifica se o endpoint de disparidade salarial responde com a série histórica."""
        response = self.client.get(f"{settings.API_V1_STR}/analytics/wage-disparity")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("serie_historica", data)

    def test_congress_composition_endpoint(self):
        """Verifica se o endpoint de composição do Congresso responde para o mandato padrão."""
        response = self.client.get(f"{settings.API_V1_STR}/analytics/congress-composition?mandate_id=lula-2023")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("mandato_id", data)
        self.assertIn("camara", data)
        self.assertIn("senado", data)

    def test_cidadania_consultas_endpoint(self):
        """Verifica se o serviço de consultas públicas responde com status 200."""
        response = self.client.get(f"{settings.API_V1_STR}/cidadania/consultas")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)


if __name__ == "__main__":
    unittest.main()
