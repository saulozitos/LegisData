import type { TipoMudancaPartido } from '@/services/api';

const EXPLICACAO: Partial<Record<TipoMudancaPartido, string>> = {
  RENOMEACAO: 'O partido mudou de nome e sigla (registro no TSE). Não é troca de partido e não entra na contagem.',
  FUSAO: 'Dois partidos se fundiram em um novo. Não é escolha do parlamentar e não entra na contagem de trocas.',
  INCORPORACAO: 'O partido foi incorporado por outro. Não é escolha do parlamentar e não entra na contagem de trocas.',
  SUCESSAO: 'O partido foi sucedido por outro. Não entra na contagem de trocas.',
};

/** Etiqueta da mudança de legenda que NÃO é troca de partido (renomeação, fusão, incorporação). Troca e início não mostram nada. */
export default function MudancaDePartido({ tipo, rotulo }: { tipo: TipoMudancaPartido; rotulo: string }) {
  const explicacao = EXPLICACAO[tipo];
  if (!explicacao) return null;
  return (
    <span
      title={explicacao}
      className="text-[9px] px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-300 border border-sky-500/20 font-medium"
    >
      {rotulo}
    </span>
  );
}
