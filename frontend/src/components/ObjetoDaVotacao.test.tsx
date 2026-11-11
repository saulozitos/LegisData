import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ObjetoDaVotacao from './ObjetoDaVotacao';

describe('ObjetoDaVotacao', () => {
  it('avisa que a urgência não aprova o projeto', () => {
    render(
      <ObjetoDaVotacao
        objeto={{
          codigo: 'URGENCIA',
          rotulo: 'Requerimento de urgência',
          explicacao: 'Aprovar a urgência não aprova o projeto.',
          decide_merito: false,
        }}
      />,
    );
    expect(screen.getByText('Requerimento de urgência')).toBeInTheDocument();
    expect(screen.getByText('Aprovar a urgência não aprova o projeto.')).toBeInTheDocument();
  });

  it('no texto principal mostra só o rótulo, sem aviso', () => {
    render(
      <ObjetoDaVotacao
        objeto={{ codigo: 'TEXTO_PRINCIPAL', rotulo: 'Texto principal', explicacao: 'Votação do projeto.', decide_merito: true }}
      />,
    );
    expect(screen.getByText('Texto principal')).toBeInTheDocument();
    expect(screen.queryByText('Votação do projeto.')).not.toBeInTheDocument();
  });

  it('sem objeto diz que a fonte não informa, em vez de supor', () => {
    render(<ObjetoDaVotacao objeto={null} />);
    expect(screen.getByText(/a fonte oficial não informa/)).toBeInTheDocument();
  });
});
