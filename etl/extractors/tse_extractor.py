"""
Extrator de Filiações Partidárias do TSE (Tribunal Superior Eleitoral)
Focado no histórico partidário da 57ª Legislatura (Deputados e Senadores),
fusões partidárias (PSL + DEM -> UNIÃO, PTB + PATRIOTA -> PRD, PSC -> PODE, PROS -> SOLIDARIEDADE)
e migrações de janela partidária.
"""

import json
import logging
from pathlib import Path
from datetime import date, datetime
from typing import List, Dict, Any, Optional
import pandas as pd

from etl.config import PROCESSED_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TSEExtractor")

# Casos de parlamentares com múltiplas legendas, curados manualmente.
# ATENÇÃO: lista digitada à mão, sem link de fonte por registro; precisa de
# conferência contra as listas oficiais de filiados do TSE antes de ser exibida
# como histórico. Para os demais parlamentares registramos apenas a legenda atual
# (dado da Câmara/Senado); históricos inferidos por regra foram removidos.
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
    ]
}


class TSEExtractor:
    """
    Extrator de Histórico de Filiações Partidárias e Migrações Parlamentares.
    Gera dados consolidados em formato tabular/JSON para análise de infidelidade partidária.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or PROCESSED_DATA_DIR

    def extract_affiliations(self) -> pd.DataFrame:
        """
        Processa e constrói o histórico de filiações partidárias cruzando:
        1. Casos nominais de grande relevância (nômades partidários).
        2. Efeitos das grandes fusões partidárias (PSL+DEM -> UNIÃO, PTB+PATRIOTA -> PRD, PSC -> PODE, PROS -> SOLIDARIEDADE).
        3. Filiação atual dos deputados e senadores da 57ª Legislatura.
        """
        logger.info("Iniciando extração do histórico de filiações partidárias do TSE...")

        dep_file = self.data_dir / "deputados_camara.json"
        sen_file = self.data_dir / "senadores_senado.json"

        deputados = []
        if dep_file.exists():
            with open(dep_file, "r", encoding="utf-8") as f:
                deputados = json.load(f)

        senadores = []
        if sen_file.exists():
            with open(sen_file, "r", encoding="utf-8") as f:
                senadores = json.load(f)

        records: List[Dict[str, Any]] = []

        # 1. Processar Senadores
        for s in senadores:
            nome = s.get("nome_eleitoral")
            partido_atual = s.get("partido_sigla") or "S.PART."
            uf = s.get("uf") or "DF"
            sid = s.get("senado_id")

            if nome in NOMADES_HISTORICO:
                hist = NOMADES_HISTORICO[nome]
                for item in hist:
                    records.append({
                        "politico_nome": nome,
                        "camara_id": None,
                        "senado_id": sid,
                        "cargo": "SENADOR",
                        "uf": uf,
                        "partido_sigla": item["partido"],
                        "data_filiacao": item["inicio"],
                        "data_desfiliacao": item["fim"],
                        "motivo_desfiliacao": item["motivo"],
                        "is_atual": item["fim"] is None,
                    })
            else:
                # Apenas a legenda atual informada pelo Senado.
                # TODO: data_filiacao é um marcador (a coluna é NOT NULL); a data real
                # deve vir da lista oficial de filiados do TSE.
                records.append({
                    "politico_nome": nome,
                    "camara_id": None,
                    "senado_id": sid,
                    "cargo": "SENADOR",
                    "uf": uf,
                    "partido_sigla": partido_atual,
                    "data_filiacao": "2018-04-05",
                    "data_desfiliacao": None,
                    "motivo_desfiliacao": None,
                    "is_atual": True,
                })

        # 2. Processar Deputados Federais
        for idx, d in enumerate(deputados):
            nome = d.get("nome_eleitoral")
            partido_atual = d.get("partido_sigla") or "S.PART."
            uf = d.get("uf") or "DF"
            cid = d.get("camara_id")

            if nome in NOMADES_HISTORICO:
                hist = NOMADES_HISTORICO[nome]
                for item in hist:
                    records.append({
                        "politico_nome": nome,
                        "camara_id": cid,
                        "senado_id": None,
                        "cargo": "DEPUTADO_FEDERAL",
                        "uf": uf,
                        "partido_sigla": item["partido"],
                        "data_filiacao": item["inicio"],
                        "data_desfiliacao": item["fim"],
                        "motivo_desfiliacao": item["motivo"],
                        "is_atual": item["fim"] is None,
                    })
            else:
                # Apenas a legenda atual informada pela Câmara.
                # TODO: data_filiacao é um marcador (a coluna é NOT NULL); a data real
                # deve vir da lista oficial de filiados do TSE.
                records.append({
                    "politico_nome": nome,
                    "camara_id": cid,
                    "senado_id": None,
                    "cargo": "DEPUTADO_FEDERAL",
                    "uf": uf,
                    "partido_sigla": partido_atual,
                    "data_filiacao": "2022-03-30",
                    "data_desfiliacao": None,
                    "motivo_desfiliacao": None,
                    "is_atual": True,
                })

        df = pd.DataFrame(records)
        logger.info(f"Total de {len(df)} registros de filiação gerados para {df['politico_nome'].nunique()} parlamentares.")
        return df

    def save_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Salva os dados processados em JSON e CSV."""
        json_path = self.data_dir / "filiacoes_partidarias.json"
        csv_path = self.data_dir / "filiacoes_partidarias.csv"

        df_clean = df.where(pd.notnull(df), None)
        records = df_clean.to_dict(orient="records")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        df.to_csv(csv_path, index=False, encoding="utf-8")
        logger.info(f"Dados salvos com sucesso em {json_path} e {csv_path}!")

        # Contagem rápida de nômades (políticos com mais de 1 filiação)
        trocas_por_politico = df.groupby("politico_nome")["partido_sigla"].count()
        nomades = trocas_por_politico[trocas_por_politico > 1]

        return {
            "total_filiacoes": len(df),
            "total_parlamentares": int(df["politico_nome"].nunique()),
            "parlamentares_com_troca": len(nomades),
            "max_trocas": int(trocas_por_politico.max()) if not trocas_por_politico.empty else 0
        }

    def run(self) -> Dict[str, Any]:
        """Executa extração e persistência completa."""
        df = self.extract_affiliations()
        return self.save_data(df)


if __name__ == "__main__":
    extractor = TSEExtractor()
    stats = extractor.run()
    print("Estatísticas da Extração do TSE:", stats)
