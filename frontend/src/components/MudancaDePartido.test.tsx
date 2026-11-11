import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import MudancaDePartido from './MudancaDePartido';

describe('MudancaDePartido', () => {
  it('mostra a etiqueta e a explicação quando só o nome do partido mudou', () => {
    render(<MudancaDePartido tipo="RENOMEACAO" rotulo="Mudança de nome e sigla do mesmo partido" />);
    const etiqueta = screen.getByText('Mudança de nome e sigla do mesmo partido');
    expect(etiqueta).toHaveAttribute('title', expect.stringContaining('Não é troca de partido'));
  });

  it.each(['FUSAO', 'INCORPORACAO'] as const)('mostra %s como mudança que não é troca', (tipo) => {
    render(<MudancaDePartido tipo={tipo} rotulo={tipo} />);
    expect(screen.getByText(tipo)).toHaveAttribute('title', expect.stringContaining('não entra na contagem'));
  });

  it.each(['INICIAL', 'TROCA'] as const)('não mostra nada para %s', (tipo) => {
    const { container } = render(<MudancaDePartido tipo={tipo} rotulo="x" />);
    expect(container).toBeEmptyDOMElement();
  });
});
