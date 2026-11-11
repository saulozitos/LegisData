import { useApi } from '@/hooks/useApi';
import { fetchCobertura } from '@/services/api';

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

function formatarData(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split('-');
  return `${Number(dia)} ${MESES[Number(mes) - 1]} ${ano}`;
}

/**
 * Uma linha com a fonte e a data da última atualização do painel, para o número não aparecer sem origem.
 * Sem cobertura para o painel (ou com a API fora), não mostra nada: nunca inventa fonte nem data.
 */
export default function FonteDoDado({ painel }: { painel: string }) {
  const { data } = useApi('cobertura', (signal) => fetchCobertura(signal));
  const cobertura = data?.find((c) => c.painel === painel);
  if (!cobertura) return null;
  return (
    <p className="text-[10px] text-slate-500" data-testid={`fonte-${painel}`}>
      Fonte: {cobertura.fonte}
      {cobertura.atualizado_em ? ` · atualizado em ${formatarData(cobertura.atualizado_em)}` : ''}
    </p>
  );
}
