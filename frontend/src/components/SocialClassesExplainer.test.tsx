import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import SocialClassesExplainer from './SocialClassesExplainer';

describe('SocialClassesExplainer', () => {
  it('renders without crashing', () => {
    render(<SocialClassesExplainer />);
  });
});
