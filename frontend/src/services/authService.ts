// ============================================================
// Auth Service — web login (docs/demo.md, decision 25)
// 1. Document + password → a 6-digit code "sent" to the phone
//    (a demo SMS: the backend returns its text).
// 2. The code → logged in, with a chat session already verified.
// Mock mode (VITE_MOCK=1): the fictional Miguel, code 123456.
// ============================================================

import type { Customer, Language } from '../types';
import { mockCustomer } from '../data/mockData';
import * as api from '../api/client';

const USE_MOCK = import.meta.env.VITE_MOCK === '1';
const MOCK_CODE = '123456';

export type LoginError =
  | 'INVALID_CREDENTIALS'
  | 'WRONG_CODE'
  | 'LOGIN_EXPIRED'
  | 'RATE_LIMITED'
  | 'AUTH_ERROR';

export interface LoginForm {
  country: string;
  documentType: string;
  documentNumber: string;
  password: string;
}

export interface PendingLogin {
  loginId: string;
  phoneLast4: string;
  demoSms: string;
}

function loginError(err: unknown): Error {
  let code: LoginError = 'AUTH_ERROR';
  if (err instanceof api.ApiError) {
    if (err.status === 429) code = 'RATE_LIMITED';
    else if (err.code === 'invalid_credentials') code = 'INVALID_CREDENTIALS';
    else if (err.code === 'wrong_code') code = 'WRONG_CODE';
    else if (err.code === 'login_expired') code = 'LOGIN_EXPIRED';
  }
  return new Error(code);
}

/** Step 1. Throws an Error whose message is a LoginError. */
export async function startLogin(form: LoginForm, lang: Language): Promise<PendingLogin> {
  if (!form.documentNumber.trim() || !form.password) throw new Error('INVALID_CREDENTIALS');
  if (USE_MOCK) {
    return { loginId: 'mock-login', phoneLast4: '0192', demoSms: `SMS (demo): tu código NovaBank es ${MOCK_CODE}` };
  }
  try {
    const started = await api.login({
      country: form.country,
      document_type: form.documentType,
      document_number: form.documentNumber.trim(),
      password: form.password,
      lang,
    });
    return { loginId: started.login_id, phoneLast4: started.phone_last4, demoSms: started.demo_sms };
  } catch (err) {
    throw loginError(err);
  }
}

/** Step 2. Throws an Error whose message is a LoginError. */
export async function verifyCode(loginId: string, code: string): Promise<Customer> {
  if (USE_MOCK) {
    if (code !== MOCK_CODE) throw new Error('WRONG_CODE');
    return mockCustomer;
  }
  try {
    const { session_id, customer } = await api.verifyLogin(loginId, code);
    return {
      id: customer.customer_id,
      name: customer.first_name,
      email: '',
      phone: '',
      language: 'es',
      memberSince: '',
      status: 'active',
      segment: 'standard',
      country: customer.country,
      documentType: customer.document_type,
      documentLast4: customer.document_last4,
      sessionId: session_id,
    };
  } catch (err) {
    throw loginError(err);
  }
}
