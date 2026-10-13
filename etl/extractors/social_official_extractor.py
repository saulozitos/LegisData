"""
Indicadores sociais OFICIAIS (nacional e por UF) a partir de APIs públicas.

Fontes (todas via IBGE/SIDRA, exceto o desemprego pré-2012):
  - Gini: PNAD Contínua t7435 (2012+, rendimento domiciliar per capita) e PNAD t1167 (1992-2011, rendimento
    das pessoas de 10+ anos com rendimento). Definições DIFERENTES: cada ano traz `serie_gini` e há quebra em 2012.
  - Analfabetismo (15+): PNAD Contínua t7113 (2016+). Antes disso não há série equivalente no SIDRA -> None.
  - Extrema pobreza e pobreza: ODS 1.1.1 (linha internacional, t5817) e 1.2.1 (linha nacional, t5877), 2012+.
  - Insegurança alimentar (% de domicílios): PNAD 2004 (t3017) e PNAD Contínua 2023-2024 (t9552). As pesquisas
    de 2009, 2013 e 2017-18 não estão disponíveis no SIDRA -> None (não se interpola).
  - Desemprego: PME/IBGE (6 regiões metropolitanas, BCB SGS 10777) até 2011 e PNAD Contínua (t6468) desde 2012.

Lacunas permanecem None. Nada é interpolado nem estimado.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.ibge_demografia import populacao_brasil
from etl.extractors.ufs import ESTADOS_BRASIL
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json, atomic_write_text
from etl.utils.provenance import mark_official
from etl.utils.sidra import (
    NIVEL_BRASIL,
    NIVEL_UF,
    SidraClient,
    parse_valor,
    serie_por_ano,
    serie_por_uf_ano,
)

logger = logging.getLogger("SocialOfficialExtractor")

FONTE_ANUAL = "IBGE/SIDRA (PNAD, PNAD Contínua, ODS) e BCB/SGS — ver fonte_detalhe"
FONTE_UF = "IBGE/SIDRA (PNAD, PNAD Contínua, ODS) — ver tabelas na documentação"
PRIMEIRO_ANO = 1992
ANO_QUEBRA_GINI = 2012
ANO_QUEBRA_DESEMPREGO = 2012

# Séries NÃO obtidas por API (curadoria manual com fonte citada). Ficam em campos próprios e NUNCA se misturam
# com `inseguranca_alimentar_pct` (IBGE): a metodologia é outra (Rede PENSSAN, VIGISAN).
REDE_PENSSAN_VIGISAN: Dict[int, Dict[str, Any]] = {
    2020: {
        "fome_pct": 9.0,
        "fome_milhoes": 19.1,
        "fonte": "Rede PENSSAN — I VIGISAN (2021), IA grave; https://olheparaafome.com.br/",
    },
    2022: {
        "fome_pct": 15.5,
        "fome_milhoes": 33.1,
        "fonte": "Rede PENSSAN — II VIGISAN (2022), IA grave; https://olheparaafome.com.br/",
    },
}

# (tabela, variável, classificações) de cada indicador
GINI_PNADC = (7435, "10681", None)
GINI_PNAD = (1167, "1879", None)
ANALFABETISMO = (7113, "10267", {2: "6794", 58: "2795"})  # total, 15 anos ou mais
EXTREMA_POBREZA = (5817, "9617", None)
POBREZA = (5877, "9948", None)
DESOCUPACAO_PNADC = (6468, "4099", None)
INSEG_ALIMENTAR_2004 = (3017, "1000800")  # % de domicílios; c12404 = 109102 (grave) | 109099 (qualquer nível)
INSEG_ALIMENTAR_PNADC = (9552, "9784")  # % de domicílios; c1 = 6795 (total)
INSEG_ALIMENTAR_MORADORES_PNADC = (9552, "10114")  # moradores em domicílios (mil pessoas)
CAT_IA_GRAVE = "109102"
CAT_IA_QUALQUER = "109099"

SGS_DESEMPREGO_PME = 10777
SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={ini}&dataFinal={fim}"


def _arredonda(valor: Optional[float], casas: int = 2) -> Optional[float]:
    return None if valor is None else round(float(valor), casas)


def _anos_trimestrais(linhas: List[Dict[str, Any]]) -> Dict[int, Dict[int, Optional[float]]]:
    """{ano: {trimestre: valor}} a partir de períodos trimestrais (D3C = AAAATT)."""
    saida: Dict[int, Dict[int, Optional[float]]] = {}
    for r in linhas:
        cod = str(r.get("D3C", ""))
        if len(cod) != 6 or not cod.isdigit():
            continue
        saida.setdefault(int(cod[:4]), {})[int(cod[4:])] = parse_valor(r.get("V"))
    return saida


class SocialOfficialExtractor:
    """Monta as séries sociais anuais (Brasil) e por UF a partir do SIDRA e do BCB."""

    def __init__(
        self,
        output_dir: Path = PROCESSED_DATA_DIR,
        sidra: Optional[SidraClient] = None,
        http: Optional[HttpClient] = None,
    ):
        self.output_dir = Path(output_dir)
        self.sidra = sidra or SidraClient()
        self.http = http or HttpClient(timeout=60.0, max_retries=3, min_interval=0.2)

    # ------------------------------------------------------------------ helpers de consulta
    def _brasil(self, spec: Tuple, periodos: str = "all") -> Dict[int, Optional[float]]:
        tabela, variavel, classif = spec
        linhas = self.sidra.try_values(tabela, NIVEL_BRASIL, "all", variavel, periodos, classif)
        return serie_por_ano(linhas)

    def _uf(self, spec: Tuple) -> Dict[str, Dict[int, Optional[float]]]:
        tabela, variavel, classif = spec
        linhas = self.sidra.try_values(tabela, NIVEL_UF, "all", variavel, "all", classif)
        return serie_por_uf_ano(linhas, "D1C", "D3C")

    def _inseguranca(self, nivel: int, categoria: str) -> Dict[Any, Dict[int, Optional[float]]]:
        """% de domicílios na categoria (2004: t3017; 2023+: t9552). Chave = 'BR' ou sigla da UF."""
        saida: Dict[Any, Dict[int, Optional[float]]] = {}
        t04, v04 = INSEG_ALIMENTAR_2004
        t23, v23 = INSEG_ALIMENTAR_PNADC
        fontes = [
            (self.sidra.try_values(t04, nivel, "all", v04, "all", {12404: categoria})),
            (self.sidra.try_values(t23, nivel, "all", v23, "all", {1: "6795", 12404: categoria})),
        ]
        for linhas in fontes:
            if nivel == NIVEL_BRASIL:
                for ano, v in serie_por_ano(linhas).items():
                    saida.setdefault("BR", {})[ano] = v
            else:
                for uf, anos in serie_por_uf_ano(linhas, "D1C", "D3C").items():
                    saida.setdefault(uf, {}).update(anos)
        return saida

    def _moradores_ia_grave_milhoes(self) -> Dict[int, Optional[float]]:
        tabela, variavel = INSEG_ALIMENTAR_MORADORES_PNADC
        linhas = self.sidra.try_values(tabela, NIVEL_BRASIL, "all", variavel, "all", {1: "6795", 12404: CAT_IA_GRAVE})
        saida: Dict[int, Optional[float]] = {}
        for r in linhas:
            try:
                ano = int(str(r["D3C"])[:4])
            except (KeyError, ValueError):
                continue
            v = parse_valor(r.get("V"))
            unidade = str(r.get("MN", "")).lower()
            if v is not None and "mil" in unidade:
                v = v / 1000.0  # mil pessoas -> milhões
            elif v is not None:
                v = v / 1_000_000.0
            saida[ano] = v
        return saida

    # ------------------------------------------------------------------ desemprego
    def desemprego_anual(self) -> Dict[int, Optional[float]]:
        """
        Taxa média anual de desemprego. ≤2011: PME (6 regiões metropolitanas, média dos 12 meses);
        ≥2012: PNAD Contínua (média dos 4 trimestres civis, só anos fechados).
        """
        saida: Dict[int, Optional[float]] = {}
        try:
            url = SGS_URL.format(codigo=SGS_DESEMPREGO_PME, ini="01/01/2002", fim="31/12/2011")
            dados = self.http.get_json(url)
            por_ano: Dict[int, List[float]] = {}
            for item in dados:
                valor = parse_valor(str(item.get("valor", "")).replace(",", "."))
                if valor is None:
                    continue
                por_ano.setdefault(int(str(item["data"])[-4:]), []).append(valor)
            for ano, valores in por_ano.items():
                if len(valores) == 12:  # só anos completos
                    saida[ano] = round(sum(valores) / 12.0, 1)
        except (HttpError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Desemprego PME (SGS %s) indisponível: %s", SGS_DESEMPREGO_PME, exc)

        tabela, variavel, _ = DESOCUPACAO_PNADC
        linhas = self.sidra.try_values(tabela, NIVEL_BRASIL, "all", variavel, "all")
        for ano, trimestres in _anos_trimestrais(linhas).items():
            valores = [v for v in trimestres.values() if v is not None]
            if len(trimestres) == 4 and len(valores) == 4:
                saida[ano] = round(sum(valores) / 4.0, 1)
        return saida

    # ------------------------------------------------------------------ série anual nacional
    def get_annual_social_indicators(self) -> List[Dict[str, Any]]:
        gini_pnadc = self._brasil(GINI_PNADC)
        gini_pnad = self._brasil(GINI_PNAD)
        analf = self._brasil(ANALFABETISMO)
        extrema = self._brasil(EXTREMA_POBREZA)
        pobreza = self._brasil(POBREZA)
        pop = populacao_brasil(self.sidra)
        ia_grave = self._inseguranca(NIVEL_BRASIL, CAT_IA_GRAVE).get("BR", {})
        ia_qualquer = self._inseguranca(NIVEL_BRASIL, CAT_IA_QUALQUER).get("BR", {})
        ia_milhoes = self._moradores_ia_grave_milhoes()
        desemprego = self.desemprego_anual()

        gini: Dict[int, Tuple[float, str]] = {}
        for ano, v in gini_pnad.items():
            if v is not None:
                gini[ano] = (v, "PNAD — pessoas de 10+ anos com rendimento (t1167)")
        for ano, v in gini_pnadc.items():
            if v is not None:
                gini[ano] = (v, "PNAD Contínua — rendimento domiciliar per capita (t7435)")

        def com_valor(serie: Dict[int, Any]) -> set:
            return {a for a, v in serie.items() if v is not None}

        anos = set(gini)  # a Rede PENSSAN só acompanha anos que já têm dado oficial (nunca cria linha sozinha)
        for serie in (analf, extrema, pobreza, ia_grave, ia_qualquer, desemprego):
            anos |= com_valor(serie)
        linhas: List[Dict[str, Any]] = []
        for ano in sorted(a for a in anos if a >= PRIMEIRO_ANO):
            ext = extrema.get(ano)
            ext_milhoes = round(ext * pop[ano] / 100.0 / 1_000_000.0, 2) if ext is not None and ano in pop else None
            gini_v, gini_serie = gini.get(ano, (None, None))
            partes = []
            if gini_v is not None:
                partes.append(f"gini: {gini_serie}")
            if analf.get(ano) is not None:
                partes.append("analfabetismo 15+: PNAD Contínua t7113")
            if ext is not None:
                partes.append("extrema pobreza: ODS 1.1.1 t5817 (milhões = % × população t6579)")
            if pobreza.get(ano) is not None:
                partes.append("pobreza: ODS 1.2.1 t5877")
            if ia_grave.get(ano) is not None:
                partes.append(
                    "insegurança alimentar grave (% domicílios): "
                    + ("PNAD 2004 t3017" if ano < 2023 else "PNAD Contínua t9552")
                )
            if desemprego.get(ano) is not None:
                partes.append(
                    "desemprego: "
                    + ("PME/BCB SGS 10777 (6 RMs)" if ano < ANO_QUEBRA_DESEMPREGO else "PNAD Contínua t6468")
                )
            item: Dict[str, Any] = {
                "ano": ano,
                "analfabetismo": _arredonda(analf.get(ano)),
                "extrema_pobreza_pct": _arredonda(ext),
                "extrema_pobreza_milhoes": ext_milhoes,
                "pobreza_pct": _arredonda(pobreza.get(ano)),
                "inseguranca_alimentar_pct": _arredonda(ia_grave.get(ano)),
                "inseguranca_alimentar_milhoes": _arredonda(ia_milhoes.get(ano)),
                "inseguranca_alimentar_total_pct": _arredonda(ia_qualquer.get(ano)),
                "gini": _arredonda(gini_v, 3),
                "desemprego_pct": _arredonda(desemprego.get(ano), 1),
                "serie_gini": gini_serie,
                "serie_desemprego": (
                    None
                    if desemprego.get(ano) is None
                    else ("PME (6 RMs)" if ano < ANO_QUEBRA_DESEMPREGO else "PNAD Contínua")
                ),
                "quebra_metodologica_gini": ano == ANO_QUEBRA_GINI,
                "quebra_metodologica_desemprego": ano == ANO_QUEBRA_DESEMPREGO,
                "fonte_inseguranca_alimentar": (
                    None
                    if ia_grave.get(ano) is None
                    else (
                        "IBGE — PNAD 2004 (suplemento EBIA)"
                        if ano < 2023
                        else "IBGE — PNAD Contínua (segurança alimentar)"
                    )
                ),
                "fonte_detalhe": "; ".join(partes),
            }
            vigisan = REDE_PENSSAN_VIGISAN.get(ano)
            if vigisan:
                item["rede_penssan_fome_pct"] = vigisan["fome_pct"]
                item["rede_penssan_fome_milhoes"] = vigisan["fome_milhoes"]
                item["rede_penssan_fonte"] = vigisan["fonte"]
            linhas.append(mark_official(item, FONTE_ANUAL))
        return linhas

    # ------------------------------------------------------------------ por UF
    def get_state_social_indicators(self) -> List[Dict[str, Any]]:
        gini_pnadc = self._uf(GINI_PNADC)
        gini_pnad = self._uf(GINI_PNAD)
        analf = self._uf(ANALFABETISMO)
        extrema = self._uf(EXTREMA_POBREZA)
        pobreza = self._uf(POBREZA)
        ia_grave = self._inseguranca(NIVEL_UF, CAT_IA_GRAVE)

        registros: List[Dict[str, Any]] = []
        for est in ESTADOS_BRASIL:
            uf = est["uf"]
            gini_uf: Dict[int, Optional[float]] = {}
            gini_uf.update({a: v for a, v in gini_pnad.get(uf, {}).items() if v is not None})
            gini_uf.update({a: v for a, v in gini_pnadc.get(uf, {}).items() if v is not None})
            series = {
                "taxa_analfabetismo_pct": analf.get(uf, {}),
                "extrema_pobreza_pct": extrema.get(uf, {}),
                "pobreza_pct": pobreza.get(uf, {}),
                "inseguranca_alimentar_pct": ia_grave.get(uf, {}),
                "indice_gini": gini_uf,
            }
            anos = sorted({a for s in series.values() for a, v in s.items() if v is not None and a >= PRIMEIRO_ANO})
            for ano in anos:
                reg = {
                    "ano": ano,
                    "uf": uf,
                    "estado_nome": est["nome"],
                    "regiao": est["regiao"],
                }
                for campo, serie in series.items():
                    casas = 3 if campo == "indice_gini" else 2
                    reg[campo] = _arredonda(serie.get(ano), casas)
                registros.append(mark_official(reg, FONTE_UF))
        return registros

    # ------------------------------------------------------------------ exportação
    def export(self) -> Dict[str, Any]:
        anuais = self.get_annual_social_indicators()
        por_uf = self.get_state_social_indicators()
        resultado = {"total_anuais": len(anuais), "total_uf_sociais": len(por_uf)}
        if anuais:
            atomic_write_text(
                self.output_dir / "indicadores_sociais_anuais.csv", pd.DataFrame(anuais).to_csv(index=False)
            )
            atomic_write_json(self.output_dir / "indicadores_sociais_anuais.json", anuais)
        else:
            logger.error("Nenhum indicador anual obtido: arquivos anteriores preservados.")
        if por_uf:
            atomic_write_text(self.output_dir / "indicadores_sociais_uf.csv", pd.DataFrame(por_uf).to_csv(index=False))
            atomic_write_json(self.output_dir / "indicadores_sociais_uf.json", por_uf)
        else:
            logger.error("Nenhum indicador por UF obtido: arquivos anteriores preservados.")
        return resultado
