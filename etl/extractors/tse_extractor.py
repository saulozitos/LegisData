"""
Extrator de Filiações Partidárias do TSE (Tribunal Superior Eleitoral)
Focado no histórico partidário da 57ª Legislatura (Deputados e Senadores),
fusões partidárias (PSL + DEM -> UNIÃO, PTB + PATRIOTA -> PRD, PSC -> PODE, PROS -> SOLIDARIEDADE)
e migrações de janela partidária.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from etl.config import PROCESSED_DATA_DIR
from etl.utils.datafiles import load_deputados, load_senadores
from etl.utils.io_utils import atomic_write_json, atomic_write_text

logger = logging.getLogger("TSEExtractor")

FONTE_CURADORIA = "Curadoria manual LegisData (trajetória notória; não verificada automaticamente contra o TSE)"
FONTE_ATUAL = "API de Dados Abertos (partido atual do parlamentar em exercício)"

# Casos notáveis de parlamentares com múltiplas legendas (curadoria manual).
# ATENÇÃO: estes períodos foram digitados à mão e NÃO são verificados automaticamente; cada registro
# derivado carrega `fonte` = FONTE_CURADORIA para que o consumidor saiba disso.
NOMADES_HISTORICO = {
    # Senadores
    "Alessandro Vieira": [
        {"partido": "REDE", "inicio": "2018-04-06", "fim": "2019-12-10", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "CIDADANIA", "inicio": "2019-12-11", "fim": "2022-03-20", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSDB", "inicio": "2022-03-21", "fim": "2023-06-25", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "MDB", "inicio": "2023-06-26", "fim": None, "motivo": None},
    ],
    "Jorge Kajuru": [
        {"partido": "PRP", "inicio": "2018-03-15", "fim": "2019-01-20", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSB", "inicio": "2019-01-21", "fim": "2019-08-15", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "CIDADANIA", "inicio": "2019-08-16", "fim": "2021-04-12", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PODE", "inicio": "2021-04-13", "fim": "2023-01-25", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSB", "inicio": "2023-01-26", "fim": None, "motivo": None},
    ],
    "Flávio Bolsonaro": [
        {"partido": "PP", "inicio": "2003-04-01", "fim": "2016-03-10", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSC", "inicio": "2016-03-11", "fim": "2018-01-15", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSL", "inicio": "2018-01-16", "fim": "2019-11-12", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "REPUBLICANOS", "inicio": "2020-03-27", "fim": "2021-11-29", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PL", "inicio": "2021-11-30", "fim": None, "motivo": None},
    ],
    "Romário": [
        {"partido": "PSB", "inicio": "2009-09-24", "fim": "2017-06-20", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PODE", "inicio": "2017-06-21", "fim": "2021-04-08", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PL", "inicio": "2021-04-09", "fim": None, "motivo": None},
    ],
    "Soraya Thronicke": [
        {"partido": "PSL", "inicio": "2018-03-05", "fim": "2022-02-07", "motivo": "FUSAO_OU_INCORPORACAO"},
        {"partido": "UNIÃO", "inicio": "2022-02-08", "fim": "2023-06-27", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PODE", "inicio": "2023-06-28", "fim": None, "motivo": None},
    ],
    "Cid Gomes": [
        {"partido": "PMDB", "inicio": "1989-05-10", "fim": "1997-08-15", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSDB", "inicio": "1997-08-16", "fim": "2005-09-20", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSB", "inicio": "2005-09-21", "fim": "2013-09-30", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PROS", "inicio": "2013-10-01", "fim": "2015-09-15", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PDT", "inicio": "2015-09-16", "fim": "2024-02-03", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSB", "inicio": "2024-02-04", "fim": None, "motivo": None},
    ],
    "Carlos Viana": [
        {"partido": "PHS", "inicio": "2018-04-05", "fim": "2019-03-15", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSD", "inicio": "2019-03-16", "fim": "2022-01-20", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "MDB", "inicio": "2022-01-21", "fim": "2022-03-30", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PL", "inicio": "2022-03-31", "fim": "2023-02-05", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PODE", "inicio": "2023-02-06", "fim": None, "motivo": None},
    ],
    "Sergio Moro": [
        {"partido": "PODE", "inicio": "2021-11-10", "fim": "2022-03-30", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "UNIÃO", "inicio": "2022-03-31", "fim": None, "motivo": None},
    ],
    "Mara Gabrilli": [
        {"partido": "PSDB", "inicio": "2007-05-10", "fim": "2023-01-26", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSD", "inicio": "2023-01-27", "fim": None, "motivo": None},
    ],
    "Eliziane Gama": [
        {"partido": "PPS", "inicio": "2007-04-05", "fim": "2019-03-22", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "CIDADANIA", "inicio": "2019-03-23", "fim": "2023-01-30", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSD", "inicio": "2023-01-31", "fim": None, "motivo": None},
    ],
    "Randolfe Rodrigues": [
        {"partido": "PT", "inicio": "2000-01-10", "fim": "2005-09-27", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSOL", "inicio": "2005-09-28", "fim": "2015-09-28", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "REDE", "inicio": "2015-09-29", "fim": "2023-05-18", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PT", "inicio": "2024-02-01", "fim": None, "motivo": None},
    ],
    "Cleitinho": [
        {"partido": "CIDADANIA", "inicio": "2018-04-05", "fim": "2022-03-25", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSC", "inicio": "2022-03-26", "fim": "2022-12-10", "motivo": "FUSAO_OU_INCORPORACAO"},
        {"partido": "REPUBLICANOS", "inicio": "2022-12-11", "fim": None, "motivo": None},
    ],
    "Carlos Portinho": [
        {"partido": "PSD", "inicio": "2020-04-01", "fim": "2020-12-15", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PL", "inicio": "2020-12-16", "fim": None, "motivo": None},
    ],
    "Chico Rodrigues": [
        {"partido": "DEM", "inicio": "2018-04-05", "fim": "2022-02-07", "motivo": "FUSAO_OU_INCORPORACAO"},
        {"partido": "UNIÃO", "inicio": "2022-02-08", "fim": "2023-02-14", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSB", "inicio": "2023-02-15", "fim": None, "motivo": None},
    ],
    "Alan Rick": [
        {"partido": "REPUBLICANOS", "inicio": "2014-04-05", "fim": "2017-03-15", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "DEM", "inicio": "2017-03-16", "fim": "2022-02-07", "motivo": "FUSAO_OU_INCORPORACAO"},
        {"partido": "UNIÃO", "inicio": "2022-02-08", "fim": None, "motivo": None},
    ],
    "Efraim Filho": [
        {"partido": "DEM", "inicio": "2007-03-15", "fim": "2022-02-07", "motivo": "FUSAO_OU_INCORPORACAO"},
        {"partido": "UNIÃO", "inicio": "2022-02-08", "fim": None, "motivo": None},
    ],
    # Deputados Federais
    "Arthur Lira": [
        {"partido": "PFL", "inicio": "1999-02-01", "fim": "2007-03-15", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PMDB", "inicio": "2007-03-16", "fim": "2009-09-20", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PP", "inicio": "2009-09-21", "fim": None, "motivo": None},
    ],
    "Tabata Amaral": [
        {"partido": "PDT", "inicio": "2018-04-05", "fim": "2021-09-15", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSB", "inicio": "2021-09-16", "fim": None, "motivo": None},
    ],
    "Kim Kataguiri": [
        {"partido": "DEM", "inicio": "2018-04-05", "fim": "2022-02-07", "motivo": "FUSAO_OU_INCORPORACAO"},
        {"partido": "UNIÃO", "inicio": "2022-02-08", "fim": None, "motivo": None},
    ],
    "Eduardo Bolsonaro": [
        {"partido": "PSC", "inicio": "2014-04-05", "fim": "2018-03-05", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSL", "inicio": "2018-03-06", "fim": "2021-11-29", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PL", "inicio": "2021-11-30", "fim": None, "motivo": None},
    ],
    "Carla Zambelli": [
        {"partido": "PSL", "inicio": "2018-04-05", "fim": "2022-03-10", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PL", "inicio": "2022-03-11", "fim": None, "motivo": None},
    ],
    "Ricardo Salles": [
        {"partido": "NOVO", "inicio": "2018-03-10", "fim": "2020-05-08", "motivo": "EXPULSAO"},
        {"partido": "PL", "inicio": "2022-03-15", "fim": None, "motivo": None},
    ],
    "Baleia Rossi": [
        {"partido": "PMDB", "inicio": "1992-05-10", "fim": "2017-12-18", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "MDB", "inicio": "2017-12-19", "fim": None, "motivo": None},
    ],
    "Aécio Neves": [
        {"partido": "PMDB", "inicio": "1986-04-10", "fim": "1989-08-15", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSDB", "inicio": "1989-08-16", "fim": None, "motivo": None},
    ],
    "Bia Kicis": [
        {"partido": "PRP", "inicio": "2018-04-05", "fim": "2018-12-31", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PSL", "inicio": "2019-01-01", "fim": "2022-03-11", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PL", "inicio": "2022-03-12", "fim": None, "motivo": None},
    ],
    "Nikolas Ferreira": [
        {"partido": "PRTB", "inicio": "2020-04-05", "fim": "2022-03-15", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PL", "inicio": "2022-03-16", "fim": None, "motivo": None},
    ],
    "Filipe Barros": [
        {"partido": "PSL", "inicio": "2018-04-05", "fim": "2022-03-11", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "PL", "inicio": "2022-03-12", "fim": None, "motivo": None},
    ],
    "Danielle Cunha": [
        {"partido": "MDB", "inicio": "2018-04-05", "fim": "2022-03-20", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "UNIÃO", "inicio": "2022-03-21", "fim": None, "motivo": None},
    ],
    "Luciano Bivar": [
        {"partido": "PSL", "inicio": "1998-04-10", "fim": "2022-02-07", "motivo": "FUSAO_OU_INCORPORACAO"},
        {"partido": "UNIÃO", "inicio": "2022-02-08", "fim": None, "motivo": None},
    ],
    "Elmar Nascimento": [
        {"partido": "PMDB", "inicio": "2001-04-10", "fim": "2007-03-15", "motivo": "MUDANCA_VOLUNTARIA"},
        {"partido": "DEM", "inicio": "2007-03-16", "fim": "2022-02-07", "motivo": "FUSAO_OU_INCORPORACAO"},
        {"partido": "UNIÃO", "inicio": "2022-02-08", "fim": None, "motivo": None},
    ],
}


class TSEExtractor:
    """
    Extrator de Histórico de Filiações Partidárias e Migrações Parlamentares.

    Para parlamentares fora da curadoria NOMADES_HISTORICO só se conhece, com segurança, o partido ATUAL
    (informado pelas APIs da Câmara/Senado). A origem e a data de filiação não são presumidas: antes, a
    origem era sorteada por `idx % N` e as datas eram fixas, o que gerava trajetórias inexistentes.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or PROCESSED_DATA_DIR

    @staticmethod
    def _registros_curados(nome: str, cargo: str, uf: str, camara_id: Any, senado_id: Any) -> List[Dict[str, Any]]:
        return [
            {
                "politico_nome": nome,
                "camara_id": camara_id,
                "senado_id": senado_id,
                "cargo": cargo,
                "uf": uf,
                "partido_sigla": item["partido"],
                "data_filiacao": item["inicio"],
                "data_filiacao_desconhecida": False,
                "data_desfiliacao": item["fim"],
                "motivo_desfiliacao": item["motivo"],
                "is_atual": item["fim"] is None,
                "fonte": FONTE_CURADORIA,
                "is_synthetic": False,
            }
            for item in NOMADES_HISTORICO[nome]
        ]

    @staticmethod
    def _registro_atual(nome: str, cargo: str, uf: str, partido: str, camara_id: Any, senado_id: Any) -> Dict[str, Any]:
        return {
            "politico_nome": nome,
            "camara_id": camara_id,
            "senado_id": senado_id,
            "cargo": cargo,
            "uf": uf,
            "partido_sigla": partido,
            "data_filiacao": None,
            "data_filiacao_desconhecida": True,
            "data_desfiliacao": None,
            "motivo_desfiliacao": None,
            "is_atual": True,
            "fonte": FONTE_ATUAL,
            "is_synthetic": False,
        }

    def extract_affiliations(self) -> pd.DataFrame:
        """Constrói o histórico: curadoria para nômades notórios + filiação atual (data desconhecida) para os demais."""
        logger.info("Iniciando extração do histórico de filiações partidárias...")

        deputados = load_deputados(self.data_dir)
        senadores = load_senadores(self.data_dir)

        records: List[Dict[str, Any]] = []

        for s in senadores:
            nome = s.get("nome_eleitoral")
            uf = s.get("uf")
            if nome in NOMADES_HISTORICO:
                records.extend(self._registros_curados(nome, "SENADOR", uf, None, s.get("senado_id")))
            else:
                records.append(
                    self._registro_atual(
                        nome, "SENADOR", uf, s.get("partido_sigla") or "S.PART.", None, s.get("senado_id")
                    )
                )

        for d in deputados:
            nome = d.get("nome_eleitoral")
            uf = d.get("uf")
            if nome in NOMADES_HISTORICO:
                records.extend(self._registros_curados(nome, "DEPUTADO_FEDERAL", uf, d.get("camara_id"), None))
            else:
                records.append(
                    self._registro_atual(
                        nome, "DEPUTADO_FEDERAL", uf, d.get("partido_sigla") or "S.PART.", d.get("camara_id"), None
                    )
                )

        df = pd.DataFrame(records)
        if df.empty:
            logger.error("Nenhuma filiação gerada: arquivos de deputados/senadores ausentes ou vazios.")
            return df
        logger.info(
            f"Total de {len(df)} registros de filiação gerados para {df['politico_nome'].nunique()} parlamentares."
        )
        return df

    def save_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Salva em JSON e CSV (atômico). DataFrame vazio NÃO sobrescreve os arquivos existentes."""
        if df.empty:
            raise RuntimeError("Extração de filiações vazia: arquivos existentes preservados.")

        json_path = self.data_dir / "filiacoes_partidarias.json"
        csv_path = self.data_dir / "filiacoes_partidarias.csv"

        df_clean = df.astype(object).where(df.notna(), None)
        registros = df_clean.to_dict(orient="records")
        for reg in registros:  # ids numéricos voltam a ser inteiros (NaN no DataFrame os transformou em float)
            for chave in ("camara_id", "senado_id"):
                if isinstance(reg.get(chave), float):
                    reg[chave] = int(reg[chave])
        atomic_write_json(json_path, registros)
        atomic_write_text(csv_path, df.to_csv(index=False))
        logger.info(f"Dados salvos com sucesso em {json_path} e {csv_path}!")

        trocas_por_politico = df.groupby("politico_nome")["partido_sigla"].count()
        nomades = trocas_por_politico[trocas_por_politico > 1]

        return {
            "total_filiacoes": len(df),
            "total_parlamentares": int(df["politico_nome"].nunique()),
            "parlamentares_com_troca": len(nomades),
            "max_trocas": int(trocas_por_politico.max()) if not trocas_por_politico.empty else 0,
        }

    def run(self) -> Dict[str, Any]:
        """Executa extração e persistência completa."""
        df = self.extract_affiliations()
        return self.save_data(df)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    extractor = TSEExtractor()
    stats = extractor.run()
    print("Estatísticas da Extração de Filiações:", stats)
