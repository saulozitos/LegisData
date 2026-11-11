import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import EntradaRapida from './EntradaRapida';

describe('EntradaRapida', () => {
  it('leva cada pergunta à consulta certa', () => {
    const onIr = vi.fn();
    render(<EntradaRapida onIr={onIr} />);
    fireEvent.click(screen.getByRole('button', { name: /Como meu deputado votou/ }));
    expect(onIr).toHaveBeenLastCalledWith({ aba: 'raiox', secao: 'votacoes' });
    fireEvent.click(screen.getByRole('button', { name: /Quem financiou a campanha/ }));
    expect(onIr).toHaveBeenLastCalledWith({ aba: 'raiox', secao: 'financiamento' });
    fireEvent.click(screen.getByRole('button', { name: /Para onde foram as emendas/ }));
    expect(onIr).toHaveBeenLastCalledWith({ aba: 'emendas' });
  });

  it('busca por assunto digitado e pelos atalhos', () => {
    const onIr = vi.fn();
    render(<EntradaRapida onIr={onIr} />);
    fireEvent.change(screen.getByLabelText('Ou busque por assunto'), { target: { value: '  escala 6x1 ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    expect(onIr).toHaveBeenLastCalledWith({ aba: 'produtividade', assunto: 'escala 6x1' });
    fireEvent.click(screen.getByRole('button', { name: 'violência contra a mulher' }));
    expect(onIr).toHaveBeenLastCalledWith({ aba: 'produtividade', assunto: 'violência contra a mulher' });
  });

  it('não busca com o campo vazio', () => {
    const onIr = vi.fn();
    render(<EntradaRapida onIr={onIr} />);
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    expect(onIr).not.toHaveBeenCalled();
  });
});
