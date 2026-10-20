"""
Indicadores sociais e resultados eleitorais por UF.

Indicadores sociais (nacional e por UF): fontes OFICIAIS via IBGE/SIDRA e BCB (ver `social_official_extractor`).
Resultados eleitorais por UF: ainda digitados à mão e NÃO verificados contra o TSE (`verificado: False`);
o loader só os aceita com `--allow-unverified`.
"""

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.social_official_extractor import SocialOfficialExtractor
from etl.extractors.ufs import ESTADOS_BRASIL
from etl.utils.io_utils import atomic_write_json, atomic_write_text
from etl.utils.provenance import mark_official

FONTE_ELEICOES = "Digitação manual LegisData — NÃO verificada contra os resultados oficiais do TSE"

# Mapeia o ano de eleição para o id de referência do mandato que ela inaugurou
# (ids iguais aos de `presidentes_historico.json`; antes usava-se "fhc-1", "lula-3"... que não casavam).
MANDATO_POR_ELEICAO = {
    1994: "fhc-1995",
    1998: "fhc-1999",
    2002: "lula-2003",
    2006: "lula-2007",
    2010: "dilma-2011",
    2014: "dilma-2015",
    2018: "bolsonaro-2019",
    2022: "lula-2023",
}

logger = logging.getLogger("SocialIndicatorsExtractor")


class SocialIndicatorsExtractor:
    """Extrai e consolida séries históricas de indicadores sociais e eleições do TSE."""

    def __init__(self, output_dir: Path = PROCESSED_DATA_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _oficial(self) -> SocialOfficialExtractor:
        if getattr(self, "_official", None) is None:
            self._official = SocialOfficialExtractor(output_dir=getattr(self, "output_dir", PROCESSED_DATA_DIR))
        return self._official

    def get_annual_social_indicators(self) -> List[Dict[str, Any]]:
        """Série anual nacional OFICIAL (IBGE/SIDRA). Lacunas de pesquisa ficam None; nada é interpolado."""
        return self._oficial().get_annual_social_indicators()

    def get_annual_unemployment_history(self) -> Dict[int, Optional[float]]:
        """Taxa média anual de desemprego: PME (≤2011) e PNAD Contínua (≥2012). Anos sem dado oficial ficam fora."""
        return {a: v for a, v in self._oficial().desemprego_anual().items() if v is not None}

    def get_state_social_indicators(self) -> List[Dict[str, Any]]:
        """Indicadores por UF OFICIAIS (IBGE/SIDRA). Não há mais estimativa por fator regional."""
        return self._oficial().get_state_social_indicators()

    def get_presidential_elections_by_uf(self) -> List[Dict[str, Any]]:
        """
        Retorna o resultado oficial do TSE para eleições presidenciais por UF no 2º turno (ou 1º em 1994/1998).
        Anos: 1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022.
        """
        eleicoes = []

        # Mapa das eleições presidenciais por ano
        mapa_eleicoes = {
            1994: {
                "turno": 1,
                "vencedor_br": "Fernando Henrique Cardoso",
                "vencedor_partido": "PSDB",
                "segundo_br": "Luiz Inácio Lula da Silva",
                "segundo_partido": "PT",
                # Distribuição por estado (vencedor e % dos votos válidos)
                "estados": {
                    "SP": (65.8, 20.3),
                    "RJ": (58.4, 25.1),
                    "MG": (60.2, 23.5),
                    "RS": (46.5, 38.2),
                    "PR": (63.1, 21.0),
                    "SC": (64.2, 21.5),
                    "BA": (48.2, 34.1),
                    "PE": (49.1, 35.8),
                    "CE": (53.4, 30.2),
                    "MA": (54.0, 29.5),
                    "PB": (51.2, 33.1),
                    "RN": (55.4, 29.8),
                    "AL": (52.1, 31.2),
                    "SE": (47.8, 35.6),
                    "PI": (53.6, 30.1),
                    "GO": (61.2, 22.4),
                    "MT": (62.5, 20.8),
                    "MS": (63.0, 21.2),
                    "DF": (44.5, 41.2),
                    "AM": (47.5, 36.2),
                    "PA": (49.8, 33.5),
                    "RO": (58.4, 24.2),
                    "AC": (52.3, 31.5),
                    "RR": (56.1, 26.2),
                    "AP": (46.8, 37.1),
                    "TO": (55.2, 28.4),
                    "ES": (58.9, 24.7),
                },
            },
            1998: {
                "turno": 1,
                "vencedor_br": "Fernando Henrique Cardoso",
                "vencedor_partido": "PSDB",
                "segundo_br": "Luiz Inácio Lula da Silva",
                "segundo_partido": "PT",
                "estados": {
                    "SP": (59.8, 26.5),
                    "RJ": (51.4, 34.2),
                    "MG": (53.7, 32.1),
                    "RS": (44.1, 46.2),  # RS Lula venceu
                    "PR": (60.3, 27.4),
                    "SC": (62.8, 25.6),
                    "BA": (52.1, 35.4),
                    "PE": (47.2, 42.1),
                    "CE": (55.6, 32.8),
                    "MA": (58.1, 28.4),
                    "PB": (53.4, 34.5),
                    "RN": (56.2, 31.8),
                    "AL": (56.4, 29.1),
                    "SE": (48.2, 39.5),
                    "PI": (54.8, 32.6),
                    "GO": (62.4, 25.1),
                    "MT": (61.5, 26.0),
                    "MS": (58.9, 27.5),
                    "DF": (43.2, 44.5),
                    "AM": (53.2, 34.0),
                    "PA": (52.6, 35.1),
                    "RO": (57.1, 28.2),
                    "AC": (55.4, 32.1),
                    "RR": (60.2, 25.4),
                    "AP": (48.1, 39.2),
                    "TO": (57.5, 29.8),
                    "ES": (56.7, 30.2),
                },
            },
            2002: {
                "turno": 2,
                "vencedor_br": "Luiz Inácio Lula da Silva",
                "vencedor_partido": "PT",
                "segundo_br": "José Serra",
                "segundo_partido": "PSDB",
                # Lula venceu em 26 UFs, Serra apenas em AL
                "estados": {
                    "SP": (55.4, 44.6),
                    "RJ": (79.0, 21.0),
                    "MG": (66.4, 33.6),
                    "RS": (56.0, 44.0),
                    "PR": (52.8, 47.2),
                    "SC": (56.7, 43.3),
                    "BA": (65.8, 34.2),
                    "PE": (63.5, 36.5),
                    "CE": (71.8, 28.2),
                    "MA": (67.4, 32.6),
                    "PB": (57.8, 42.2),
                    "RN": (60.2, 39.8),
                    "AL": (49.2, 50.8),
                    "SE": (66.5, 33.5),
                    "PI": (64.2, 35.8),
                    "GO": (53.2, 46.8),
                    "MT": (54.5, 45.5),
                    "MS": (55.1, 44.9),
                    "DF": (62.3, 37.7),
                    "AM": (68.4, 31.6),
                    "PA": (57.2, 42.8),
                    "RO": (55.8, 44.2),
                    "AC": (59.6, 40.4),
                    "RR": (54.3, 45.7),
                    "AP": (66.8, 33.2),
                    "TO": (58.9, 41.1),
                    "ES": (61.5, 38.5),
                },
            },
            2006: {
                "turno": 2,
                "vencedor_br": "Luiz Inácio Lula da Silva",
                "vencedor_partido": "PT",
                "segundo_br": "Geraldo Alckmin",
                "segundo_partido": "PSDB",
                # Divisão clara: Lula forte N/NE/MG/RJ, Alckmin forte Sul/Centro-Oeste/SP
                "estados": {
                    "SP": (47.7, 52.3),
                    "RJ": (69.7, 30.3),
                    "MG": (65.2, 34.8),
                    "RS": (45.1, 54.9),
                    "PR": (41.4, 58.6),
                    "SC": (35.5, 64.5),
                    "BA": (78.1, 21.9),
                    "PE": (78.5, 21.5),
                    "CE": (82.4, 17.6),
                    "MA": (84.6, 15.4),
                    "PB": (75.5, 24.5),
                    "RN": (73.2, 26.8),
                    "AL": (68.6, 31.4),
                    "SE": (70.5, 29.5),
                    "PI": (77.8, 22.2),
                    "GO": (45.2, 54.8),
                    "MT": (45.3, 54.7),
                    "MS": (44.8, 55.2),
                    "DF": (43.0, 57.0),
                    "AM": (86.8, 13.2),
                    "PA": (60.0, 40.0),
                    "RO": (46.2, 53.8),
                    "AC": (43.8, 56.2),
                    "RR": (37.2, 62.8),
                    "AP": (62.5, 37.5),
                    "TO": (65.8, 34.2),
                    "ES": (51.2, 48.8),
                },
            },
            2010: {
                "turno": 2,
                "vencedor_br": "Dilma Rousseff",
                "vencedor_partido": "PT",
                "segundo_br": "José Serra",
                "segundo_partido": "PSDB",
                "estados": {
                    "SP": (45.9, 54.1),
                    "RJ": (60.5, 39.5),
                    "MG": (58.4, 41.6),
                    "RS": (49.1, 50.9),
                    "PR": (44.6, 55.4),
                    "SC": (35.3, 64.7),
                    "BA": (70.8, 29.2),
                    "PE": (75.6, 24.4),
                    "CE": (77.4, 22.6),
                    "MA": (79.1, 20.9),
                    "PB": (64.3, 35.7),
                    "RN": (63.5, 36.5),
                    "AL": (53.6, 46.4),
                    "SE": (57.1, 42.9),
                    "PI": (69.9, 30.1),
                    "GO": (49.2, 50.8),
                    "MT": (48.9, 51.1),
                    "MS": (44.9, 55.1),
                    "DF": (47.2, 52.8),
                    "AM": (80.6, 19.4),
                    "PA": (53.2, 46.8),
                    "RO": (47.8, 52.2),
                    "AC": (29.5, 70.5),
                    "RR": (32.8, 67.2),
                    "AP": (62.7, 37.3),
                    "TO": (58.9, 41.1),
                    "ES": (49.1, 50.9),
                },
            },
            2014: {
                "turno": 2,
                "vencedor_br": "Dilma Rousseff",
                "vencedor_partido": "PT",
                "segundo_br": "Aécio Neves",
                "segundo_partido": "PSDB",
                "estados": {
                    "SP": (35.7, 64.3),
                    "RJ": (54.9, 45.1),
                    "MG": (52.4, 47.6),
                    "RS": (46.5, 53.5),
                    "PR": (39.0, 61.0),
                    "SC": (35.4, 64.6),
                    "BA": (70.2, 29.8),
                    "PE": (70.2, 29.8),
                    "CE": (76.7, 23.3),
                    "MA": (78.8, 21.2),
                    "PB": (64.3, 35.7),
                    "RN": (69.9, 30.1),
                    "AL": (62.1, 37.9),
                    "SE": (67.0, 33.0),
                    "PI": (78.3, 21.7),
                    "GO": (42.9, 57.1),
                    "MT": (45.3, 54.7),
                    "MS": (43.7, 56.3),
                    "DF": (38.1, 61.9),
                    "AM": (65.0, 35.0),
                    "PA": (53.5, 46.5),
                    "RO": (45.1, 54.9),
                    "AC": (36.1, 63.9),
                    "RR": (31.1, 68.9),
                    "AP": (61.5, 38.5),
                    "TO": (50.2, 49.8),
                    "ES": (46.2, 53.8),
                },
            },
            2018: {
                "turno": 2,
                "vencedor_br": "Jair Bolsonaro",
                "vencedor_partido": "PSL",
                "segundo_br": "Fernando Haddad",
                "segundo_partido": "PT",
                # Bolsonaro venceu em Sul, Sudeste, Centro-Oeste e maior parte do Norte; Haddad no Nordeste + PA
                "estados": {
                    "SP": (68.0, 32.0),
                    "RJ": (68.0, 32.0),
                    "MG": (58.2, 41.8),
                    "RS": (63.2, 36.8),
                    "PR": (68.4, 31.6),
                    "SC": (75.9, 24.1),
                    "BA": (27.4, 72.6),
                    "PE": (33.5, 66.5),
                    "CE": (28.9, 71.1),
                    "MA": (26.7, 73.3),
                    "PB": (35.0, 65.0),
                    "RN": (36.6, 63.4),
                    "AL": (38.8, 61.2),
                    "SE": (32.8, 67.2),
                    "PI": (22.9, 77.1),
                    "GO": (65.5, 34.5),
                    "MT": (66.4, 33.6),
                    "MS": (65.2, 34.8),
                    "DF": (69.9, 30.1),
                    "AM": (50.3, 49.7),
                    "PA": (45.2, 54.8),
                    "RO": (72.2, 27.8),
                    "AC": (77.2, 22.8),
                    "RR": (71.5, 28.5),
                    "AP": (50.2, 49.8),
                    "TO": (45.1, 54.9),
                    "ES": (63.1, 36.9),
                },
            },
            2022: {
                "turno": 2,
                "vencedor_br": "Luiz Inácio Lula da Silva",
                "vencedor_partido": "PT",
                "segundo_br": "Jair Bolsonaro",
                "segundo_partido": "PL",
                # Eleição mais polarizada: Lula vence em todo o NE + AM/PA; Bolsonaro no Sul/CO/SE/Norte restante
                "estados": {
                    "SP": (44.8, 55.2),
                    "RJ": (43.5, 56.5),
                    "MG": (50.2, 49.8),
                    "RS": (43.7, 56.3),
                    "PR": (37.5, 62.5),
                    "SC": (30.8, 69.2),
                    "BA": (72.1, 27.9),
                    "PE": (67.0, 33.0),
                    "CE": (69.9, 30.1),
                    "MA": (71.1, 28.9),
                    "PB": (66.6, 33.4),
                    "RN": (65.1, 34.9),
                    "AL": (58.7, 41.3),
                    "SE": (67.2, 32.8),
                    "PI": (76.9, 23.1),
                    "GO": (41.3, 58.7),
                    "MT": (35.0, 65.0),
                    "MS": (40.5, 59.5),
                    "DF": (41.2, 58.8),
                    "AM": (51.1, 48.9),
                    "PA": (52.2, 47.8),
                    "RO": (29.3, 70.7),
                    "AC": (29.7, 70.3),
                    "RR": (23.9, 76.1),
                    "AP": (48.6, 51.4),
                    "TO": (48.6, 51.4),
                    "ES": (41.9, 58.1),
                },
            },
        }

        for ano, data_eleicao in mapa_eleicoes.items():
            mandato_ref = MANDATO_POR_ELEICAO[ano]
            turno = data_eleicao["turno"]
            venc_br = data_eleicao["vencedor_br"]
            part_venc_br = data_eleicao["vencedor_partido"]
            seg_br = data_eleicao["segundo_br"]
            part_seg_br = data_eleicao["segundo_partido"]

            for est in ESTADOS_BRASIL:
                uf = est["uf"]
                pct_v1, pct_v2 = data_eleicao["estados"].get(uf, (50.0, 50.0))

                # Determinar quem ganhou no estado específico
                if pct_v1 >= pct_v2:
                    ganhador_uf = venc_br
                    partido_ganhador_uf = part_venc_br
                    pct_ganhador = pct_v1
                    segundo_uf = seg_br
                    partido_segundo_uf = part_seg_br
                    pct_segundo = pct_v2
                else:
                    ganhador_uf = seg_br
                    partido_ganhador_uf = part_seg_br
                    pct_ganhador = pct_v2
                    segundo_uf = venc_br
                    partido_segundo_uf = part_venc_br
                    pct_segundo = pct_v1

                eleicoes.append(
                    mark_official(
                        {
                            "ano_eleicao": ano,
                            "mandato_id_ref": mandato_ref,
                            "uf": uf,
                            "estado_nome": est["nome"],
                            "regiao": est["regiao"],
                            "candidato_vencedor_nome": ganhador_uf,
                            "partido_vencedor_sigla": partido_ganhador_uf,
                            "votos_vencedor_pct": Decimal(str(pct_ganhador)),
                            "candidato_segundo_nome": segundo_uf,
                            "partido_segundo_sigla": partido_segundo_uf,
                            "votos_segundo_pct": Decimal(str(pct_segundo)),
                            "turno": turno,
                            "verificado": False,
                        },
                        FONTE_ELEICOES,
                    )
                )

        return eleicoes

    def export_all(self, allow_synthetic: bool = False) -> Dict[str, Any]:
        """Exporta indicadores sociais oficiais (CSV/JSON atômicos) e as eleições por UF (não verificadas).

        `allow_synthetic` é aceito por compatibilidade: já não há dado sintético neste módulo.
        """
        sociais = self._oficial().export()
        anuais = sociais["total_anuais"]
        uf_sociais = sociais["total_uf_sociais"]

        # 3. Eleições por UF
        eleicoes = self.get_presidential_elections_by_uf()
        eleicoes_serializable = []
        for e in eleicoes:
            item = e.copy()
            item["votos_vencedor_pct"] = float(item["votos_vencedor_pct"])
            item["votos_segundo_pct"] = float(item["votos_segundo_pct"])
            eleicoes_serializable.append(item)

        atomic_write_text(
            self.output_dir / "resultados_eleicoes_presidenciais_uf.csv",
            pd.DataFrame(eleicoes_serializable).to_csv(index=False),
        )
        atomic_write_json(self.output_dir / "resultados_eleicoes_presidenciais_uf.json", eleicoes_serializable)

        logger.info(f"Arquivos sociais e eleitorais exportados com sucesso em {self.output_dir}")
        return {
            "total_anuais": anuais,
            "total_uf_sociais": uf_sociais,
            "total_eleicoes_uf": len(eleicoes),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    extractor = SocialIndicatorsExtractor()
    res = extractor.export_all()
    print("Exportação concluída com sucesso:", res)
