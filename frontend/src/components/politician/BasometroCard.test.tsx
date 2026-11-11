import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { fullDossier, sparseDossier } from '@/test/dossier';
import type { BasometroData, PoliticoDossier } from '@/services/api';
import BasometroCard from './BasometroCard';

function semIndice(extra: Partial<BasometroData>, resumo = true): PoliticoDossier {
  const d = sparseDossier();
  d.basometro = {
    taxa_governismo_pct: null,
    total_votacoes_analisadas: 4,
    votos_alinhados: 3,
    votos_divergentes: 1,
    classificacao: null,
    ...extra,
  };
  if (resumo) {
    d.resumo_votos = {
      sim: { total: 20, itens: [] },
      nao: { total: 7, itens: [] },
      ausente: { total: 3, itens: [] },
    };
  }
  return d;
}

describe('BasometroCard', () => {
  it('com índice mostra a taxa e a barra', () => {
    render(<BasometroCard dossier={fullDossier()} onChangeTab={vi.fn()} />);
    expect(screen.getByText('72%')).toBeInTheDocument();
    expect(screen.queryByTestId('basometro-sem-indice')).toBeNull();
  });

  it('sem índice explica o motivo e mostra o que se sabe dos votos', () => {
    const onChangeTab = vi.fn();
    render(
      <BasometroCard
        dossier={semIndice({
          motivo_indisponivel: 'AMOSTRA_INSUFICIENTE',
          explicacao_indisponivel: 'Só 4 voto(s) comparável(is) com a orientação do Governo; o índice exige 10.',
          votos_registrados: 30,
          primeiro_voto: '2023-02-01',
          ultimo_voto: '2024-06-10',
          base_desde: '2019-02-01',
        })}
        onChangeTab={onChangeTab}
      />,
    );
    expect(screen.getByText('Índice não calculado')).toBeInTheDocument();
    expect(screen.getByText(/Só 4 voto/)).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
    expect(screen.getByText(/de 01\/02\/2023 a 10\/06\/2024/)).toBeInTheDocument();
    expect(screen.getByText(/desde 01\/02\/2019/)).toBeInTheDocument();
    fireEvent.click(screen.getByText('Ver cada votação'));
    expect(onChangeTab).toHaveBeenCalledWith('votacoes');
  });

  it('sem votos registrados explica o motivo e não mostra contagens zeradas', () => {
    render(
      <BasometroCard
        dossier={semIndice(
          {
            motivo_indisponivel: 'MANDATO_ANTERIOR_A_BASE',
            explicacao_indisponivel: 'O último mandato terminou em 2010; as votações nominais carregadas começam em 2019.',
            votos_registrados: 0,
            base_desde: '2019-02-01',
          },
          false,
        )}
        onChangeTab={vi.fn()}
      />,
    );
    expect(screen.getByText(/terminou em 2010/)).toBeInTheDocument();
    expect(screen.queryByText('Votos registrados')).toBeNull();
    expect(screen.queryByText('Ver cada votação')).toBeNull();
  });

  it('sem dados do backend usa a frase padrão', () => {
    const d = sparseDossier();
    d.basometro = undefined;
    render(<BasometroCard dossier={d} onChangeTab={vi.fn()} />);
    expect(screen.getByText(/Não há votos nominais suficientes/)).toBeInTheDocument();
  });
});
