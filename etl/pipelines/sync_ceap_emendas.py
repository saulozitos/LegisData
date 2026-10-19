"""
Pipeline unificado e idempotente de CEAP (Câmara + Senado) e Emendas Parlamentares.

Substitui `sync_ceap_emendas_2019_2026.py` e `sync_ceap_emendas_lula_bolsonaro.py`, que:
  * gravavam nos mesmos arquivos com esquemas diferentes (chave `por_ano` int x str, cargo DEPUTADO x DEPUTADO_FEDERAL);
  * somavam sobre o resumo existente (rodar duas vezes duplicava `total_gasto`);
  * usavam `hash()` (não determinístico) e aceitavam respostas truncadas (`IncompleteRead.partial`);
  * fabricavam emendas com tetos e cidades inventados.

Aqui o resultado é sempre recalculado do zero para o intervalo pedido (mesma entrada => mesma saída),
as agregações usam identificadores oficiais (ideCadastro / codSenador) e nada é gravado se a extração falhar.

CPF de fornecedor pessoa física nunca é gravado (decisão D3): `CeapAccumulator.add` guarda só o CNPJ de 14 dígitos e o
nome sem CPF embutido, então nem o arquivo processado nem o cache por ano carregam o documento da fonte.

Cada ano é baixado separadamente. Com `cache_dir`, o ano já fechado (depois de 1º de abril do ano seguinte) fica em
cache e só é baixado de novo quando o cache vence (`VALIDADE_DO_CACHE_DIAS`); a atualização diária vai à rede apenas
para o ano corrente (e o anterior até março). Com ou sem cache, vale a mesma política de rede: pausa entre downloads
(a Câmara responde 429 a vários CSVs anuais seguidos), uma segunda tentativa depois de uma pausa maior, e um ano que
volta vazio é falha (nunca "gasto zero").

Uso:
    python -m etl.pipelines.sync_ceap_emendas --ano-inicio 2019 --ano-fim 2026
"""

import argparse
import copy
import io
import json
import logging
import math
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.emendas_extractor import EmendasExtractor
from etl.pipelines.loader_helpers import cnpj_do_fornecedor, nome_do_fornecedor
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json, write_json_if_valid
from etl.utils.provenance import mark_official

logger = logging.getLogger("CeapEmendasSync")

CEAP_OUTPUT = "despesas_ceap_2019_2026.json"  # nome mantido: o `financas_loader` lê este arquivo e grava em `fin` (a API não abre arquivos)
EMENDAS_OUTPUT = "emendas_parlamentares_2019_2026.json"
ANO_INICIAL_CEAP = 2008  # início da publicação aberta da CEAP
ANO_INICIAL_ARQUIVO = 2019  # início dos arquivos processados (`run_etl --ceap-ano-inicio` e a atualização diária)
TOP_FORNECEDORES = 15
FONTE_CEAP_CAMARA = "Câmara dos Deputados — Cota Parlamentar (CSV oficial)"
FONTE_CEAP_SENADO = "Senado Federal — CEAPS (API de Dados Abertos Administrativos)"
CARGOS = frozenset({"DEPUTADO_FEDERAL", "SENADOR"})

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

# ── Política de rede e de cache ───────────────────────────────────────────────────────────────────────────────────────
# Suba VERSAO_DO_CACHE a cada mudança no formato do cache ou na regra de agregação (`CeapAccumulator.add`, `para_json`,
# `mesclar`, colunas lidas): os anos fechados em cache carregariam a regra antiga para sempre. Um teste trava o formato.
VERSAO_DO_CACHE = 2
PASTA_DO_CACHE = "ceap_por_ano"
VALIDADE_DO_CACHE_DIAS = 90  # um ano fechado é baixado de novo depois disso (estornos e correções tardias)
# A Câmara responde 429 (Too Many Requests) a vários CSVs anuais seguidos (visto com 7 downloads em 30 s). O Senado
# limita em 10 requisições por segundo e aqui há uma por ano; a pausa dele é só cortesia.
PAUSA_POR_CASA = {"camara": 10.0, "senado": 1.0}
ESPERA_NOVA_TENTATIVA = 90.0
TETO_DO_DOWNLOAD = 300 * 1024 * 1024  # os CSVs anuais compactados têm cerca de 4 MB
TETO_DO_CSV = 1024 * 1024 * 1024  # tamanho descomprimido máximo aceito (o contêiner tem 2 GB de memória)
FUSO_DO_BRASIL = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019
FRACAO_MINIMA_DAS_EMENDAS = 0.8  # lista de emendas com menos que isso do arquivo anterior é tratada como truncada


def hoje_no_brasil() -> date:
    """A data em Brasília: o servidor e os contêineres rodam em UTC, e 1º de abril vira às 21h do dia 31."""
    return datetime.now(FUSO_DO_BRASIL).date()


def _numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


def _inteiro(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0


def _validar_registro(chave: Any, reg: Any) -> Tuple[str, Any]:
    """Confere a forma completa de um item do cache; qualquer divergência levanta ValueError (cache refeito)."""
    if not (isinstance(chave, list) and len(chave) == 2):
        raise ValueError("chave do cache fora do formato [cargo, identificador]")
    cargo, ident = chave
    if cargo not in CARGOS or isinstance(ident, bool) or not isinstance(ident, (int, str)):
        raise ValueError("cargo ou identificador inválido")
    if not isinstance(reg, dict):
        raise ValueError("registro do cache não é objeto")
    if not (isinstance(reg.get("nome"), str) and reg["nome"] and reg.get("cargo") == cargo):
        raise ValueError("nome ou cargo do registro inválido")
    if "camara_id" not in reg or "senado_id" not in reg:
        raise ValueError("registro sem camara_id/senado_id")
    if not (_numero(reg.get("total_gasto")) and _inteiro(reg.get("total_notas")) and _inteiro(reg.get("nome_ano"))):
        raise ValueError("totais do registro inválidos")
    for campo in ("por_ano", "por_tipo"):
        mapa = reg.get(campo)
        if not isinstance(mapa, dict) or not all(isinstance(k, str) and _numero(v) for k, v in mapa.items()):
            raise ValueError(f"{campo} inválido")
    por_ano_tipo = reg.get("por_ano_tipo")
    if not isinstance(por_ano_tipo, dict) or not all(
        isinstance(a, str) and isinstance(t, dict) and all(isinstance(k, str) and _numero(v) for k, v in t.items())
        for a, t in por_ano_tipo.items()
    ):
        raise ValueError("por_ano_tipo inválido")
    fornecedores = reg.get("fornecedores")
    if not isinstance(fornecedores, dict) or not all(
        isinstance(n, str)
        and isinstance(f, dict)
        and isinstance(f.get("nome"), str)
        and _numero(f.get("total"))
        and _inteiro(f.get("notas"))
        and (f.get("cnpj_cpf") is None or isinstance(f["cnpj_cpf"], str))
        for n, f in fornecedores.items()
    ):
        raise ValueError("fornecedores inválidos")
    return cargo, ident


class CeapAccumulator:
    """
    Acumula despesas por parlamentar. Chave = (cargo, identificador oficial); o nome é só rótulo (o do ano mais recente).
    Valores negativos (estornos) reduzem os totais; `total_notas` conta apenas lançamentos positivos.
    """

    def __init__(self) -> None:
        self._dados: Dict[Tuple[str, Any], Dict[str, Any]] = {}

    @property
    def vazio(self) -> bool:
        return not self._dados

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
        # Nada de CPF em disco (D3): só o CNPJ de 14 dígitos fica, e o nome perde o CPF embutido (MEI aparece como
        # "NOME 09876543200"). O loader aplica as mesmas regras, então o `fin` recebe o mesmo que recebia antes.
        fornecedor = nome_do_fornecedor(fornecedor)
        cnpj = cnpj_do_fornecedor(cnpj)
        chave = (cargo, ident if ident is not None else nome.upper().strip())
        reg = self._dados.setdefault(
            chave,
            {
                "nome": nome.upper().strip(),
                "nome_ano": ano,
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
        if ano > reg["nome_ano"]:  # o rótulo é o do lançamento mais recente, na ordem que os anos chegarem
            reg["nome"], reg["nome_ano"] = nome.upper().strip(), ano
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
    def de_json(cls, itens: Any) -> "CeapAccumulator":
        """Reconstrói o acumulador de um cache; forma inválida em qualquer item levanta ValueError."""
        if not isinstance(itens, list):
            raise ValueError("dados do cache não são lista")
        acc = cls()
        for item in itens:
            if not isinstance(item, dict) or "chave" not in item or "reg" not in item:
                raise ValueError("item do cache sem chave/reg")
            cargo, ident = _validar_registro(item["chave"], item["reg"])
            acc._dados[(cargo, ident)] = item["reg"]
        return acc

    def mesclar(self, outro: "CeapAccumulator") -> None:
        """Soma os totais de `outro` (anos diferentes dos já acumulados). O nome é o do ano mais recente, em qualquer ordem."""
        for chave, novo in outro._dados.items():
            reg = self._dados.get(chave)
            if reg is None:
                self._dados[chave] = copy.deepcopy(novo)
                continue
            if novo["nome_ano"] > reg["nome_ano"]:
                reg["nome"], reg["nome_ano"] = novo["nome"], novo["nome_ano"]
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
                **{k: v for k, v in reg.items() if k != "nome_ano"},  # detalhe interno do acumulador
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


Extrator = Callable[..., Tuple[int, List[int]]]


def extract_camara_ceap(
    http: HttpClient, anos: Iterable[int], acc: CeapAccumulator, ausentes: Optional[List[int]] = None
) -> Tuple[int, List[int]]:
    """
    Baixa o CSV anual da Câmara. Devolve (registros, anos_com_falha). Um ano cujo arquivo não existe (HTTP 404) entra
    também em `ausentes`, para o chamador distinguir "ainda não publicado" de falha de rede.
    """
    total, falhas = 0, []
    for ano in anos:
        t0 = time.time()
        url = f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
        try:
            conteudo = http.get_bytes(url, max_bytes=TETO_DO_DOWNLOAD)
            with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
                membro = z.infolist()[0]
                if membro.file_size > TETO_DO_CSV:
                    raise ValueError(f"CSV descomprimido de {membro.file_size} bytes passa do teto de {TETO_DO_CSV}")
                with z.open(membro) as f:
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
            if isinstance(exc, HttpError) and exc.status == 404 and ausentes is not None:
                ausentes.append(ano)
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


def extract_senado_ceaps(
    http: HttpClient, anos: Iterable[int], acc: CeapAccumulator, ausentes: Optional[List[int]] = None
) -> Tuple[int, List[int]]:
    """Baixa a CEAPS do Senado ano a ano. Respostas truncadas são re-tentadas (nunca aceitas)."""
    total, falhas = 0, []
    for ano in anos:
        t0 = time.time()
        url = f"https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}"
        try:
            dados = http.get_json(url, max_bytes=TETO_DO_DOWNLOAD)
        except HttpError as exc:
            logger.warning("[Senado %s] falha na extração: %s", ano, exc)
            falhas.append(ano)
            if exc.status == 404 and ausentes is not None:
                ausentes.append(ano)
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


# ── Cache por ano ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _definitivo(ano: int, hoje: date) -> bool:
    """
    A CEAP de um ano só é dado fechado depois de 1º de abril do ano seguinte (a Câmara e o Senado ainda corrigem
    lançamentos nos primeiros meses). Antes disso o ano é baixado de novo a cada execução e nunca fica em cache.
    """
    return hoje >= date(ano + 1, 4, 1)


def _arquivo_do_cache(cache_dir: Path, casa: str, ano: int) -> Path:
    return Path(cache_dir) / f"{casa}_{ano}.json"


def _ler_cache(cache_dir: Path, casa: str, ano: int, hoje: date) -> Optional[CeapAccumulator]:
    """O cache do ano, ou None se não existe, tem forma inválida, é de outra versão, nasceu antes de o ano fechar ou venceu."""
    try:
        conteudo = json.loads(_arquivo_do_cache(cache_dir, casa, ano).read_text(encoding="utf-8"))
        if not isinstance(conteudo, dict) or conteudo.get("versao") != VERSAO_DO_CACHE:
            return None
        if conteudo.get("casa") != casa or conteudo.get("ano") != ano or not conteudo.get("dados"):
            return None
        gerado_em = date.fromisoformat(conteudo["gerado_em"])
        if not _definitivo(ano, gerado_em) or (hoje - gerado_em).days > VALIDADE_DO_CACHE_DIAS:
            return None
        return CeapAccumulator.de_json(conteudo["dados"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _gravar_cache(cache_dir: Path, casa: str, ano: int, acc: CeapAccumulator, hoje: date) -> None:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        _arquivo_do_cache(cache_dir, casa, ano),
        {
            "versao": VERSAO_DO_CACHE,
            "casa": casa,
            "ano": ano,
            "gerado_em": hoje.isoformat(),
            "dados": acc.para_json(),
        },
        indent=None,
    )


def _baixar_ano(
    http: HttpClient, ano: int, casa: str, extrator: Extrator, hoje: date
) -> Tuple[Optional[CeapAccumulator], bool]:
    """
    Baixa um ano, com uma segunda tentativa depois de `ESPERA_NOVA_TENTATIVA` (menos para arquivo inexistente).
    Devolve (acumulador, ainda_sem_arquivo): acumulador None é falha; `ainda_sem_arquivo` só vale para o ano corrente
    em janeiro, quando o arquivo do ano novo pode não ter sido publicado (falta de arquivo não é zero gasto).
    """
    for tentativa in (1, 2):
        parcial, ausentes = CeapAccumulator(), []
        _, falhou = extrator(http, [ano], parcial, ausentes=ausentes)
        if not falhou and not parcial.vazio:
            return parcial, False
        if falhou and ano in ausentes:
            if ano == hoje.year and hoje.month == 1:
                return None, True
            break  # 404 em outro ano ou época é falha de verdade, e repetir não faz o arquivo aparecer
        if not falhou and ano == hoje.year and hoje.month == 1:
            return None, True  # resposta vazia no começo do ano corrente: ainda não há despesa lançada
        logger.warning(
            "[%s %s] %s; %s",
            casa,
            ano,
            "falhou" if falhou else "veio vazio",
            "nova tentativa depois da pausa" if tentativa == 1 else "desistindo",
        )
        if tentativa == 1:
            time.sleep(ESPERA_NOVA_TENTATIVA)
    return None, False


def _extrair_anos(
    http: HttpClient,
    anos: Iterable[int],
    casa: str,
    extrator: Extrator,
    acc: CeapAccumulator,
    cache_dir: Optional[Path],
    hoje: date,
) -> Tuple[int, List[int], List[int], List[int]]:
    """
    Extrai ano a ano, em ordem crescente. Com `cache_dir`, ano fechado e em cache entra sem baixar nada; os demais são
    baixados (com pausa entre downloads) e, se o ano já está fechado, vão para o cache. Devolve (anos baixados, anos
    com falha, anos vindos do cache, anos ainda sem arquivo). Uma falha em qualquer ano aborta a gravação do arquivo final.
    """
    baixados, falhas, do_cache, sem_arquivo = 0, [], [], []
    baixou = False
    for ano in sorted(anos):
        if cache_dir is not None and _definitivo(ano, hoje):
            guardado = _ler_cache(cache_dir, casa, ano, hoje)
            if guardado is not None:
                acc.mesclar(guardado)
                do_cache.append(ano)
                continue
        if baixou:
            time.sleep(PAUSA_POR_CASA[casa])
        baixou = True
        parcial, ainda_sem_arquivo = _baixar_ano(http, ano, casa, extrator, hoje)
        if ainda_sem_arquivo:
            sem_arquivo.append(ano)
            continue
        if parcial is None:
            falhas.append(ano)
            continue
        baixados += 1
        if cache_dir is not None and _definitivo(ano, hoje):
            _gravar_cache(cache_dir, casa, ano, parcial, hoje)
        acc.mesclar(parcial)
    return baixados, falhas, do_cache, sem_arquivo


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
    Sincroniza CEAP e emendas. Com `cache_dir`, a CEAP de cada ano já fechado é guardada e não é baixada de novo até o
    cache vencer: a atualização diária só refaz o ano corrente (e o anterior até março). Cada fonte é independente: a
    falha de uma não impede a gravação da outra, e o resumo diz o que foi gravado (`ceap_gravado`, `emendas_gravado`).
    """
    hoje = hoje or hoje_no_brasil()
    ano_fim = ano_fim or hoje.year
    if ano_inicio > ano_fim:
        raise ValueError("ano_inicio não pode ser maior que ano_fim")
    http = http or HttpClient(timeout=60.0, max_retries=3)
    anos = list(range(ano_inicio, ano_fim + 1))
    resumo: Dict[str, Any] = {"anos": f"{ano_inicio}-{ano_fim}"}

    if ceap:
        acc = CeapAccumulator()
        por_casa = {}
        for casa, extrator in (("camara", extract_camara_ceap), ("senado", extract_senado_ceaps)):
            por_casa[casa] = _extrair_anos(http, anos, casa, extrator, acc, cache_dir, hoje)
        falhas = {casa: r[1] for casa, r in por_casa.items()}
        resumo.update(
            {
                "ceap_anos_baixados": {casa: r[0] for casa, r in por_casa.items()},
                "ceap_falhas": falhas,
            }
        )
        if cache_dir is not None:
            resumo["ceap_anos_do_cache"] = {casa: r[2] for casa, r in por_casa.items()}
        sem_arquivo = {casa: r[3] for casa, r in por_casa.items() if r[3]}
        if sem_arquivo:
            resumo["ceap_anos_sem_arquivo"] = sem_arquivo
        if any(falhas.values()):
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
        if _emendas_truncadas(registros, PROCESSED_DATA_DIR / EMENDAS_OUTPUT):
            resumo["emendas_gravado"] = False
        else:
            resumo["emendas_gravado"] = write_json_if_valid(PROCESSED_DATA_DIR / EMENDAS_OUTPUT, registros, indent=None)

    logger.info("Sincronização concluída: %s", resumo)
    return resumo


def _emendas_truncadas(registros: List[Any], anterior: Path) -> bool:
    """True se a lista nova tem menos de FRACAO_MINIMA_DAS_EMENDAS do arquivo anterior (download cortado no meio)."""
    try:
        antes = json.loads(anterior.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(antes, list) or not antes or not registros:
        return False
    if len(registros) < len(antes) * FRACAO_MINIMA_DAS_EMENDAS:
        logger.error(
            "Emendas: %d registros contra %d no arquivo anterior (menos de %.0f%%); download tratado como truncado, "
            "arquivo anterior preservado.",
            len(registros),
            len(antes),
            FRACAO_MINIMA_DAS_EMENDAS * 100,
        )
        return True
    return False


def fontes_nao_gravadas(resumo: Dict[str, Any]) -> List[str]:
    """As fontes ("ceap", "emendas") que o `run` tentou e não gravou; vazio quando tudo foi gravado ou não foi pedido."""
    return [fonte for fonte in ("ceap", "emendas") if resumo.get(f"{fonte}_gravado") is False]


def main(argv: Optional[List[str]] = None) -> Dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Sincroniza CEAP (Câmara/Senado) e emendas parlamentares.")
    parser.add_argument("--ano-inicio", type=int, default=ANO_INICIAL_CEAP)
    parser.add_argument("--ano-fim", type=int, default=None)
    parser.add_argument("--sem-ceap", action="store_true")
    parser.add_argument("--sem-emendas", action="store_true")
    args = parser.parse_args(argv)
    return run(args.ano_inicio, args.ano_fim, ceap=not args.sem_ceap, emendas=not args.sem_emendas)


if __name__ == "__main__":
    main()
