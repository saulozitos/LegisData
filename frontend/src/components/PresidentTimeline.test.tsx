import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import PresidentTimeline from './PresidentTimeline';

describe('PresidentTimeline', () => {
  it('renders without crashing', () => {
    render(<PresidentTimeline mandates={[]} presidents={[]} activeMandateId="" onSelectMandate={() => {}} />);
  });
});
