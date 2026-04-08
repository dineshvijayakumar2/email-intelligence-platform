import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,        // 30s before refetch (replaces CACHE_TTL_SHORT)
      gcTime: 5 * 60_000,       // 5min garbage collection
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

/** Redirect old parameterized routes (e.g. /errors/:mailboxId → /manage/errors/:mailboxId) */
const RedirectWithParams: React.FC<{ to: string }> = ({ to }) => {
  const { mailboxId } = useParams();
  return <Navigate to={`${to}/${mailboxId}`} replace />;
};

// Auth
import { AuthProvider } from './contexts/AuthContext';
import { WebSocketProvider } from './contexts/WebSocketContext';
import { ClientProvider } from './contexts/ClientContext';
import { ProtectedRoute, AdminRoute } from './components/ProtectedRoute';
import { LoginPage } from './pages/login';
import { ResetPasswordPage } from './pages/reset-password';

// Components
import { Layout } from './components/layout';
import { Dashboard } from './pages/dashboard';
import { MailboxList, MailboxCreate, MailboxEdit } from './pages/mailboxes';
import { MailboxProcess } from './pages/mailbox-process';
import { EmailList } from './pages/emails';
import { ProcessingJobs } from './pages/processing';
import ErrorsPage from './pages/errors';
import ClientsPage from './pages/clients';
import UsersPage from './pages/users';
import AdminDataViewPage from './pages/admin-data';
import OAuthCallback from './pages/oauth-callback';

// Customers pages (formerly analytics/companies, contacts, threads)
import { ContactsAnalytics } from './pages/analytics/contacts';
import { ContactDetail } from './pages/analytics/contact-detail';
import { CompaniesAnalytics } from './pages/analytics/companies';
import { CompanyDetail } from './pages/analytics/company-detail';
import { ThreadAnalytics } from './pages/analytics/threads';

// Insights pages (formerly intelligence/*)
import InboxPage from './pages/intelligence/inbox';
import DigestPage from './pages/intelligence/digest';
import OpportunitiesPage from './pages/intelligence/opportunities';
import StrategicDigestPage from './pages/intelligence/strategic-digest';
import VectorSearchPage from './pages/intelligence/vector-search';
import AgentPage from './pages/intelligence/agent';

// Manage pages
import { ResponseTimesAnalytics } from './pages/analytics/response-times';
import { CommunicationPatterns } from './pages/analytics/patterns';
import { EmailRulesPage } from './pages/analytics/email-rules';
import { DataHealthDashboard } from './pages/analytics/data-health';
import { ExtractionManagement } from './pages/extraction';
import UsagePage from './pages/intelligence/usage';
import PlaygroundPage from './pages/intelligence/playground';
import QuickbaseConfigPage from './pages/intelligence/quickbase-config';
import QuickbaseDataPage from './pages/intelligence/quickbase-data';
import QuickbaseMatchesPage from './pages/intelligence/quickbase-matches';
import IntelligenceConfigPage from './pages/manage/intelligence-config';
import LogMonitorPage from './pages/manage/log-monitor';

// Settings
import SettingsPage from './pages/settings';

// Audit
import AuditLogsPage from './pages/audit-logs';

// Styles
import './App.css';

function App() {
  return (
    <QueryClientProvider client={queryClient}>
    <BrowserRouter>
        <AuthProvider>
          <ClientProvider>
          <WebSocketProvider>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />

            {/* Protected routes - require authentication */}
            <Route path="/" element={<ProtectedRoute><Layout><Dashboard /></Layout></ProtectedRoute>} />

            {/* Mailbox routes */}
            <Route path="/mailboxes" element={<ProtectedRoute><Layout><MailboxList /></Layout></ProtectedRoute>} />
            <Route path="/mailboxes/create" element={<ProtectedRoute><Layout><MailboxCreate /></Layout></ProtectedRoute>} />
            <Route path="/mailboxes/edit/:id" element={<ProtectedRoute><Layout><MailboxEdit /></Layout></ProtectedRoute>} />
            <Route path="/mailboxes/process/:id" element={<ProtectedRoute><Layout><MailboxProcess /></Layout></ProtectedRoute>} />

            {/* Email routes */}
            <Route path="/emails" element={<ProtectedRoute><Layout><EmailList /></Layout></ProtectedRoute>} />
            <Route path="/emails/:mailboxId" element={<ProtectedRoute><Layout><EmailList /></Layout></ProtectedRoute>} />
            <Route path="/emails/:mailboxId/:emailId" element={<ProtectedRoute><Layout><EmailList /></Layout></ProtectedRoute>} />

            {/* Customers routes (formerly /analytics/companies, /analytics/contacts, /analytics/threads) */}
            <Route path="/customers" element={<ProtectedRoute><Layout><CompaniesAnalytics /></Layout></ProtectedRoute>} />
            <Route path="/customers/:companyId" element={<ProtectedRoute><Layout><CompanyDetail /></Layout></ProtectedRoute>} />
            <Route path="/customers/contacts" element={<ProtectedRoute><Layout><ContactsAnalytics /></Layout></ProtectedRoute>} />
            <Route path="/customers/contacts/:contactId" element={<ProtectedRoute><Layout><ContactDetail /></Layout></ProtectedRoute>} />
            <Route path="/customers/threads" element={<ProtectedRoute><Layout><ThreadAnalytics /></Layout></ProtectedRoute>} />

            {/* Insights routes (formerly /intelligence/*) */}
            <Route path="/insights/inbox" element={<ProtectedRoute><Layout><InboxPage /></Layout></ProtectedRoute>} />
            <Route path="/insights/digest" element={<ProtectedRoute><Layout><DigestPage /></Layout></ProtectedRoute>} />
            <Route path="/insights/opportunities" element={<ProtectedRoute><Layout><OpportunitiesPage /></Layout></ProtectedRoute>} />
            <Route path="/insights/strategic" element={<ProtectedRoute><Layout><StrategicDigestPage /></Layout></ProtectedRoute>} />
            <Route path="/insights/search" element={<ProtectedRoute><Layout><VectorSearchPage /></Layout></ProtectedRoute>} />
            <Route path="/insights/agent" element={<ProtectedRoute><Layout><AgentPage /></Layout></ProtectedRoute>} />

            {/* Manage routes */}
            <Route path="/manage/response-times" element={<ProtectedRoute><Layout><ResponseTimesAnalytics /></Layout></ProtectedRoute>} />
            <Route path="/manage/patterns" element={<ProtectedRoute><Layout><CommunicationPatterns /></Layout></ProtectedRoute>} />
            <Route path="/insights/email-rules" element={<ProtectedRoute><Layout><EmailRulesPage /></Layout></ProtectedRoute>} />
            <Route path="/manage/email-rules" element={<Navigate to="/insights/email-rules" replace />} />
            <Route path="/manage/data-health" element={<ProtectedRoute><Layout><DataHealthDashboard /></Layout></ProtectedRoute>} />
            <Route path="/manage/extraction" element={<ProtectedRoute><Layout><ExtractionManagement /></Layout></ProtectedRoute>} />
            <Route path="/manage/processing" element={<ProtectedRoute><Layout><ProcessingJobs /></Layout></ProtectedRoute>} />
            <Route path="/manage/processing/:mailboxId" element={<ProtectedRoute><Layout><ProcessingJobs /></Layout></ProtectedRoute>} />
            <Route path="/manage/errors" element={<ProtectedRoute><Layout><ErrorsPage /></Layout></ProtectedRoute>} />
            <Route path="/manage/errors/:mailboxId" element={<ProtectedRoute><Layout><ErrorsPage /></Layout></ProtectedRoute>} />
            <Route path="/clients" element={<ProtectedRoute><Layout><ClientsPage /></Layout></ProtectedRoute>} />
            <Route path="/settings" element={<ProtectedRoute><Layout><SettingsPage /></Layout></ProtectedRoute>} />

            {/* Admin-only manage routes */}
            <Route path="/manage/ai-usage" element={<AdminRoute><Layout><UsagePage /></Layout></AdminRoute>} />
            <Route path="/manage/ai-playground" element={<AdminRoute><Layout><PlaygroundPage /></Layout></AdminRoute>} />
            <Route path="/manage/quickbase" element={<AdminRoute><Layout><QuickbaseConfigPage /></Layout></AdminRoute>} />
            <Route path="/manage/quickbase-data" element={<AdminRoute><Layout><QuickbaseDataPage /></Layout></AdminRoute>} />
            <Route path="/manage/quickbase-matches" element={<AdminRoute><Layout><QuickbaseMatchesPage /></Layout></AdminRoute>} />
            <Route path="/manage/intelligence-config" element={<AdminRoute><Layout><IntelligenceConfigPage /></Layout></AdminRoute>} />
            <Route path="/manage/logs" element={<AdminRoute><Layout><LogMonitorPage /></Layout></AdminRoute>} />
            <Route path="/users" element={<AdminRoute><Layout><UsersPage /></Layout></AdminRoute>} />
            <Route path="/admin/data" element={<AdminRoute><Layout><AdminDataViewPage /></Layout></AdminRoute>} />
            <Route path="/admin/audit-logs" element={<AdminRoute><Layout><AuditLogsPage /></Layout></AdminRoute>} />

            {/* Legacy redirects — old routes redirect to new paths */}
            <Route path="/analytics" element={<Navigate to="/customers" replace />} />
            <Route path="/analytics/companies" element={<Navigate to="/customers" replace />} />
            <Route path="/analytics/companies/:id" element={<Navigate to="/customers/:id" replace />} />
            <Route path="/analytics/contacts" element={<Navigate to="/customers/contacts" replace />} />
            <Route path="/analytics/contacts/:id" element={<Navigate to="/customers/contacts/:id" replace />} />
            <Route path="/analytics/threads" element={<Navigate to="/customers/threads" replace />} />
            <Route path="/analytics/response-times" element={<Navigate to="/manage/response-times" replace />} />
            <Route path="/analytics/patterns" element={<Navigate to="/manage/patterns" replace />} />
            <Route path="/analytics/data-health" element={<Navigate to="/manage/data-health" replace />} />
            <Route path="/analytics/email-rules" element={<Navigate to="/manage/email-rules" replace />} />
            <Route path="/intelligence/inbox" element={<Navigate to="/insights/inbox" replace />} />
            <Route path="/intelligence/digest" element={<Navigate to="/insights/digest" replace />} />
            <Route path="/intelligence/opportunities" element={<Navigate to="/insights/opportunities" replace />} />
            <Route path="/intelligence/strategic-digest" element={<Navigate to="/insights/strategic" replace />} />
            <Route path="/intelligence/usage" element={<Navigate to="/manage/ai-usage" replace />} />
            <Route path="/intelligence/quickbase" element={<Navigate to="/manage/quickbase" replace />} />
            <Route path="/intelligence/quickbase-data" element={<Navigate to="/manage/quickbase-data" replace />} />
            <Route path="/processing" element={<Navigate to="/manage/processing" replace />} />
            <Route path="/processing/:mailboxId" element={<RedirectWithParams to="/manage/processing" />} />
            <Route path="/errors" element={<Navigate to="/manage/errors" replace />} />
            <Route path="/errors/:mailboxId" element={<RedirectWithParams to="/manage/errors" />} />
            <Route path="/extraction" element={<Navigate to="/manage/extraction" replace />} />

            {/* OAuth callback routes - for popup windows */}
            <Route path="/auth/microsoft/callback" element={<OAuthCallback />} />
            <Route path="/auth/google/callback" element={<OAuthCallback />} />

            {/* Catch-all - redirect to dashboard */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </WebSocketProvider>
          </ClientProvider>
        </AuthProvider>
    </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
