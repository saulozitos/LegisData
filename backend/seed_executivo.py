import asyncio
from datetime import date, timedelta
from app.core.database import SessionLocal
from app.models.executivo import PresidentialMandate, MandateIndicator
from sqlalchemy.orm import Session
import random

async def seed_data():
    db: Session = SessionLocal()
    
    # Clean previous data
    db.query(PresidentialMandate).delete()
    db.commit()

    # Create mock mandates
    mandate1 = PresidentialMandate(
        nome="Jair Bolsonaro",
        inicio=date(2019, 1, 1),
        fim=date(2022, 12, 31),
        partido="PL",
        foto_url="https://ui-avatars.com/api/?name=Jair+Bolsonaro&background=0D8ABC&color=fff&size=256"
    )
    
    mandate2 = PresidentialMandate(
        nome="Luiz Inácio Lula da Silva",
        inicio=date(2023, 1, 1),
        fim=None,
        partido="PT",
        foto_url="https://ui-avatars.com/api/?name=Luiz+Inacio+Lula+da+Silva&background=c62828&color=fff&size=256"
    )

    db.add(mandate1)
    db.add(mandate2)
    db.commit()

    # Create mock indicators for mandate1
    current_date = mandate1.inicio
    while current_date <= mandate1.fim:
        db.add(MandateIndicator(mandate_id=mandate1.id, chave_indicador="inflacao_ipca", valor=random.uniform(2.0, 10.0), data_medicao=current_date))
        db.add(MandateIndicator(mandate_id=mandate1.id, chave_indicador="desemprego_pnad", valor=random.uniform(7.0, 14.0), data_medicao=current_date))
        db.add(MandateIndicator(mandate_id=mandate1.id, chave_indicador="aprovacao_popular", valor=random.uniform(20.0, 45.0), data_medicao=current_date))
        db.add(MandateIndicator(mandate_id=mandate1.id, chave_indicador="taxa_sucesso_congresso", valor=random.uniform(30.0, 60.0), data_medicao=current_date))
        db.add(MandateIndicator(mandate_id=mandate1.id, chave_indicador="volume_emendas", valor=random.uniform(100.0, 500.0), data_medicao=current_date))
        
        # Next month
        month = current_date.month % 12 + 1
        year = current_date.year + (current_date.month // 12)
        current_date = date(year, month, 1)

    # Create mock indicators for mandate2
    current_date = mandate2.inicio
    end_date = date.today()
    while current_date <= end_date:
        db.add(MandateIndicator(mandate_id=mandate2.id, chave_indicador="inflacao_ipca", valor=random.uniform(2.0, 6.0), data_medicao=current_date))
        db.add(MandateIndicator(mandate_id=mandate2.id, chave_indicador="desemprego_pnad", valor=random.uniform(7.0, 10.0), data_medicao=current_date))
        db.add(MandateIndicator(mandate_id=mandate2.id, chave_indicador="aprovacao_popular", valor=random.uniform(35.0, 60.0), data_medicao=current_date))
        db.add(MandateIndicator(mandate_id=mandate2.id, chave_indicador="taxa_sucesso_congresso", valor=random.uniform(40.0, 70.0), data_medicao=current_date))
        db.add(MandateIndicator(mandate_id=mandate2.id, chave_indicador="volume_emendas", valor=random.uniform(150.0, 600.0), data_medicao=current_date))
        
        # Next month
        month = current_date.month % 12 + 1
        year = current_date.year + (current_date.month // 12)
        current_date = date(year, month, 1)

    db.commit()
    db.close()
    print("Dados inseridos com sucesso!")

if __name__ == "__main__":
    asyncio.run(seed_data())
