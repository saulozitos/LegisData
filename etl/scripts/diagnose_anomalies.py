import sys
import os
# Add both root and backend to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend')))

from app.core.database import SessionLocal
from app.models.politician import Politician
from app.models.legislative import Proposition
from sqlalchemy import func

def diagnose_anomalies():
    with SessionLocal() as db:
        # Get count of propositions per politician
        results = db.query(
            Politician.id,
            Politician.electoral_name,
            Politician.civil_name,
            func.count(Proposition.id).label('prop_count')
        ).join(Proposition, Proposition.author_politician_id == Politician.id)\
         .group_by(Politician.id)\
         .order_by(func.count(Proposition.id).desc())\
         .all()

        print(f"Total de políticos com proposições: {len(results)}")
        
        print("\n=== TOP 50 POLÍTICOS COM MAIS PROPOSIÇÕES ===")
        # Analyze top 50 politicians by proposition count
        for i, (pol_id, elec_name, civil_name, prop_count) in enumerate(results[:50]):
            
            # Fetch a sample of their propositions to check author_name
            props = db.query(Proposition.author_name, Proposition.id).filter(Proposition.author_politician_id == pol_id).all()
            
            suspect_count = 0
            suspect_names = set()
            
            elec_lower = (elec_name or "").lower().strip()
            civil_lower = (civil_name or "").lower().strip()
            
            for p_author, p_id in props:
                aut_lower = (p_author or "").lower()
                
                # Check if electoral or civil name is in author_name
                if elec_lower not in aut_lower and civil_lower not in aut_lower:
                    # sometimes the name in the database is "Senador X" or "Deputado X"
                    suspect_count += 1
                    suspect_names.add(p_author)
            
            if suspect_count > 0 or prop_count > 100:
                print(f"\n{i+1}. {elec_name} (ID: {pol_id}) - {prop_count} proposições")
                print(f"   Nome Civil: {civil_name}")
                if suspect_count > 0:
                    print(f"   ALERTA: {suspect_count} proposições suspeitas ({suspect_count/prop_count*100:.1f}%)")
                    print(f"   Exemplos de author_name suspeitos:")
                    for name in list(suspect_names)[:10]:
                        print(f"     - {name}")

if __name__ == "__main__":
    diagnose_anomalies()
