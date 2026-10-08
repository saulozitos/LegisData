import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import PartyMembersModal from './PartyMembersModal';

vi.mock('@/services/api', () => ({
  getPoliticiansByParty: vi.fn().mockResolvedValue([])
}));

describe('PartyMembersModal', () => {
  it('renders without crashing', () => {
    render(<PartyMembersModal isOpen={true} onClose={() => {}} partySigla="PT" />);
  });
});
