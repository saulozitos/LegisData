import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Compartilhar from './Compartilhar';

const baixarCartao = vi.fn();
vi.mock('@/lib/compartilhar', () => ({ baixarCartao: (...a: unknown[]) => baixarCartao(...a) }));

const cartao = {
  titulo: 'x',
  linhas: [] as Array<[string, string]>,
  fonte: 'f',
  data: 'd',
  periodo: 'p',
  etapa: 'e',
  link: 'l',
};

describe('Compartilhar', () => {
  beforeEach(() => {
    baixarCartao.mockReset();
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it('copia o link direto da consulta', async () => {
    render(<Compartilhar link="https://x/?aba=raiox" />);
    fireEvent.click(screen.getByRole('button', { name: /copiar link/i }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Link copiado.'));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('https://x/?aba=raiox');
  });

  it('mostra o endereço quando o navegador não deixa copiar', async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('negado')) } });
    render(<Compartilhar link="https://x/?a=1" />);
    fireEvent.click(screen.getByRole('button', { name: /copiar link/i }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('https://x/?a=1'));
  });

  it('só oferece o cartão quando há dados dele e baixa a imagem', async () => {
    baixarCartao.mockResolvedValue(true);
    const { rerender } = render(<Compartilhar link="l" />);
    expect(screen.queryByRole('button', { name: /baixar cartão/i })).not.toBeInTheDocument();
    rerender(<Compartilhar link="l" cartao={cartao} nomeDoArquivo="votacao" />);
    fireEvent.click(screen.getByRole('button', { name: /baixar cartão/i }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Cartão baixado.'));
    expect(baixarCartao).toHaveBeenCalledWith(cartao, 'votacao');
  });

  it('avisa quando o navegador não gera a imagem', async () => {
    baixarCartao.mockResolvedValue(false);
    render(<Compartilhar link="l" cartao={cartao} />);
    fireEvent.click(screen.getByRole('button', { name: /baixar cartão/i }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/não consegue gerar a imagem/));
  });
});
