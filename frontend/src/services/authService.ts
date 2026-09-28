// ============================================================
// Auth Service — mock only
// Replace with real auth (Cognito / OAuth) when ready.
// ============================================================

import type { Customer } from '../types';
import { mockCustomer } from '../data/mockData';

interface LoginRequest {
  email: string;
  password: string;
}

interface LoginResponse {
  customer: Customer;
  token: string; // mock JWT — not cryptographically real
}

const DEMO_CREDENTIALS = {
  email: 'miguel@demo.novabank.lat',
  password: 'demo1234',
};

export async function login(request: LoginRequest): Promise<LoginResponse> {
  await new Promise((r) => setTimeout(r, 900));

  // Accept demo credentials or any non-empty input for UX purposes
  if (!request.email || !request.password) {
    throw new Error('MISSING_CREDENTIALS');
  }

  if (
    request.email !== DEMO_CREDENTIALS.email &&
    !request.email.includes('@')
  ) {
    throw new Error('INVALID_EMAIL');
  }

  // In demo mode, any valid-looking credentials authenticate successfully
  return {
    customer: mockCustomer,
    token: 'mock-jwt-token-demo-only',
  };
}

export async function logout(): Promise<void> {
  await new Promise((r) => setTimeout(r, 200));
  // In production: invalidate token, clear session
}

export function getDemoCredentials(): typeof DEMO_CREDENTIALS {
  return DEMO_CREDENTIALS;
}
