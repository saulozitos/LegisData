import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ReportarErro from './ReportarErro';

const enviar = vi.fn();
vi.mock('@/services/api', () => ({ enviarRelatoDeErro: (...a: unknown[]) => enviar(...a) }));

function abrir() {
  fireEvent.click(screen.getByRole('button', { name: 'Encontrou uma informação incorreta?' }));
}

describe('ReportarErro', () => {
  beforeEach(() => {
    enviar.mockReset();
  });

  it('envia o relato já ligado ao político e à seção consultados', async () => {
    enviar.mockResolvedValue({ mensagem: 'Recebemos o seu relato.' });
    render(<ReportarErro alvoTipo="POLITICO" alvoId="abc" alvoRotulo="Fulano" secao="Histórico partidário" />);
    abrir();
    fireEvent.change(screen.getByLabelText(/O que está errado/), { target: { value: 'O partido de 2018 está errado.' } });
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: 'a@b.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar relato' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Recebemos o seu relato.'));
    expect(enviar).toHaveBeenCalledWith(
      expect.objectContaining({
        alvo_tipo: 'POLITICO',
        alvo_id: 'abc',
        alvo_rotulo: 'Fulano',
        secao: 'Histórico partidário',
        descricao: 'O partido de 2018 está errado.',
        contato: 'a@b.com',
        website: null,
      }),
    );
  });

  it('só habilita o envio com descrição de pelo menos 10 caracteres', () => {
    render(<ReportarErro alvoTipo="PAINEL" alvoId="votacoes" />);
    abrir();
    const botao = screen.getByRole('button', { name: 'Enviar relato' });
    expect(botao).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/O que está errado/), { target: { value: 'curto' } });
    expect(botao).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/O que está errado/), { target: { value: 'texto bem longo agora' } });
    expect(botao).toBeEnabled();
  });

  it('mostra o motivo quando a API recusa (ex.: CPF no texto) e mantém o que foi digitado', async () => {
    enviar.mockImplementation(async () => {
      throw new Error('O texto parece conter um CPF.');
    });
    render(<ReportarErro alvoTipo="VOTACAO" alvoId="v1" />);
    abrir();
    fireEvent.change(screen.getByLabelText(/O que está errado/), { target: { value: 'meu texto com problema' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar relato' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('parece conter um CPF'));
    expect(screen.getByLabelText(/O que está errado/)).toHaveValue('meu texto com problema');
  });

  it('usa o rótulo pedido no botão e fecha o formulário', () => {
    render(<ReportarErro alvoTipo="CLASSIFICACAO" rotulo="Discorda desta classificação?" />);
    fireEvent.click(screen.getByRole('button', { name: 'Discorda desta classificação?' }));
    fireEvent.click(screen.getByRole('button', { name: 'Fechar' }));
    expect(screen.getByRole('button', { name: 'Discorda desta classificação?' })).toBeInTheDocument();
  });
});
