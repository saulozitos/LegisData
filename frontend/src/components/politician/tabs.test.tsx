import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { fullDossier, sparseDossier } from '@/test/dossier';
import OverviewTab from './OverviewTab';
import IntelligenceTab from './IntelligenceTab';
import PropositionsTab from './PropositionsTab';
import FinancingTab from './FinancingTab';
import CeapTab from './CeapTab';
import AmendmentsTab from './AmendmentsTab';
import JusticeTab from './JusticeTab';
import AttendanceTab from './AttendanceTab';
import RemunerationTab from './RemunerationTab';
import VotesTab from './VotesTab';
import PoliticianHeaderCard from './PoliticianHeaderCard';
import PoliticianTabNav from './PoliticianTabNav';

vi.mock('recharts', async () => (await import('@/test/recharts')).rechartsMock);

const noop = () => {};
const tabs: Array<[string, (d: ReturnType<typeof fullDossier>) => React.ReactElement]> = [
  ['OverviewTab', (d) => <OverviewTab dossier={d} onChangeTab={noop} onSelectParty={noop} />],
  ['IntelligenceTab', (d) => <IntelligenceTab dossier={d} />],
  ['PropositionsTab', (d) => <PropositionsTab dossier={d} />],
  ['FinancingTab', (d) => <FinancingTab dossier={d} />],
  ['CeapTab', (d) => <CeapTab dossier={d} />],
  ['AmendmentsTab', (d) => <AmendmentsTab dossier={d} />],
  ['JusticeTab', (d) => <JusticeTab dossier={d} />],
  ['AttendanceTab', (d) => <AttendanceTab dossier={d} />],
  ['RemunerationTab', (d) => <RemunerationTab dossier={d} />],
  ['VotesTab', (d) => <VotesTab dossier={d} />],
  ['PoliticianHeaderCard', (d) => <PoliticianHeaderCard dossier={d} onBack={noop} onChangeTab={noop} onSelectParty={noop} />],
  ['PoliticianTabNav', (d) => <PoliticianTabNav dossier={d} activeTab="visao_geral" onChange={noop} />],
];

describe.each(tabs)('%s com dossiê completo', (_name, make) => {
  it('renderiza sem lançar e sem imprimir null/undefined/NaN', () => {
    const { container } = render(make(fullDossier()));
    expect(container.textContent?.length).toBeGreaterThan(20);
    expect(container.textContent).not.toMatch(/\bnull\b|undefined|NaN/);
  });
});

describe.each(tabs)('%s com dossiê esparso (contrato real do backend)', (_name, make) => {
  it('não quebra e nunca imprime null/undefined/NaN', () => {
    const { container } = render(make(sparseDossier()));
    expect(container.textContent).not.toMatch(/\bnull\b|undefined|NaN/);
  });
});
