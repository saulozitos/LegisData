import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import Home from './page';

vi.mock('@/components/Header', () => ({ default: () => <div data-testid="Header" /> }));
vi.mock('@/components/PresidentTimeline', () => ({ default: () => <div data-testid="PresidentTimeline" /> }));
vi.mock('@/components/ExecutivoPanel', () => ({ default: () => <div data-testid="ExecutivoPanel" /> }));
vi.mock('@/components/MacroeconomicChart', () => ({ default: () => <div data-testid="MacroeconomicChart" /> }));
vi.mock('@/components/LegislativePanel', () => ({ default: () => <div data-testid="LegislativePanel" /> }));
vi.mock('@/components/PartyFidelityPanel', () => ({ default: () => <div data-testid="PartyFidelityPanel" /> }));
vi.mock('@/components/WageDisparityPanel', () => ({ default: () => <div data-testid="WageDisparityPanel" /> }));
vi.mock('@/components/CongressCompositionPanel', () => ({ default: () => <div data-testid="CongressCompositionPanel" /> }));
vi.mock('@/components/FederalTransfersPanel', () => ({ default: () => <div data-testid="FederalTransfersPanel" /> }));
vi.mock('@/components/PoliticianProfile', () => ({ default: () => <div data-testid="PoliticianProfile" /> }));
vi.mock('@/components/SocialClassesExplainer', () => ({ default: () => <div data-testid="SocialClassesExplainer" /> }));
vi.mock('@/components/DeepBrazilPanel', () => ({ default: () => <div data-testid="DeepBrazilPanel" /> }));
vi.mock('@/components/PropositionsExplorerPanel', () => ({ default: () => <div data-testid="PropositionsExplorerPanel" /> }));
vi.mock('@/components/PartiesPanel', () => ({ default: () => <div data-testid="PartiesPanel" /> }));
vi.mock('@/components/PartyMembersModal', () => ({ default: () => <div data-testid="PartyMembersModal" /> }));
vi.mock('@/components/VotingCalendarPanel', () => ({ default: () => <div data-testid="VotingCalendarPanel" /> }));
vi.mock('@/components/LoadingSkeleton', () => ({ default: () => <div data-testid="LoadingSkeleton" /> }));
vi.mock('@/services/api', () => ({
  getMandatesPerformance: vi.fn().mockResolvedValue([{ id_mandato: '123' }]),
}));

describe('Home page', () => {
  it('renders without crashing', async () => {
    render(<Home />);
    expect(await screen.findByTestId('Header')).toBeInTheDocument();
  });
});
