"""Basômetro: alinhamento à orientação do governo calculado só com orientação oficial registrada por votação."""

from datetime import datetime, timezone

from app.models import CasaLegislativaEnum, ParliamentaryVote, VotingSession, VotoOpcaoEnum
from app.services.basometro import MIN_VOTACOES_AMOSTRA, calcular_basometro, classificar_governismo
from app.services.staging_merge import merge_staging
from sqlalchemy import text

BASE = "/api/v1/politicians"
SIM, NAO = VotoOpcaoEnum.SIM, VotoOpcaoEnum.NAO


def _votar(db, seed, politico, orientacao, voto, indice):
    sessao = VotingSession(
        proposition_id=seed.proposition.id,
        legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
        session_datetime=datetime(2023, 6, 1, 12, indice % 60, tzinfo=timezone.utc),
        agenda_title=f"Sessão {indice}",
        is_approved=True,
        external_id=f"baso-{politico.camara_id}-{indice}",
        government_orientation=orientacao,
    )
    db.add(sessao)
    db.flush()
    db.add(ParliamentaryVote(voting_session_id=sessao.id, politician_id=politico.id, vote_choice=voto))


def _pessoa_id(db, politico):
    """Id interno em core.pessoa do político legado (a ponte carrega o legado para o schema novo)."""
    merge_staging(db)
    return db.execute(text("SELECT id FROM core.pessoa WHERE uid = :u"), {"u": politico.id}).scalar()


def _popular_fulano(db, seed):
    """8 alinhados, 3 divergentes (2 opostos + 1 abstenção); AUSENTE, 'Liberado' e sem orientação ficam de fora."""
    i = 0
    for _ in range(4):
        _votar(db, seed, seed.fulano, "SIM", SIM, i)
        _votar(db, seed, seed.fulano, "NAO", NAO, i + 1)
        i += 2
    _votar(db, seed, seed.fulano, "SIM", NAO, i)
    _votar(db, seed, seed.fulano, "NAO", SIM, i + 1)
    _votar(db, seed, seed.fulano, "SIM", VotoOpcaoEnum.ABSTENCAO, i + 2)
    _votar(db, seed, seed.fulano, "SIM", VotoOpcaoEnum.AUSENTE, i + 3)
    _votar(db, seed, seed.fulano, "LIBERADO", SIM, i + 4)
    _votar(db, seed, seed.fulano, "LIBERADO", NAO, i + 5)
    _votar(db, seed, seed.fulano, None, SIM, i + 6)
    db.commit()


def test_basometro_counts_only_votes_with_government_orientation(db, seed):
    _popular_fulano(db, seed)
    baso = calcular_basometro(db, _pessoa_id(db, seed.fulano), "PT", votos_sim=20, votos_nao=5)
    assert (baso["votos_alinhados"], baso["votos_divergentes"]) == (8, 3)
    assert baso["total_votacoes_analisadas"] == 11
    assert baso["taxa_governismo_pct"] == 72.7
    assert baso["classificacao"] == "Base Aliada Moderada"
    assert baso["dados_suficientes"] is True and baso["amostra_minima"] == MIN_VOTACOES_AMOSTRA
    assert (baso["votos_sim"], baso["votos_nao"], baso["partido_sigla"]) == (20, 5, "PT")


def test_basometro_is_unavailable_below_minimum_sample(db, seed):
    for i in range(MIN_VOTACOES_AMOSTRA - 1):
        _votar(db, seed, seed.lula_fonte, "SIM", SIM, i)
    db.commit()
    baso = calcular_basometro(db, _pessoa_id(db, seed.lula_fonte), "PT")
    assert baso["dados_suficientes"] is False
    assert baso["taxa_governismo_pct"] is None and baso["classificacao"] is None
    assert baso["votos_alinhados"] == MIN_VOTACOES_AMOSTRA - 1  # contagem real, sem taxa inventada


def test_basometro_without_any_orientation_has_no_counts(db, seed):
    baso = calcular_basometro(db, _pessoa_id(db, seed.beltrano), "PTB")  # só votos em sessões sem orientação de governo
    assert baso["votos_alinhados"] is None and baso["votos_divergentes"] is None
    assert baso["total_votacoes_analisadas"] == 0 and baso["taxa_governismo_pct"] is None


def test_classificar_governismo_boundaries():
    assert [classificar_governismo(t) for t in (100, 80, 79.9, 60, 40, 20, 19.9, 0)] == [
        "Governista Fiel",
        "Governista Fiel",
        "Base Aliada Moderada",
        "Base Aliada Moderada",
        "Independente / Centro",
        "Oposição Moderada",
        "Oposição Firme",
        "Oposição Firme",
    ]


def test_dossier_exposes_real_basometro(client, db, seed):
    _popular_fulano(db, seed)
    baso = client.get(f"{BASE}/{seed.fulano.id}").json()["basometro"]
    assert baso["taxa_governismo_pct"] == 72.7 and baso["classificacao"] == "Base Aliada Moderada"
    assert (baso["votos_alinhados"], baso["votos_divergentes"]) == (8, 3)
    estab = client.get(f"{BASE}/{seed.fulano.id}").json()["indices_inteligencia"]["estabilidade_partidaria"]
    assert estab["taxa_governismo_pct"] == 72.7
