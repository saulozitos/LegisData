"""
Extrator oficial do TSE: candidaturas, bens declarados e receitas de campanha.

Fonte: Portal de Dados Abertos do TSE (CDN pública, sem chave)
  https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano}.zip
  https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_{ano}.zip
  https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ano}.zip
  https://cdn.tse.jus.br/estatistica/sead/odsele/motivo_cassacao/motivo_cassacao_{ano}.zip

Saídas (etl/data/processed/):
  tse_candidaturas.json  -> vínculo político <-> SQ_CANDIDATO por eleição + situação
  declaracoes_patrimonio.json -> total de bens declarados por eleição (com fonte)
  tse_receitas_campanha.json  -> receitas de campanha dos candidatos vinculados

Vínculo com os políticos do LegisData:
  - Deputados: CPF da API da Câmara (GET /api/v2/deputados/{id}; o CSV em lote
    'deputados.csv' traz a coluna cpf vazia) comparado com NR_CPF_CANDIDATO. O CPF é
    usado SOMENTE em memória como chave de junção e NÃO é gravado em disco.
  - Senadores e presidentes: a API do Senado não expõe CPF; usa-se nome civil completo
    normalizado + UF + cargo (5=Senador, 1=Presidente), aceitando apenas
    correspondência ÚNICA. Ambíguos são descartados e contados no log.

Privacidade (LGPD): CPF de doadores pessoas físicas não é gravado; CNPJ de pessoa
jurídica é mantido (dado empresarial público). Texto livre dos bens
(DS_BEM_CANDIDATO) não é gravado: só tipo e valor.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import time
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from etl.config import DEFAULT_USER_AGENT, PROCESSED_DATA_DIR, RAW_DATA_DIR

logger = logging.getLogger("TSEOficialExtractor")

CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"
URLS = {
    "consulta_cand": CDN + "/consulta_cand/consulta_cand_{ano}.zip",
    "bem_candidato": CDN + "/bem_candidato/bem_candidato_{ano}.zip",
    "prestacao_contas": CDN + "/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ano}.zip",
    "motivo_cassacao": CDN + "/motivo_cassacao/motivo_cassacao_{ano}.zip",
}
CAMARA_DEPUTADO_API = "https://dadosabertos.camara.leg.br/api/v2/deputados/{id}"

# Códigos de cargo do TSE
CARGO_PRESIDENTE = "1"
CARGO_SENADOR = "5"
CARGO_DEPUTADO_FEDERAL = "6"
CARGOS_FEDERAIS = {CARGO_PRESIDENTE, CARGO_SENADOR, CARGO_DEPUTADO_FEDERAL}

NULOS = {"", "#NULO", "#NULO#", "#NE", "#NE#", "-1", "-3"}

# Anos gerais com layout 'consulta_cand' compatível (verificado: 2014, 2018, 2022)
ANOS_PADRAO = (2014, 2018, 2022)


# ---------------------------------------------------------------------------
# Funções puras (testáveis sem rede e sem pandas)
# ---------------------------------------------------------------------------

def normalizar_nome(nome: Optional[str]) -> str:
    """Remove acentos, normaliza espaços e coloca em maiúsculas."""
    if not nome:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", nome) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sem_acento.upper().split())


def somente_digitos(valor: Optional[str]) -> str:
    return "".join(ch for ch in (valor or "") if ch.isdigit())


def valor_br(valor: Optional[str]) -> Optional[Decimal]:
    """Converte '1.234,56' -> Decimal('1234.56'). Retorna None para nulos do TSE."""
    if valor is None:
        return None
    v = valor.strip()
    if v in NULOS:
        return None
    v = v.replace(".", "").replace(",", ".")
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def limpar(valor: Optional[str]) -> Optional[str]:
    if valor is None:
        return None
    v = valor.strip()
    return None if v in NULOS else v


def documento_publicavel(doc: Optional[str]) -> Optional[str]:
    """Mantém CNPJ (14 dígitos); descarta CPF (11 dígitos) de pessoa física."""
    d = somente_digitos(doc)
    if len(d) == 14:
        return d
    return None


def ler_csv_tse(stream: io.BufferedIOBase) -> Iterator[Dict[str, str]]:
    """Lê CSV do TSE (latin-1, ';', aspas) devolvendo dicts."""
    texto = io.TextIOWrapper(stream, encoding="latin-1", newline="")
    yield from csv.DictReader(texto, delimiter=";", quotechar='"')


def indexar_unicos(chaves: Iterable[Tuple[Tuple[str, ...], str]]) -> Dict[Tuple[str, ...], str]:
    """Constrói índice chave->valor descartando chaves ambíguas (mais de um valor)."""
    vistos: Dict[Tuple[str, ...], set] = defaultdict(set)
    for chave, valor in chaves:
        vistos[chave].add(valor)
    return {k: next(iter(v)) for k, v in vistos.items() if len(v) == 1}


# ---------------------------------------------------------------------------
# Download com cache
# ---------------------------------------------------------------------------

def baixar(url: str, destino: Path, timeout: int = 120, tentativas: int = 3) -> Path:
    """Baixa em streaming; reaproveita o cache se o tamanho remoto não mudou."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if destino.exists():
        try:
            req = urllib.request.Request(url, method="HEAD", headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                if int(r.headers.get("Content-Length", -1)) == destino.stat().st_size:
                    logger.info(f"Cache válido: {destino.name}")
                    return destino
        except Exception as e:  # sem rede: usa o cache existente
            logger.warning(f"HEAD falhou para {url} ({e}); usando cache {destino.name}")
            return destino

    ultimo_erro: Optional[Exception] = None
    for tentativa in range(1, tentativas + 1):
        tmp = destino.with_suffix(destino.suffix + ".part")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
                while True:
                    bloco = r.read(1 << 20)
                    if not bloco:
                        break
                    f.write(bloco)
            tmp.replace(destino)
            logger.info(f"Baixado: {destino.name} ({destino.stat().st_size / 1e6:.1f} MB)")
            return destino
        except Exception as e:
            ultimo_erro = e
            logger.warning(f"Tentativa {tentativa} falhou para {url}: {e}")
            time.sleep(2 * tentativa)
    raise RuntimeError(f"Falha ao baixar {url}: {ultimo_erro}")


# ---------------------------------------------------------------------------
# Extrator
# ---------------------------------------------------------------------------

class TSEOficialExtractor:
    def __init__(self, anos: Iterable[int] = ANOS_PADRAO,
                 raw_dir: Path = RAW_DATA_DIR, processed_dir: Path = PROCESSED_DATA_DIR):
        self.anos = list(anos)
        self.raw_dir = Path(raw_dir) / "tse"
        self.processed_dir = Path(processed_dir)

    # ---- políticos do LegisData -------------------------------------------------
    def _politicos(self) -> Tuple[List[dict], List[dict], List[dict]]:
        def carregar(nome):
            p = self.processed_dir / nome
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        return carregar("deputados_camara.json"), carregar("senadores_senado.json"), carregar("presidentes_historico.json")

    def _cpfs_deputados(self, camara_ids: Iterable[int], intervalo: float = 0.2) -> Dict[str, int]:
        """CPF (só dígitos) -> camara_id, consultando a API da Câmara deputado a deputado.

        Mantido apenas em memória (não é escrito em cache nem nos arquivos de saída).
        """
        mapa: Dict[str, int] = {}
        falhas = 0
        headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
        for cid in sorted(set(camara_ids)):
            url = CAMARA_DEPUTADO_API.format(id=cid)
            for tentativa in range(3):
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                        dados = json.loads(r.read().decode("utf-8")).get("dados", {})
                    cpf = somente_digitos(dados.get("cpf"))
                    if len(cpf) == 11:
                        mapa[cpf] = int(cid)
                    break
                except Exception as e:
                    if tentativa == 2:
                        falhas += 1
                        logger.warning(f"Câmara: falha ao obter deputado {cid}: {e}")
                    time.sleep(1 + tentativa)
            time.sleep(intervalo)
        logger.info(f"Câmara: CPF obtido para {len(mapa)} deputados ({falhas} falhas)")
        return mapa

    # ---- candidaturas -----------------------------------------------------------
    def _candidaturas(self, ano: int) -> List[dict]:
        zpath = baixar(URLS["consulta_cand"].format(ano=ano), self.raw_dir / f"consulta_cand_{ano}.zip")
        linhas = []
        with zipfile.ZipFile(zpath) as z:
            membros = [n for n in z.namelist()
                       if n.endswith(".csv") and (n.endswith("_BRASIL.csv") or n.endswith("_BR.csv"))]
            for m in membros:
                with z.open(m) as f:
                    for r in ler_csv_tse(f):
                        if r.get("CD_CARGO") in CARGOS_FEDERAIS and r.get("NR_TURNO") == "1":
                            linhas.append(r)
        # _BRASIL pode ou não incluir a abrangência BR: deduplica por SQ_CANDIDATO
        unicos = {r["SQ_CANDIDATO"]: r for r in linhas}
        logger.info(f"[{ano}] {len(unicos)} candidaturas federais (Pres/Sen/Dep) lidas")
        return list(unicos.values())

    def _motivos(self, ano: int) -> Dict[str, List[dict]]:
        try:
            zpath = baixar(URLS["motivo_cassacao"].format(ano=ano), self.raw_dir / f"motivo_cassacao_{ano}.zip")
        except RuntimeError as e:
            logger.warning(f"[{ano}] motivo_cassacao indisponível: {e}")
            return {}
        out: Dict[str, List[dict]] = defaultdict(list)
        with zipfile.ZipFile(zpath) as z:
            for m in z.namelist():
                if m.endswith(".csv") and (m.endswith("_BRASIL.csv") or m.endswith("_BR.csv")):
                    with z.open(m) as f:
                        for r in ler_csv_tse(f):
                            out[r["SQ_CANDIDATO"]].append({
                                "numero_processo": limpar(r.get("NR_PROCESSO")),
                                "tipo_motivo": limpar(r.get("DS_TP_MOTIVO")),
                                "motivo": limpar(r.get("DS_MOTIVO")),
                            })
        # dedup
        return {k: [dict(t) for t in {tuple(sorted(d.items())) for d in v}] for k, v in out.items()}

    def vincular(self) -> List[dict]:
        """Retorna lista de candidaturas vinculadas a políticos do LegisData."""
        deputados, senadores, presidentes = self._politicos()
        ids_camara = {d["camara_id"] for d in deputados if d.get("camara_id")}
        cpf_para_camara = self._cpfs_deputados(ids_camara)

        # índice por nome civil + UF + cargo (senadores) e nome civil + cargo (presidentes)
        idx_sen = indexar_unicos(
            ((normalizar_nome(s.get("nome_civil")), s.get("uf") or "", CARGO_SENADOR), str(s["senado_id"]))
            for s in senadores if s.get("senado_id") and s.get("nome_civil")
        )
        idx_pres = indexar_unicos(
            ((normalizar_nome(p.get("nome_civil")), "BR", CARGO_PRESIDENTE), normalizar_nome(p.get("nome_civil")))
            for p in presidentes if p.get("nome_civil")
        )

        vinculos: List[dict] = []
        sem_vinculo = defaultdict(int)
        for ano in self.anos:
            cands = self._candidaturas(ano)
            motivos = self._motivos(ano)
            # para nomes: só aceitamos se o nome civil for único naquele ano/UF/cargo entre candidatos
            cont_nome = defaultdict(int)
            for r in cands:
                cont_nome[(normalizar_nome(r.get("NM_CANDIDATO")), r.get("SG_UF") or "", r.get("CD_CARGO"))] += 1

            for r in cands:
                cargo = r.get("CD_CARGO")
                alvo = None
                if cargo == CARGO_DEPUTADO_FEDERAL:
                    cid = cpf_para_camara.get(somente_digitos(r.get("NR_CPF_CANDIDATO")))
                    if cid:
                        alvo = {"camara_id": cid}
                else:
                    uf = "BR" if cargo == CARGO_PRESIDENTE else (r.get("SG_UF") or "")
                    chave = (normalizar_nome(r.get("NM_CANDIDATO")), uf, cargo)
                    chave_cont = (chave[0], r.get("SG_UF") or "", cargo)
                    if cont_nome[chave_cont] == 1:
                        if cargo == CARGO_SENADOR and chave in idx_sen:
                            alvo = {"senado_id": int(idx_sen[chave])}
                        elif cargo == CARGO_PRESIDENTE and chave in idx_pres:
                            alvo = {"nome_civil_normalizado": idx_pres[chave]}
                if not alvo:
                    sem_vinculo[(ano, cargo)] += 1
                    continue
                vinculos.append({
                    **alvo,
                    "ano_eleicao": ano,
                    "sq_candidato": r["SQ_CANDIDATO"],
                    "cargo_tse": limpar(r.get("DS_CARGO")),
                    "uf": limpar(r.get("SG_UF")),
                    "partido": limpar(r.get("SG_PARTIDO")),
                    "nome_urna": limpar(r.get("NM_URNA_CANDIDATO")),
                    "situacao_candidatura": limpar(r.get("DS_SITUACAO_CANDIDATURA")),
                    "situacao_turno": limpar(r.get("DS_SIT_TOT_TURNO")),
                    "motivos_indeferimento_cassacao": motivos.get(r["SQ_CANDIDATO"], []),
                    "fonte_url": URLS["consulta_cand"].format(ano=ano),
                })
        logger.info(f"Vínculos encontrados: {len(vinculos)}; sem vínculo (candidatos que não são "
                    f"políticos do LegisData ou ambíguos) por (ano, cargo): {dict(sem_vinculo)}")
        return vinculos

    # ---- bens ---------------------------------------------------------------------
    def bens(self, vinculos: List[dict]) -> List[dict]:
        por_ano: Dict[int, Dict[str, dict]] = defaultdict(dict)
        for v in vinculos:
            por_ano[v["ano_eleicao"]][v["sq_candidato"]] = v
        saida = []
        for ano, mapa in por_ano.items():
            zpath = baixar(URLS["bem_candidato"].format(ano=ano), self.raw_dir / f"bem_candidato_{ano}.zip")
            total: Dict[str, Decimal] = defaultdict(Decimal)
            n_bens: Dict[str, int] = defaultdict(int)
            por_tipo: Dict[str, Dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
            with zipfile.ZipFile(zpath) as z:
                membros = [n for n in z.namelist() if n.endswith(".csv") and not n.endswith("_BRASIL.csv")]
                vistos = set()
                for m in membros:
                    with z.open(m) as f:
                        for r in ler_csv_tse(f):
                            sq = r.get("SQ_CANDIDATO")
                            if sq not in mapa:
                                continue
                            chave = (sq, r.get("NR_ORDEM_BEM_CANDIDATO"))
                            if chave in vistos:
                                continue
                            vistos.add(chave)
                            val = valor_br(r.get("VR_BEM_CANDIDATO")) or Decimal("0")
                            total[sq] += val
                            n_bens[sq] += 1
                            tipo = limpar(r.get("DS_TIPO_BEM_CANDIDATO")) or "Não informado"
                            por_tipo[sq][tipo] += val
            for sq, v in mapa.items():
                if sq not in total:
                    continue
                tipos = sorted(por_tipo[sq].items(), key=lambda kv: kv[1], reverse=True)
                saida.append({
                    "camara_id": v.get("camara_id"),
                    "senado_id": v.get("senado_id"),
                    "nome_civil_normalizado": v.get("nome_civil_normalizado"),
                    "ano_eleicao": ano,
                    "sq_candidato": sq,
                    "valor_declarado_brl": float(total[sq]),
                    "quantidade_bens": n_bens[sq],
                    "detalhes_bens": "; ".join(f"{t}: R$ {float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                                               for t, val in tipos[:5]),
                    "fonte_url": URLS["bem_candidato"].format(ano=ano),
                })
        logger.info(f"Declarações de bens geradas: {len(saida)}")
        return saida

    # ---- receitas -------------------------------------------------------------------
    def receitas(self, vinculos: List[dict]) -> List[dict]:
        por_ano: Dict[int, Dict[str, dict]] = defaultdict(dict)
        for v in vinculos:
            por_ano[v["ano_eleicao"]][v["sq_candidato"]] = v
        saida = []
        for ano, mapa in por_ano.items():
            try:
                zpath = baixar(URLS["prestacao_contas"].format(ano=ano), self.raw_dir / f"prestacao_contas_{ano}.zip",
                               timeout=600)
            except RuntimeError as e:
                logger.warning(f"[{ano}] prestação de contas indisponível: {e}")
                continue
            with zipfile.ZipFile(zpath) as z:
                prefixo = f"receitas_candidatos_{ano}_"
                membros = [n for n in z.namelist()
                           if n.startswith(prefixo) and n.endswith(".csv")
                           and "BRASIL" not in n and "doador_originario" not in n]
                if not membros:
                    logger.warning(f"[{ano}] nenhum arquivo {prefixo}*.csv (layout diferente?) — ano ignorado")
                    continue
                vistos = set()
                for m in membros:
                    with z.open(m) as f:
                        for r in ler_csv_tse(f):
                            sq = r.get("SQ_CANDIDATO")
                            if sq not in mapa:
                                continue
                            # Só a prestação FINAL (as parciais duplicariam valores)
                            if (r.get("TP_PRESTACAO_CONTAS") or "").upper() != "FINAL":
                                continue
                            sq_rec = r.get("SQ_RECEITA")
                            if sq_rec in vistos:
                                continue
                            vistos.add(sq_rec)
                            valor = valor_br(r.get("VR_RECEITA"))
                            if valor is None:
                                continue
                            v = mapa[sq]
                            saida.append({
                                "camara_id": v.get("camara_id"),
                                "senado_id": v.get("senado_id"),
                                "nome_civil_normalizado": v.get("nome_civil_normalizado"),
                                "ano_eleicao": ano,
                                "sq_candidato": sq,
                                "sq_receita": sq_rec,
                                "nome_doador": limpar(r.get("NM_DOADOR_RFB")) or limpar(r.get("NM_DOADOR")) or "Não informado",
                                "cnpj_doador": documento_publicavel(r.get("NR_CPF_CNPJ_DOADOR")),
                                "origem_receita": limpar(r.get("DS_ORIGEM_RECEITA")),
                                "fonte_recurso": limpar(r.get("DS_FONTE_RECEITA")),
                                "natureza": limpar(r.get("DS_NATUREZA_RECEITA")),
                                "data_receita": limpar(r.get("DT_RECEITA")),
                                "valor": float(valor),
                                "fonte_url": URLS["prestacao_contas"].format(ano=ano),
                            })
        logger.info(f"Receitas de campanha vinculadas: {len(saida)}")
        return saida

    # ---- execução ---------------------------------------------------------------------
    def run(self, incluir_receitas: bool = True) -> Dict[str, int]:
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        vinculos = self.vincular()
        bens = self.bens(vinculos)
        receitas = self.receitas(vinculos) if incluir_receitas else []

        def salvar(nome, dados):
            (self.processed_dir / nome).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")

        salvar("tse_candidaturas.json", vinculos)
        salvar("declaracoes_patrimonio.json", bens)
        if incluir_receitas:
            salvar("tse_receitas_campanha.json", receitas)
        return {"candidaturas": len(vinculos), "declaracoes_bens": len(bens), "receitas": len(receitas)}


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="Extrai candidaturas, bens e receitas oficiais do TSE")
    ap.add_argument("--anos", nargs="*", type=int, default=list(ANOS_PADRAO))
    ap.add_argument("--sem-receitas", action="store_true", help="Não baixa a prestação de contas (arquivos de 200-475 MB)")
    a = ap.parse_args()
    print(TSEOficialExtractor(anos=a.anos).run(incluir_receitas=not a.sem_receitas))
