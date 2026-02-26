import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';

// Auth
import { AuthProvider } from './contexts/AuthContext';
import { WebSocketProvider } from './contexts/WebSocketContext';
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

// Analytics pages
import { AnalyticsDashboard } from './pages/analytics/dashboard';
import { ContactsAnalytics } from './pages/analytics/contacts';
import { ContactDetail } from './pages/analytics/contact-detail';
import { CompaniesAnalytics } from './pages/analytics/companies';
import { CompanyDetail } from './pages/analytics/company-detail';
import { ThreadAnalytics } from './pages/analytics/threads';
import { ResponseTimesAnalytics } from './pages/analytics/response-times';
import { CommunicationPatterns } from './pages/analytics/patterns';
import { ExtractionManagement } from './pages/extraction';

// Theme and styles
import { antTheme } from './theme/glassTheme';
import './styles/glass.css';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <ConfigProvider theme={antTheme}>
        <AuthProvider>
          <WebSocketProvider>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />

            {/* Protected routes - require authentication */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Dashboard />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/mailboxes"
              element={
                <ProtectedRoute>
                  <Layout>
                    <MailboxList />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/mailboxes/create"
              element={
                <ProtectedRoute>
                  <Layout>
                    <MailboxCreate />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/mailboxes/edit/:id"
              element={
                <ProtectedRoute>
                  <Layout>
                    <MailboxEdit />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/mailboxes/process/:id"
              element={
                <ProtectedRoute>
                  <Layout>
                    <MailboxProcess />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/emails"
              element={
                <ProtectedRoute>
                  <Layout>
                    <EmailList />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/emails/:mailboxId"
              element={
                <ProtectedRoute>
                  <Layout>
                    <EmailList />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/emails/:mailboxId/:emailId"
              element={
                <ProtectedRoute>
                  <Layout>
                    <EmailList />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/processing"
              element={
                <ProtectedRoute>
                  <Layout>
                    <ProcessingJobs />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/processing/:mailboxId"
              element={
                <ProtectedRoute>
                  <Layout>
                    <ProcessingJobs />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/errors"
              element={
                <ProtectedRoute>
                  <Layout>
                    <ErrorsPage />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/errors/:mailboxId"
              element={
                <ProtectedRoute>
                  <Layout>
                    <ErrorsPage />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/clients"
              element={
                <ProtectedRoute>
                  <Layout>
                    <ClientsPage />
                  </Layout>
                </ProtectedRoute>
              }
            />

            {/* Analytics routes */}
            <Route path="/analytics" element={<ProtectedRoute><Layout><AnalyticsDashboard /></Layout></ProtectedRoute>} />
            <Route path="/analytics/contacts" element={<ProtectedRoute><Layout><ContactsAnalytics /></Layout></ProtectedRoute>} />
            <Route path="/analytics/contacts/:contactId" element={<ProtectedRoute><Layout><ContactDetail /></Layout></ProtectedRoute>} />
            <Route path="/analytics/companies" element={<ProtectedRoute><Layout><CompaniesAnalytics /></Layout></ProtectedRoute>} />
            <Route path="/analytics/companies/:companyId" element={<ProtectedRoute><Layout><CompanyDetail /></Layout></ProtectedRoute>} />
            <Route path="/analytics/threads" element={<ProtectedRoute><Layout><ThreadAnalytics /></Layout></ProtectedRoute>} />
            <Route path="/analytics/response-times" element={<ProtectedRoute><Layout><ResponseTimesAnalytics /></Layout></ProtectedRoute>} />
            <Route path="/analytics/patterns" element={<ProtectedRoute><Layout><CommunicationPatterns /></Layout></ProtectedRoute>} />
            <Route path="/extraction" element={<ProtectedRoute><Layout><ExtractionManagement /></Layout></ProtectedRoute>} />

            {/* Admin-only routes */}
            <Route
              path="/users"
              element={
                <AdminRoute>
                  <Layout>
                    <UsersPage />
                  </Layout>
                </AdminRoute>
              }
            />
            <Route path="/admin/data" element={<AdminRoute><Layout><AdminDataViewPage /></Layout></AdminRoute>} />

            {/* OAuth callback routes - for popup windows */}
            <Route path="/auth/microsoft/callback" element={<OAuthCallback />} />
            <Route path="/auth/google/callback" element={<OAuthCallback />} />

            {/* Catch-all - redirect to dashboard */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </WebSocketProvider>
        </AuthProvider>
      </ConfigProvider>
    </BrowserRouter>
  );
}

export default App;
