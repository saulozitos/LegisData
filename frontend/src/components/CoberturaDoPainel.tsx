import { Database } from 'lucide-react';
import ReportarErro from '@/components/ReportarErro';
import { useApi } from '@/hooks/useApi';
import { fetchCobertura, type CoberturaPainel } from '@/services/api';

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

function formatarData(iso: string | null): string {
  if (!iso) return 'n/d';
  const [ano, mes, dia] = iso.slice(0, 10).split('-');
  return `${Number(dia)} ${MESES[Number(mes) - 1]} ${ano}`;
}

const ROTULO = { COMPLETA: 'Base completa', PARCIAL: 'Base parcial', SEM_DADOS: 'Sem dados' } as const;
const COR = {
  COMPLETA: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
  PARCIAL: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
  SEM_DADOS: 'bg-slate-500/10 text-slate-300 border-slate-500/30',
} as const;

/** Fonte, período, última atualização e se a base está completa ou parcial, para a tela não parecer uma conclusão sobre tudo. */
export function CoberturaView({ cobertura }: { cobertura: CoberturaPainel }) {
  return (
    <aside
      aria-label={`Cobertura dos dados: ${cobertura.titulo}`}
      className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-[11px] text-slate-400 space-y-1.5"
    >
      <div className="flex items-center gap-2 flex-wrap">
        <Database className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
        <span className="font-semibold text-slate-300">Cobertura dos dados</span>
        <span className={`px-2 py-0.5 rounded-full border font-bold ${COR[cobertura.situacao]}`}>
          {ROTULO[cobertura.situacao]}
        </span>
      </div>
      <dl className="grid grid-cols-1 sm:grid-cols-3 gap-x-4 gap-y-1">
        <div>
          <dt className="inline font-semibold text-slate-300">Fonte: </dt>
          <dd className="inline">{cobertura.fonte}</dd>
        </div>
        <div>
          <dt className="inline font-semibold text-slate-300">Período na base: </dt>
          <dd className="inline">
            {cobertura.periodo_inicio
              ? `${formatarData(cobertura.periodo_inicio)} a ${formatarData(cobertura.periodo_fim)}`
              : 'n/d'}
          </dd>
        </div>
        <div>
          <dt className="inline font-semibold text-slate-300">Última atualização: </dt>
          <dd className="inline">{formatarData(cobertura.atualizado_em)}</dd>
        </div>
      </dl>
      <p>
        {cobertura.registros.toLocaleString('pt-BR')} {cobertura.unidade} cadastrados. {cobertura.nota}
      </p>
      <ReportarErro alvoTipo="PAINEL" alvoId={cobertura.painel} alvoRotulo={cobertura.titulo} />
    </aside>
  );
}

/** Busca a cobertura e mostra a do painel pedido; se falhar ou o painel não existir, não mostra nada (nunca inventa). */
export default function CoberturaDoPainel({ painel }: { painel: string }) {
  const { data } = useApi('cobertura', (signal) => fetchCobertura(signal));
  const cobertura = data?.find((c) => c.painel === painel);
  if (!cobertura) return null;
  return <CoberturaView cobertura={cobertura} />;
}
