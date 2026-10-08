import { describe, it, expect } from 'vitest';
import { ApiError, isAbortError } from './errors';
import { fmtBRL, fmtNum, fmtPct, fmtSigned, isNum, UNAVAILABLE_LABEL } from './format';
import { isActiveMandate, isActiveStatus, toMandateRange } from './mandate';
import { safeExternalUrl } from './safeUrl';
import { voteLabel, voteTone } from './votes';

describe('errors', () => {
  it('ApiError carrega endpoint e status', () => {
    const err = new ApiError('falhou', '/x', 503);
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe('ApiError');
    expect(err.endpoint).toBe('/x');
    expect(err.status).toBe(503);
  });

  it('ApiError sem status usa null', () => {
    expect(new ApiError('rede', '/y').status).toBeNull();
  });

  it('isAbortError reconhece apenas AbortError', () => {
    const abort = new Error('x');
    abort.name = 'AbortError';
    expect(isAbortError(abort)).toBe(true);
    expect(isAbortError(new Error('x'))).toBe(false);
    expect(isAbortError(null)).toBe(false);
    expect(isAbortError('AbortError')).toBe(false);
  });
});

describe('format', () => {
  it('isNum rejeita NaN, Infinity e não-números', () => {
    expect(isNum(1)).toBe(true);
    expect(isNum(0)).toBe(true);
    expect(isNum(NaN)).toBe(false);
    expect(isNum(Infinity)).toBe(false);
    expect(isNum('1')).toBe(false);
    expect(isNum(null)).toBe(false);
  });

  it('nunca imprime null/undefined/NaN', () => {
    for (const bad of [null, undefined, NaN]) {
      expect(fmtNum(bad)).toBe(UNAVAILABLE_LABEL);
      expect(fmtPct(bad)).toBe(UNAVAILABLE_LABEL);
      expect(fmtBRL(bad)).toBe(UNAVAILABLE_LABEL);
      expect(fmtSigned(bad)).toBe(UNAVAILABLE_LABEL);
    }
  });

  it('formata números em pt-BR e preserva zero legítimo', () => {
    expect(fmtNum(1234.5, 1)).toBe('1.234,5');
    expect(fmtNum(0, 1)).toBe('0,0');
    expect(fmtPct(12.34, 1)).toBe('12,3%');
    expect(fmtBRL(10, 2).replace(/\s/g, ' ')).toContain('10,00');
  });

  it('fmtSigned coloca sinal apenas em positivos', () => {
    expect(fmtSigned(2, ' pp')).toBe('+2,0 pp');
    expect(fmtSigned(-2, ' pp')).toBe('-2,0 pp');
    expect(fmtSigned(0)).toBe('0,0');
  });
});

describe('mandate', () => {
  it('isActiveMandate usa o status quando existe', () => {
    expect(isActiveMandate('EM_EXERCICIO')).toBe(true);
    expect(isActiveMandate('titular_ativo')).toBe(true);
    expect(isActiveMandate('IMPEACHMENT')).toBe(false);
    expect(isActiveMandate('CONCLUIDO', null)).toBe(false);
  });

  it('isActiveMandate cai para a data de fim sem status', () => {
    expect(isActiveMandate(null, null)).toBe(true);
    expect(isActiveMandate(undefined, '2022-12-31')).toBe(false);
  });

  it('isActiveStatus é estrito', () => {
    expect(isActiveStatus('ATIVO')).toBe(true);
    expect(isActiveStatus('IMPEACHMENT')).toBe(false);
    expect(isActiveStatus(null)).toBe(false);
  });

  it('toMandateRange deriva anos e usa o ano corrente em mandatos abertos', () => {
    const base = {
      id_referencia: 'lula-2023',
      nome_eleitoral: 'Luiz Inácio Lula da Silva',
      mandato_numero: 3,
      ano_eleicao: 2022,
      data_inicio: '2023-01-01',
    };
    expect(toMandateRange({ ...base, data_fim: null }, 2026)).toEqual({
      id: 'lula-2023',
      label: 'Silva 3',
      start: 2023,
      end: 2026,
      electionYear: 2022,
    });
    expect(toMandateRange({ ...base, data_fim: '2024-12-31' }, 2026).end).toBe(2024);
  });
});

describe('safeExternalUrl', () => {
  it('aceita apenas http(s)', () => {
    expect(safeExternalUrl('https://camara.leg.br/x')).toBe('https://camara.leg.br/x');
    expect(safeExternalUrl('http://a.com')).toBe('http://a.com/');
  });

  it('bloqueia esquemas perigosos e valores inválidos', () => {
    expect(safeExternalUrl('javascript:alert(1)')).toBeUndefined();
    expect(safeExternalUrl('data:text/html,<script>')).toBeUndefined();
    expect(safeExternalUrl('not a url')).toBeUndefined();
    expect(safeExternalUrl('')).toBeUndefined();
    expect(safeExternalUrl(null)).toBeUndefined();
    expect(safeExternalUrl(undefined)).toBeUndefined();
  });
});

describe('votes', () => {
  it('voteLabel mapeia decisões conhecidas, inclusive sem acento', () => {
    expect(voteLabel('SIM')).toBe('Sim');
    expect(voteLabel('nao')).toBe('Não');
    expect(voteLabel('NÃO')).toBe('Não');
    expect(voteLabel('OBSTRUCAO')).toBe('Obstrução');
    expect(voteLabel('ABSTENCAO')).toBe('Abstenção');
    expect(voteLabel('ARTIGO_17')).toBe('Art. 17');
  });

  it('OBSTRUCAO nunca vira Abstenção nem Ausente', () => {
    expect(voteLabel('OBSTRUCAO')).not.toBe('Abstenção');
    expect(voteLabel('OBSTRUCAO')).not.toBe('Ausente');
  });

  it('voteLabel não força desconhecidos para Ausente', () => {
    expect(voteLabel(null)).toBe('Não informado');
    expect(voteLabel('LICENCA_MEDICA')).toBe('LICENCA MEDICA');
  });

  it('voteTone classifica corretamente', () => {
    expect(voteTone('SIM')).toBe('yes');
    expect(voteTone('Não')).toBe('no');
    expect(voteTone('ABSTENCAO')).toBe('abstain');
    expect(voteTone('OBSTRUCAO')).toBe('obstruction');
    expect(voteTone('AUSENTE')).toBe('absent');
    expect(voteTone('XYZ')).toBe('other');
    expect(voteTone(undefined)).toBe('other');
  });
});
