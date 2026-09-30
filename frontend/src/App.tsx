import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import { AgentProvider } from './context/AgentContext';
import { ProtectedRoute } from './components/common/ProtectedRoute';
import { LoginPage } from './pages/Login/LoginPage';
import { DashboardPage } from './pages/Dashboard/DashboardPage';
import { AgentPage } from './pages/Agent/AgentPage';
import { AgentConsolePage } from './pages/AgentConsole/AgentConsolePage';
import './styles/globals.css';

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
            <Route path="/login" element={<LoginPage />} />
            {/* Human agent console: its own key, not the customer login */}
            <Route path="/asesor" element={<AgentConsolePage />} />
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
            {/* Redirect root and unknown routes */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </AgentProvider>
      </AppProvider>
    </BrowserRouter>
  );
}
