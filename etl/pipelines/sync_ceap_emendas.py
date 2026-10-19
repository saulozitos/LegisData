"""
Pipeline unificado e idempotente de CEAP (Câmara + Senado) e Emendas Parlamentares.

Substitui `sync_ceap_emendas_2019_2026.py` e `sync_ceap_emendas_lula_bolsonaro.py`, que:
  * gravavam nos mesmos arquivos com esquemas diferentes (chave `por_ano` int x str, cargo DEPUTADO x DEPUTADO_FEDERAL);
  * somavam sobre o resumo existente (rodar duas vezes duplicava `total_gasto`);
  * usavam `hash()` (não determinístico) e aceitavam respostas truncadas (`IncompleteRead.partial`);
  * fabricavam emendas com tetos e cidades inventados.

Aqui o resultado é sempre recalculado do zero para o intervalo pedido (mesma entrada => mesma saída),
as agregações usam identificadores oficiais (ideCadastro / codSenador) e nada é gravado se a extração falhar.

Uso:
    python -m etl.pipelines.sync_ceap_emendas --ano-inicio 2019 --ano-fim 2026
"""

import argparse
import copy
import io
import json
import logging
import time
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.emendas_extractor import EmendasExtractor
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json, write_json_if_valid
from etl.utils.provenance import mark_official

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CeapEmendasSync")

CEAP_OUTPUT = "despesas_ceap_2019_2026.json"  # nome mantido: o `financas_loader` lê este arquivo e grava em `fin` (a API não abre arquivos)
EMENDAS_OUTPUT = "emendas_parlamentares_2019_2026.json"
ANO_INICIAL_CEAP = 2008  # início da publicação aberta da CEAP
TOP_FORNECEDORES = 15
FONTE_CEAP_CAMARA = "Câmara dos Deputados — Cota Parlamentar (CSV oficial)"
FONTE_CEAP_SENADO = "Senado Federal — CEAPS (API de Dados Abertos Administrativos)"

CAMARA_COLS = {
    "txNomeParlamentar",
    "ideCadastro",
    "sgUF",
    "sgPartido",
    "numAno",
    "numMes",
    "txtDescricao",
    "vlrLiquido",
    "txtFornecedor",
    "txtCNPJCPF",
}


class CeapAccumulator:
    """
    Acumula despesas por parlamentar. Chave = (cargo, identificador oficial); o nome é só rótulo.
    Valores negativos (estornos) reduzem os totais; `total_notas` conta apenas lançamentos positivos.
    """

    def __init__(self) -> None:
        self._dados: Dict[Tuple[str, Any], Dict[str, Any]] = {}

    def add(
        self,
        cargo: str,
        ident: Any,
        nome: str,
        ano: int,
        mes: Optional[int],
        tipo: str,
        fornecedor: str,
        cnpj: Optional[str],
        valor: float,
    ) -> None:
        if not nome or valor == 0:
            return
        chave = (cargo, ident if ident is not None else nome.upper().strip())
        reg = self._dados.setdefault(
            chave,
            {
                "nome": nome.upper().strip(),
                "cargo": cargo,
                "camara_id": ident if cargo == "DEPUTADO_FEDERAL" else None,
                "senado_id": ident if cargo == "SENADOR" else None,
                "total_gasto": 0.0,
                "total_notas": 0,
                "por_ano": {},
                "por_tipo": {},
                "por_ano_tipo": {},
                "fornecedores": {},
            },
        )
        ano_s = str(ano)
        reg["total_gasto"] += valor
        if valor > 0:
            reg["total_notas"] += 1
        reg["por_ano"][ano_s] = reg["por_ano"].get(ano_s, 0.0) + valor
        reg["por_tipo"][tipo] = reg["por_tipo"].get(tipo, 0.0) + valor
        por_tipo_ano = reg["por_ano_tipo"].setdefault(ano_s, {})
        por_tipo_ano[tipo] = por_tipo_ano.get(tipo, 0.0) + valor

        forn = reg["fornecedores"].setdefault(
            fornecedor, {"nome": fornecedor, "cnpj_cpf": cnpj, "total": 0.0, "notas": 0}
        )
        forn["total"] += valor
        if valor > 0:
            forn["notas"] += 1
        if not forn.get("cnpj_cpf") and cnpj:
            forn["cnpj_cpf"] = cnpj

    def para_json(self) -> List[Dict[str, Any]]:
        """Estado completo (sem truncar fornecedores) para o cache por ano; a chave vira lista [cargo, identificador]."""
        return [{"chave": [cargo, ident], "reg": reg} for (cargo, ident), reg in self._dados.items()]

    @classmethod
    def de_json(cls, itens: List[Dict[str, Any]]) -> "CeapAccumulator":
        acc = cls()
        for item in itens:
            cargo, ident = item["chave"]
            acc._dados[(cargo, ident)] = item["reg"]
        return acc

    def mesclar(self, outro: "CeapAccumulator") -> None:
        """
        Soma os totais de `outro` (anos diferentes dos já acumulados). O nome do rótulo é o do último acumulador
        mesclado, então mescle em ordem crescente de ano para ficar com o nome mais recente do parlamentar.
        """
        for chave, novo in outro._dados.items():
            reg = self._dados.get(chave)
            if reg is None:
                self._dados[chave] = copy.deepcopy(novo)
                continue
            reg["nome"] = novo["nome"]
            reg["total_gasto"] += novo["total_gasto"]
            reg["total_notas"] += novo["total_notas"]
            for campo in ("por_ano", "por_tipo"):
                for k, v in novo[campo].items():
                    reg[campo][k] = reg[campo].get(k, 0.0) + v
            for ano, tipos in novo["por_ano_tipo"].items():
                destino = reg["por_ano_tipo"].setdefault(ano, {})
                for tipo, v in tipos.items():
                    destino[tipo] = destino.get(tipo, 0.0) + v
            for nome_f, forn in novo["fornecedores"].items():
                atual = reg["fornecedores"].setdefault(
                    nome_f, {"nome": nome_f, "cnpj_cpf": forn.get("cnpj_cpf"), "total": 0.0, "notas": 0}
                )
                atual["total"] += forn["total"]
                atual["notas"] += forn["notas"]
                if not atual.get("cnpj_cpf") and forn.get("cnpj_cpf"):
                    atual["cnpj_cpf"] = forn["cnpj_cpf"]

    def finalize(self, fonte_por_cargo: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        """Arredonda, mantém os maiores fornecedores e resolve homônimos sem perder ninguém."""
        saida: Dict[str, Dict[str, Any]] = {}
        for (cargo, ident), reg in sorted(self._dados.items(), key=lambda kv: (kv[1]["nome"], str(kv[0][1]))):
            top = sorted(reg["fornecedores"].values(), key=lambda f: f["total"], reverse=True)[:TOP_FORNECEDORES]
            final = {
                **reg,
                "total_gasto": round(reg["total_gasto"], 2),
                "por_ano": {a: round(v, 2) for a, v in sorted(reg["por_ano"].items())},
                "por_tipo": {t: round(v, 2) for t, v in sorted(reg["por_tipo"].items())},
                "por_ano_tipo": {
                    a: {t: round(v, 2) for t, v in sorted(tipos.items())}
                    for a, tipos in sorted(reg["por_ano_tipo"].items())
                },
                "fornecedores": {f["nome"]: {**f, "total": round(f["total"], 2)} for f in top},
            }
            mark_official(final, fonte_por_cargo[cargo])
            nome = reg["nome"]
            if nome in saida:  # homônimo: desambigua pelo identificador oficial
                nome = f"{nome} [{ident}]"
            saida[nome] = final
        return saida


def _num(valor: Any) -> float:
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def extract_camara_ceap(http: HttpClient, anos: Iterable[int], acc: CeapAccumulator) -> Tuple[int, List[int]]:
    """Baixa o CSV anual da Câmara. Devolve (registros, anos_com_falha)."""
    total, falhas = 0, []
    for i, ano in enumerate(anos):
        if i:
            time.sleep(PAUSA_ENTRE_DOWNLOADS)  # a Câmara responde 429 a vários CSVs anuais seguidos
        t0 = time.time()
        url = f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
        try:
            conteudo = http.get_bytes(url)
            with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
                with z.open(z.namelist()[0]) as f:
                    df = pd.read_csv(
                        f,
                        sep=";",
                        encoding="utf-8-sig",
                        low_memory=False,
                        usecols=lambda c: c in CAMARA_COLS,
                    )
        except (HttpError, zipfile.BadZipFile, ValueError, IndexError) as exc:
            logger.warning("[Câmara %s] falha na extração: %s", ano, exc)
            falhas.append(ano)
            continue

        df["vlrLiquido"] = df["vlrLiquido"].map(_num)
        for row in df.to_dict(orient="records"):
            ide = row.get("ideCadastro")
            ident = int(ide) if pd.notna(ide) else None
            acc.add(
                "DEPUTADO_FEDERAL",
                ident,
                str(row.get("txNomeParlamentar") or ""),
                int(row.get("numAno") or ano),
                int(row["numMes"]) if pd.notna(row.get("numMes")) else None,
                str(row.get("txtDescricao") or "OUTROS").strip(),
                str(row.get("txtFornecedor") or "Não informado").strip(),
                str(row["txtCNPJCPF"]) if pd.notna(row.get("txtCNPJCPF")) else None,
                row["vlrLiquido"],
            )
        total += len(df)
        logger.info("[Câmara %s] %s registros em %.1fs", ano, f"{len(df):,}", time.time() - t0)
    return total, falhas


def extract_senado_ceaps(http: HttpClient, anos: Iterable[int], acc: CeapAccumulator) -> Tuple[int, List[int]]:
    """Baixa a CEAPS do Senado ano a ano. Respostas truncadas são re-tentadas (nunca aceitas)."""
    total, falhas = 0, []
    for ano in anos:
        t0 = time.time()
        url = f"https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}"
        try:
            dados = http.get_json(url)
        except HttpError as exc:
            logger.warning("[Senado %s] falha na extração: %s", ano, exc)
            falhas.append(ano)
            continue
        itens = dados if isinstance(dados, list) else (dados or {}).get("despesas", [])
        for item in itens:
            cod = item.get("codSenador")
            acc.add(
                "SENADOR",
                int(cod) if cod not in (None, "") else None,
                str(item.get("nomeSenador") or ""),
                int(item.get("ano") or ano),
                int(item["mes"]) if item.get("mes") else None,
                str(item.get("tipoDespesa") or "OUTROS").strip(),
                str(item.get("fornecedor") or "Não informado").strip(),
                item.get("cpfCnpj"),
                _num(item.get("valorReembolsado")),
            )
        total += len(itens)
        logger.info("[Senado %s] %s registros em %.1fs", ano, f"{len(itens):,}", time.time() - t0)
    return total, falhas


VERSAO_DO_CACHE = 1
PASTA_DO_CACHE = "ceap_por_ano"
# A Câmara responde 429 (Too Many Requests) quando os CSVs anuais são pedidos em sequência (visto com 7 downloads em
# 30 s): entre dois downloads espera-se um pouco, e um ano que falhou ganha uma segunda tentativa depois de uma pausa maior.
PAUSA_ENTRE_DOWNLOADS = 10.0
ESPERA_NOVA_TENTATIVA = 90.0


def _definitivo(ano: int, hoje: date) -> bool:
    """
    A CEAP de um ano só é dado fechado depois de 1º de abril do ano seguinte (a Câmara e o Senado ainda corrigem
    lançamentos nos primeiros meses). Antes disso o ano é baixado de novo a cada execução e nunca fica em cache.
    """
    return hoje >= date(ano + 1, 4, 1)


def _arquivo_do_cache(cache_dir: Path, casa: str, ano: int) -> Path:
    return Path(cache_dir) / f"{casa}_{ano}.json"


def _ler_cache(cache_dir: Path, casa: str, ano: int) -> Optional[CeapAccumulator]:
    caminho = _arquivo_do_cache(cache_dir, casa, ano)
    try:
        conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(conteudo, dict) or conteudo.get("versao") != VERSAO_DO_CACHE:
        return None
    if conteudo.get("casa") != casa or conteudo.get("ano") != ano or not isinstance(conteudo.get("dados"), list):
        return None
    try:
        return CeapAccumulator.de_json(conteudo["dados"])
    except (KeyError, TypeError, ValueError):
        return None


def _gravar_cache(cache_dir: Path, casa: str, ano: int, acc: CeapAccumulator) -> None:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        _arquivo_do_cache(cache_dir, casa, ano),
        {"versao": VERSAO_DO_CACHE, "casa": casa, "ano": ano, "dados": acc.para_json()},
        indent=None,
    )


def _extrair_com_cache(
    http: HttpClient,
    anos: Iterable[int],
    casa: str,
    extrator: Any,
    acc: CeapAccumulator,
    cache_dir: Path,
    hoje: date,
) -> Tuple[int, List[int], List[int]]:
    """
    Extrai ano a ano: ano fechado já em cache entra sem baixar nada; os demais são baixados e, se o ano já está fechado
    (`_definitivo`) e trouxe dados, vão para o cache. Entre downloads há uma pausa e um ano que falha é tentado de novo
    uma vez (a Câmara limita pedidos em sequência). Devolve (registros baixados, anos com falha, anos vindos do cache).
    A mescla é em ordem crescente de ano. Uma falha em qualquer ano continua abortando a gravação do arquivo final.
    """
    total, falhas, do_cache = 0, [], []
    baixou = False
    for ano in sorted(anos):
        guardado = _ler_cache(cache_dir, casa, ano) if _definitivo(ano, hoje) else None
        if guardado is not None:
            acc.mesclar(guardado)
            do_cache.append(ano)
            continue
        if baixou:
            time.sleep(PAUSA_ENTRE_DOWNLOADS)
        baixou = True
        parcial = CeapAccumulator()
        n, falhou = extrator(http, [ano], parcial)
        if falhou:
            logger.warning("[%s %s] falhou; nova tentativa em %.0fs", casa, ano, ESPERA_NOVA_TENTATIVA)
            time.sleep(ESPERA_NOVA_TENTATIVA)
            parcial = CeapAccumulator()
            n, falhou = extrator(http, [ano], parcial)
        if falhou:
            falhas.extend(falhou)
            continue
        total += n
        if _definitivo(ano, hoje) and parcial._dados:
            _gravar_cache(cache_dir, casa, ano, parcial)
        acc.mesclar(parcial)
    return total, falhas, do_cache


def run(
    ano_inicio: int = ANO_INICIAL_CEAP,
    ano_fim: Optional[int] = None,
    ceap: bool = True,
    emendas: bool = True,
    http: Optional[HttpClient] = None,
    cache_dir: Optional[Path] = None,
    hoje: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Sincroniza CEAP e emendas. Com `cache_dir`, a CEAP de cada ano já fechado (depois de 1º de abril do ano seguinte) é
    guardada e não é baixada de novo: a atualização diária só refaz o ano corrente (e o anterior até março).
    """
    hoje = hoje or date.today()
    ano_fim = ano_fim or hoje.year
    if ano_inicio > ano_fim:
        raise ValueError("ano_inicio não pode ser maior que ano_fim")
    http = http or HttpClient(timeout=60.0, max_retries=3)
    anos = list(range(ano_inicio, ano_fim + 1))
    resumo: Dict[str, Any] = {"anos": f"{ano_inicio}-{ano_fim}"}

    if ceap:
        acc = CeapAccumulator()
        if cache_dir is None:
            n_cam, falhas_cam = extract_camara_ceap(http, anos, acc)
            n_sen, falhas_sen = extract_senado_ceaps(http, anos, acc)
        else:
            n_cam, falhas_cam, cache_cam = _extrair_com_cache(
                http, anos, "camara", extract_camara_ceap, acc, cache_dir, hoje
            )
            n_sen, falhas_sen, cache_sen = _extrair_com_cache(
                http, anos, "senado", extract_senado_ceaps, acc, cache_dir, hoje
            )
            resumo["ceap_anos_do_cache"] = {"camara": cache_cam, "senado": cache_sen}
        falhas = {"camara": falhas_cam, "senado": falhas_sen}
        resumo.update({"ceap_registros": n_cam + n_sen, "ceap_falhas": falhas})
        if falhas_cam or falhas_sen:
            # Um ano faltando silenciosamente geraria totais subestimados: aborta sem gravar.
            logger.error("CEAP incompleta (anos com falha: %s). Arquivo anterior preservado.", falhas)
            resumo["ceap_gravado"] = False
        else:
            resultado = acc.finalize({"DEPUTADO_FEDERAL": FONTE_CEAP_CAMARA, "SENADOR": FONTE_CEAP_SENADO})
            resumo["ceap_gravado"] = write_json_if_valid(PROCESSED_DATA_DIR / CEAP_OUTPUT, resultado, indent=None)
            resumo["ceap_parlamentares"] = len(resultado)

    if emendas:
        registros = EmendasExtractor().fetch_portal()
        registros = [r for r in registros if ano_inicio <= r["ano"] <= ano_fim] if registros else []
        resumo["emendas_registros"] = len(registros)
        resumo["emendas_gravado"] = write_json_if_valid(PROCESSED_DATA_DIR / EMENDAS_OUTPUT, registros, indent=None)

    logger.info("Sincronização concluída: %s", resumo)
    return resumo


def main(argv: Optional[List[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Sincroniza CEAP (Câmara/Senado) e emendas parlamentares.")
    parser.add_argument("--ano-inicio", type=int, default=ANO_INICIAL_CEAP)
    parser.add_argument("--ano-fim", type=int, default=None)
    parser.add_argument("--sem-ceap", action="store_true")
    parser.add_argument("--sem-emendas", action="store_true")
    args = parser.parse_args(argv)
    return run(args.ano_inicio, args.ano_fim, ceap=not args.sem_ceap, emendas=not args.sem_emendas)


if __name__ == "__main__":
    main()
