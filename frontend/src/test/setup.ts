import { afterEach } from 'vitest';

// Sessions now survive a reload (sessionStorage): every test starts with none.
afterEach(() => sessionStorage.clear());
