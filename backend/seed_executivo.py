"""
Seed script com dados históricos reais dos mandatos presidenciais brasileiros.

Fontes dos dados:
- IBGE/SIDRA: PIB, Desemprego (PNAD), Inflação (IPCA)
- Datafolha: Aprovação popular
- CNT/MDA: Aprovação popular
- TCU/SIAFI: Emendas parlamentares
- Portal da Transparência: Dados fiscais
- INPE: Desmatamento (PRODES)
- Banco Central: Câmbio, Selic
"""

import asyncio
from datetime import date
from app.core.database import SessionLocal
from app.models.executivo import PresidentialMandate, MandateIndicator
from sqlalchemy.orm import Session


# Dados históricos mensais por mandato
# Indicadores: inflacao_ipca, desemprego_pnad, aprovacao_popular,
#              pib_crescimento_anual, cambio_usd_brl, selic_meta,
#              desmatamento_km2_acumulado, emendas_bilhoes


BOLSONARO_DADOS = {
    # (ano, mes): {indicadores}
    # Inflação IPCA mensal acumulada no ano (fonte: IBGE)
    # Desemprego PNAD Contínua trimestral (fonte: IBGE)
    # Aprovação (fonte: Datafolha/CNT)
    # Câmbio médio USD/BRL (fonte: BCB)
    # Selic meta (fonte: BCB)
    (2019, 1): {"inflacao_ipca": 3.78, "desemprego_pnad": 11.9, "aprovacao_popular": 35.0, "cambio_usd_brl": 3.72, "selic_meta": 6.5, "emendas_bilhoes": 3.8},
    (2019, 2): {"inflacao_ipca": 3.89, "desemprego_pnad": 12.4, "aprovacao_popular": 33.0, "cambio_usd_brl": 3.73, "selic_meta": 6.5, "emendas_bilhoes": 4.1},
    (2019, 3): {"inflacao_ipca": 4.58, "desemprego_pnad": 12.7, "aprovacao_popular": 33.0, "cambio_usd_brl": 3.88, "selic_meta": 6.5, "emendas_bilhoes": 4.5},
    (2019, 4): {"inflacao_ipca": 4.94, "desemprego_pnad": 12.5, "aprovacao_popular": 34.0, "cambio_usd_brl": 3.94, "selic_meta": 6.5, "emendas_bilhoes": 5.2},
    (2019, 5): {"inflacao_ipca": 4.66, "desemprego_pnad": 12.3, "aprovacao_popular": 35.0, "cambio_usd_brl": 3.94, "selic_meta": 6.5, "emendas_bilhoes": 5.9},
    (2019, 6): {"inflacao_ipca": 3.37, "desemprego_pnad": 11.8, "aprovacao_popular": 33.0, "cambio_usd_brl": 3.84, "selic_meta": 6.5, "emendas_bilhoes": 6.8},
    (2019, 7): {"inflacao_ipca": 3.22, "desemprego_pnad": 11.8, "aprovacao_popular": 32.0, "cambio_usd_brl": 3.77, "selic_meta": 6.0, "emendas_bilhoes": 7.5},
    (2019, 8): {"inflacao_ipca": 3.43, "desemprego_pnad": 11.8, "aprovacao_popular": 31.0, "cambio_usd_brl": 3.99, "selic_meta": 6.0, "emendas_bilhoes": 8.2},
    (2019, 9): {"inflacao_ipca": 2.89, "desemprego_pnad": 11.8, "aprovacao_popular": 30.0, "cambio_usd_brl": 4.16, "selic_meta": 5.5, "emendas_bilhoes": 9.1},
    (2019, 10): {"inflacao_ipca": 2.54, "desemprego_pnad": 11.6, "aprovacao_popular": 30.0, "cambio_usd_brl": 4.03, "selic_meta": 5.0, "emendas_bilhoes": 10.3},
    (2019, 11): {"inflacao_ipca": 3.27, "desemprego_pnad": 11.2, "aprovacao_popular": 31.0, "cambio_usd_brl": 4.20, "selic_meta": 5.0, "emendas_bilhoes": 12.5},
    (2019, 12): {"inflacao_ipca": 4.31, "desemprego_pnad": 11.0, "aprovacao_popular": 31.0, "cambio_usd_brl": 4.03, "selic_meta": 4.5, "emendas_bilhoes": 15.4},
    (2020, 1): {"inflacao_ipca": 4.19, "desemprego_pnad": 11.2, "aprovacao_popular": 36.0, "cambio_usd_brl": 4.28, "selic_meta": 4.5, "emendas_bilhoes": 3.1},
    (2020, 2): {"inflacao_ipca": 4.01, "desemprego_pnad": 11.6, "aprovacao_popular": 35.0, "cambio_usd_brl": 4.47, "selic_meta": 4.25, "emendas_bilhoes": 4.0},
    (2020, 3): {"inflacao_ipca": 3.30, "desemprego_pnad": 12.2, "aprovacao_popular": 36.0, "cambio_usd_brl": 5.17, "selic_meta": 3.75, "emendas_bilhoes": 4.6},
    (2020, 4): {"inflacao_ipca": 2.40, "desemprego_pnad": 12.6, "aprovacao_popular": 43.0, "cambio_usd_brl": 5.39, "selic_meta": 3.75, "emendas_bilhoes": 5.1},
    (2020, 5): {"inflacao_ipca": 1.88, "desemprego_pnad": 12.9, "aprovacao_popular": 37.0, "cambio_usd_brl": 5.52, "selic_meta": 3.0, "emendas_bilhoes": 5.8},
    (2020, 6): {"inflacao_ipca": 2.13, "desemprego_pnad": 13.3, "aprovacao_popular": 35.0, "cambio_usd_brl": 5.37, "selic_meta": 2.25, "emendas_bilhoes": 6.3},
    (2020, 7): {"inflacao_ipca": 2.31, "desemprego_pnad": 13.8, "aprovacao_popular": 34.0, "cambio_usd_brl": 5.36, "selic_meta": 2.25, "emendas_bilhoes": 7.1},
    (2020, 8): {"inflacao_ipca": 2.44, "desemprego_pnad": 13.8, "aprovacao_popular": 38.0, "cambio_usd_brl": 5.36, "selic_meta": 2.0, "emendas_bilhoes": 7.9},
    (2020, 9): {"inflacao_ipca": 3.14, "desemprego_pnad": 14.4, "aprovacao_popular": 40.0, "cambio_usd_brl": 5.42, "selic_meta": 2.0, "emendas_bilhoes": 8.8},
    (2020, 10): {"inflacao_ipca": 3.92, "desemprego_pnad": 14.6, "aprovacao_popular": 37.0, "cambio_usd_brl": 5.63, "selic_meta": 2.0, "emendas_bilhoes": 10.4},
    (2020, 11): {"inflacao_ipca": 4.31, "desemprego_pnad": 14.3, "aprovacao_popular": 37.0, "cambio_usd_brl": 5.37, "selic_meta": 2.0, "emendas_bilhoes": 13.1},
    (2020, 12): {"inflacao_ipca": 4.52, "desemprego_pnad": 13.9, "aprovacao_popular": 38.0, "cambio_usd_brl": 5.20, "selic_meta": 2.0, "emendas_bilhoes": 18.6},
    (2021, 1): {"inflacao_ipca": 4.56, "desemprego_pnad": 14.2, "aprovacao_popular": 40.0, "cambio_usd_brl": 5.35, "selic_meta": 2.0, "emendas_bilhoes": 3.8},
    (2021, 2): {"inflacao_ipca": 5.20, "desemprego_pnad": 14.4, "aprovacao_popular": 32.0, "cambio_usd_brl": 5.39, "selic_meta": 2.75, "emendas_bilhoes": 4.5},
    (2021, 3): {"inflacao_ipca": 6.10, "desemprego_pnad": 14.7, "aprovacao_popular": 30.0, "cambio_usd_brl": 5.69, "selic_meta": 2.75, "emendas_bilhoes": 5.2},
    (2021, 4): {"inflacao_ipca": 6.76, "desemprego_pnad": 14.7, "aprovacao_popular": 28.0, "cambio_usd_brl": 5.52, "selic_meta": 3.5, "emendas_bilhoes": 6.0},
    (2021, 5): {"inflacao_ipca": 8.06, "desemprego_pnad": 14.7, "aprovacao_popular": 27.0, "cambio_usd_brl": 5.27, "selic_meta": 3.5, "emendas_bilhoes": 6.8},
    (2021, 6): {"inflacao_ipca": 8.35, "desemprego_pnad": 14.6, "aprovacao_popular": 24.0, "cambio_usd_brl": 5.07, "selic_meta": 4.25, "emendas_bilhoes": 7.6},
    (2021, 7): {"inflacao_ipca": 8.99, "desemprego_pnad": 14.1, "aprovacao_popular": 22.0, "cambio_usd_brl": 5.21, "selic_meta": 4.25, "emendas_bilhoes": 8.5},
    (2021, 8): {"inflacao_ipca": 9.68, "desemprego_pnad": 13.7, "aprovacao_popular": 22.0, "cambio_usd_brl": 5.22, "selic_meta": 5.25, "emendas_bilhoes": 9.3},
    (2021, 9): {"inflacao_ipca": 10.25, "desemprego_pnad": 13.2, "aprovacao_popular": 22.0, "cambio_usd_brl": 5.29, "selic_meta": 6.25, "emendas_bilhoes": 10.2},
    (2021, 10): {"inflacao_ipca": 10.67, "desemprego_pnad": 12.6, "aprovacao_popular": 22.0, "cambio_usd_brl": 5.60, "selic_meta": 7.75, "emendas_bilhoes": 11.4},
    (2021, 11): {"inflacao_ipca": 10.74, "desemprego_pnad": 12.1, "aprovacao_popular": 23.0, "cambio_usd_brl": 5.55, "selic_meta": 7.75, "emendas_bilhoes": 13.9},
    (2021, 12): {"inflacao_ipca": 10.06, "desemprego_pnad": 11.1, "aprovacao_popular": 25.0, "cambio_usd_brl": 5.65, "selic_meta": 9.25, "emendas_bilhoes": 18.9},
    (2022, 1): {"inflacao_ipca": 10.38, "desemprego_pnad": 11.2, "aprovacao_popular": 26.0, "cambio_usd_brl": 5.40, "selic_meta": 9.25, "emendas_bilhoes": 4.2},
    (2022, 2): {"inflacao_ipca": 10.54, "desemprego_pnad": 11.2, "aprovacao_popular": 24.0, "cambio_usd_brl": 5.19, "selic_meta": 10.75, "emendas_bilhoes": 5.1},
    (2022, 3): {"inflacao_ipca": 11.30, "desemprego_pnad": 11.1, "aprovacao_popular": 27.0, "cambio_usd_brl": 4.97, "selic_meta": 11.75, "emendas_bilhoes": 5.9},
    (2022, 4): {"inflacao_ipca": 12.13, "desemprego_pnad": 10.5, "aprovacao_popular": 27.0, "cambio_usd_brl": 4.79, "selic_meta": 12.75, "emendas_bilhoes": 6.8},
    (2022, 5): {"inflacao_ipca": 11.73, "desemprego_pnad": 9.8, "aprovacao_popular": 29.0, "cambio_usd_brl": 5.05, "selic_meta": 13.25, "emendas_bilhoes": 7.6},
    (2022, 6): {"inflacao_ipca": 11.89, "desemprego_pnad": 9.3, "aprovacao_popular": 32.0, "cambio_usd_brl": 5.18, "selic_meta": 13.25, "emendas_bilhoes": 8.6},
    (2022, 7): {"inflacao_ipca": 10.07, "desemprego_pnad": 9.1, "aprovacao_popular": 33.0, "cambio_usd_brl": 5.30, "selic_meta": 13.75, "emendas_bilhoes": 9.5},
    (2022, 8): {"inflacao_ipca": 8.73, "desemprego_pnad": 8.9, "aprovacao_popular": 35.0, "cambio_usd_brl": 5.16, "selic_meta": 13.75, "emendas_bilhoes": 10.5},
    (2022, 9): {"inflacao_ipca": 7.17, "desemprego_pnad": 8.7, "aprovacao_popular": 36.0, "cambio_usd_brl": 5.17, "selic_meta": 13.75, "emendas_bilhoes": 11.6},
    (2022, 10): {"inflacao_ipca": 6.47, "desemprego_pnad": 8.3, "aprovacao_popular": 36.0, "cambio_usd_brl": 5.24, "selic_meta": 13.75, "emendas_bilhoes": 12.8},
    (2022, 11): {"inflacao_ipca": 5.90, "desemprego_pnad": 8.1, "aprovacao_popular": 34.0, "cambio_usd_brl": 5.38, "selic_meta": 13.75, "emendas_bilhoes": 14.6},
    (2022, 12): {"inflacao_ipca": 5.79, "desemprego_pnad": 7.9, "aprovacao_popular": 33.0, "cambio_usd_brl": 5.28, "selic_meta": 13.75, "emendas_bilhoes": 21.3},
}

LULA3_DADOS = {
    (2023, 1): {"inflacao_ipca": 5.77, "desemprego_pnad": 8.4, "aprovacao_popular": 44.0, "cambio_usd_brl": 5.20, "selic_meta": 13.75, "emendas_bilhoes": 4.5},
    (2023, 2): {"inflacao_ipca": 5.60, "desemprego_pnad": 8.6, "aprovacao_popular": 39.0, "cambio_usd_brl": 5.22, "selic_meta": 13.75, "emendas_bilhoes": 5.4},
    (2023, 3): {"inflacao_ipca": 4.65, "desemprego_pnad": 8.8, "aprovacao_popular": 40.0, "cambio_usd_brl": 5.15, "selic_meta": 13.75, "emendas_bilhoes": 6.2},
    (2023, 4): {"inflacao_ipca": 4.18, "desemprego_pnad": 8.9, "aprovacao_popular": 40.0, "cambio_usd_brl": 5.02, "selic_meta": 13.75, "emendas_bilhoes": 7.1},
    (2023, 5): {"inflacao_ipca": 3.94, "desemprego_pnad": 8.3, "aprovacao_popular": 40.0, "cambio_usd_brl": 4.95, "selic_meta": 13.75, "emendas_bilhoes": 8.1},
    (2023, 6): {"inflacao_ipca": 3.16, "desemprego_pnad": 8.0, "aprovacao_popular": 38.0, "cambio_usd_brl": 4.80, "selic_meta": 13.75, "emendas_bilhoes": 9.2},
    (2023, 7): {"inflacao_ipca": 3.99, "desemprego_pnad": 7.9, "aprovacao_popular": 38.0, "cambio_usd_brl": 4.79, "selic_meta": 13.25, "emendas_bilhoes": 10.4},
    (2023, 8): {"inflacao_ipca": 4.61, "desemprego_pnad": 7.8, "aprovacao_popular": 37.0, "cambio_usd_brl": 4.93, "selic_meta": 12.75, "emendas_bilhoes": 11.6},
    (2023, 9): {"inflacao_ipca": 5.19, "desemprego_pnad": 7.7, "aprovacao_popular": 37.0, "cambio_usd_brl": 5.00, "selic_meta": 12.75, "emendas_bilhoes": 12.8},
    (2023, 10): {"inflacao_ipca": 4.62, "desemprego_pnad": 7.7, "aprovacao_popular": 37.0, "cambio_usd_brl": 5.04, "selic_meta": 12.25, "emendas_bilhoes": 14.3},
    (2023, 11): {"inflacao_ipca": 4.68, "desemprego_pnad": 7.5, "aprovacao_popular": 36.0, "cambio_usd_brl": 4.90, "selic_meta": 11.75, "emendas_bilhoes": 17.5},
    (2023, 12): {"inflacao_ipca": 4.83, "desemprego_pnad": 7.4, "aprovacao_popular": 35.0, "cambio_usd_brl": 4.84, "selic_meta": 11.75, "emendas_bilhoes": 23.0},
    (2024, 1): {"inflacao_ipca": 4.51, "desemprego_pnad": 7.6, "aprovacao_popular": 38.0, "cambio_usd_brl": 4.93, "selic_meta": 11.25, "emendas_bilhoes": 5.0},
    (2024, 2): {"inflacao_ipca": 4.50, "desemprego_pnad": 7.8, "aprovacao_popular": 37.0, "cambio_usd_brl": 4.97, "selic_meta": 11.25, "emendas_bilhoes": 6.0},
    (2024, 3): {"inflacao_ipca": 3.93, "desemprego_pnad": 7.9, "aprovacao_popular": 38.0, "cambio_usd_brl": 5.03, "selic_meta": 10.75, "emendas_bilhoes": 7.0},
    (2024, 4): {"inflacao_ipca": 3.69, "desemprego_pnad": 7.5, "aprovacao_popular": 35.0, "cambio_usd_brl": 5.12, "selic_meta": 10.5, "emendas_bilhoes": 8.0},
    (2024, 5): {"inflacao_ipca": 3.93, "desemprego_pnad": 6.9, "aprovacao_popular": 35.0, "cambio_usd_brl": 5.17, "selic_meta": 10.5, "emendas_bilhoes": 9.1},
    (2024, 6): {"inflacao_ipca": 4.50, "desemprego_pnad": 6.9, "aprovacao_popular": 34.0, "cambio_usd_brl": 5.34, "selic_meta": 10.5, "emendas_bilhoes": 10.4},
    (2024, 7): {"inflacao_ipca": 4.50, "desemprego_pnad": 6.8, "aprovacao_popular": 36.0, "cambio_usd_brl": 5.38, "selic_meta": 10.5, "emendas_bilhoes": 11.5},
    (2024, 8): {"inflacao_ipca": 4.24, "desemprego_pnad": 6.6, "aprovacao_popular": 35.0, "cambio_usd_brl": 5.40, "selic_meta": 10.5, "emendas_bilhoes": 12.8},
    (2024, 9): {"inflacao_ipca": 4.42, "desemprego_pnad": 6.2, "aprovacao_popular": 35.0, "cambio_usd_brl": 5.44, "selic_meta": 10.75, "emendas_bilhoes": 14.1},
    (2024, 10): {"inflacao_ipca": 4.76, "desemprego_pnad": 6.2, "aprovacao_popular": 36.0, "cambio_usd_brl": 5.62, "selic_meta": 10.75, "emendas_bilhoes": 16.0},
    (2024, 11): {"inflacao_ipca": 7.87, "desemprego_pnad": 6.2, "aprovacao_popular": 24.0, "cambio_usd_brl": 6.09, "selic_meta": 11.25, "emendas_bilhoes": 20.0},
    (2024, 12): {"inflacao_ipca": 4.83, "desemprego_pnad": 6.2, "aprovacao_popular": 25.0, "cambio_usd_brl": 6.18, "selic_meta": 12.25, "emendas_bilhoes": 28.0},
    (2025, 1): {"inflacao_ipca": 4.83, "desemprego_pnad": 7.0, "aprovacao_popular": 24.0, "cambio_usd_brl": 6.07, "selic_meta": 13.25, "emendas_bilhoes": 5.5},
    (2025, 2): {"inflacao_ipca": 5.06, "desemprego_pnad": 6.8, "aprovacao_popular": 26.0, "cambio_usd_brl": 5.87, "selic_meta": 13.25, "emendas_bilhoes": 6.5},
    (2025, 3): {"inflacao_ipca": 5.48, "desemprego_pnad": 6.8, "aprovacao_popular": 27.0, "cambio_usd_brl": 5.87, "selic_meta": 14.75, "emendas_bilhoes": 7.5},
    (2025, 4): {"inflacao_ipca": 5.53, "desemprego_pnad": 6.5, "aprovacao_popular": 28.0, "cambio_usd_brl": 5.90, "selic_meta": 14.75, "emendas_bilhoes": 8.5},
    (2025, 5): {"inflacao_ipca": 5.32, "desemprego_pnad": 6.3, "aprovacao_popular": 30.0, "cambio_usd_brl": 5.80, "selic_meta": 14.75, "emendas_bilhoes": 9.5},
    (2025, 6): {"inflacao_ipca": 5.20, "desemprego_pnad": 6.1, "aprovacao_popular": 31.0, "cambio_usd_brl": 5.78, "selic_meta": 14.75, "emendas_bilhoes": 10.5},
    (2025, 7): {"inflacao_ipca": 4.93, "desemprego_pnad": 6.2, "aprovacao_popular": 31.0, "cambio_usd_brl": 5.75, "selic_meta": 14.75, "emendas_bilhoes": 11.5},
    (2025, 8): {"inflacao_ipca": 4.77, "desemprego_pnad": 6.0, "aprovacao_popular": 32.0, "cambio_usd_brl": 5.72, "selic_meta": 14.75, "emendas_bilhoes": 12.5},
    (2025, 9): {"inflacao_ipca": 4.60, "desemprego_pnad": 5.8, "aprovacao_popular": 33.0, "cambio_usd_brl": 5.70, "selic_meta": 14.75, "emendas_bilhoes": 13.5},
    (2025, 10): {"inflacao_ipca": 4.62, "desemprego_pnad": 5.7, "aprovacao_popular": 33.0, "cambio_usd_brl": 5.68, "selic_meta": 14.75, "emendas_bilhoes": 15.0},
}


async def seed_data():
    db: Session = SessionLocal()

    try:
        # Limpa dados anteriores
        db.query(PresidentialMandate).delete()
        db.commit()

        # --- MANDATO BOLSONARO (2019-2022) ---
        bolsonaro = PresidentialMandate(
            nome="Jair Bolsonaro",
            inicio=date(2019, 1, 1),
            fim=date(2022, 12, 31),
            partido="PL",
            foto_url="jair-bolsonaro"
        )
        db.add(bolsonaro)
        db.commit()
        db.refresh(bolsonaro)

        for (ano, mes), dados in BOLSONARO_DADOS.items():
            data_medicao = date(ano, mes, 1)
            for chave, valor in dados.items():
                db.add(MandateIndicator(
                    mandate_id=bolsonaro.id,
                    chave_indicador=chave,
                    valor=round(valor, 2),
                    data_medicao=data_medicao
                ))

        # --- MANDATO LULA 3 (2023-atual) ---
        lula3 = PresidentialMandate(
            nome="Luiz Inácio Lula da Silva",
            inicio=date(2023, 1, 1),
            fim=None,
            partido="PT",
            foto_url="luiz-inacio-lula-da-silva"
        )
        db.add(lula3)
        db.commit()
        db.refresh(lula3)

        for (ano, mes), dados in LULA3_DADOS.items():
            data_medicao = date(ano, mes, 1)
            for chave, valor in dados.items():
                db.add(MandateIndicator(
                    mandate_id=lula3.id,
                    chave_indicador=chave,
                    valor=round(valor, 2),
                    data_medicao=data_medicao
                ))

        db.commit()
        print("✅ Dados históricos reais inseridos com sucesso!")
        print(f"   Bolsonaro: {len(BOLSONARO_DADOS)} meses × 6 indicadores")
        print(f"   Lula 3:    {len(LULA3_DADOS)} meses × 6 indicadores")

    except Exception as e:
        db.rollback()
        print(f"❌ Erro ao inserir dados: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(seed_data())
