import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import { AgentProvider } from './context/AgentContext';
import { ProtectedRoute } from './components/common/ProtectedRoute';
import { LoginPage } from './pages/Login/LoginPage';
import { DashboardPage } from './pages/Dashboard/DashboardPage';
import { AgentPage } from './pages/Agent/AgentPage';
import { AgentConsolePage } from './pages/AgentConsole/AgentConsolePage';
import { DemoPage } from './pages/Demo/DemoPage';

import './styles/globals.css';

// Loaded on demand: its charts and metrics stay out of the customer app's bundle.
const ModelsPage = lazy(() => import('./pages/Models/ModelsPage'));

/**
 * App — Root router and provider tree.
 *
 * Provider order: AppProvider (auth, language) → AgentProvider (conversation)
 * AgentProvider depends on AppProvider for customer ID and language.
 */
export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <AgentProvider>
          <Routes>
            {/* The entry point: the three parts of the demo, each with a line on what it is */}
            <Route path="/demo" element={<DemoPage />} />
            <Route path="/login" element={<LoginPage />} />
            {/* Human agent console: its own key, not the customer login. /asesor is the original name */}
            <Route path="/console" element={<AgentConsolePage />} />
            <Route path="/asesor" element={<AgentConsolePage />} />
            {/* How the learned components are evaluated: public, no customer data. /modelos: original name */}
            <Route path="/models" element={<Suspense fallback={null}><ModelsPage /></Suspense>} />
            <Route path="/modelos" element={<Suspense fallback={null}><ModelsPage /></Suspense>} />
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <DashboardPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/agent"
              element={
                <ProtectedRoute>
                  <AgentPage />
                </ProtectedRoute>
              }
            />
            {/* The root opens the demo entry point; unknown routes go to the customer app */}
            <Route path="/" element={<Navigate to="/demo" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </AgentProvider>
      </AppProvider>
    </BrowserRouter>
  );
}
