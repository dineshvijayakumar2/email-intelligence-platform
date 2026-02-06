import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';

// Auth
import { AuthProvider } from './contexts/AuthContext';
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

// Theme and styles
import { antTheme } from './theme/glassTheme';
import './styles/glass.css';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <ConfigProvider theme={antTheme}>
        <AuthProvider>
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
              path="/clients"
              element={
                <ProtectedRoute>
                  <Layout>
                    <ClientsPage />
                  </Layout>
                </ProtectedRoute>
              }
            />

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

            {/* Catch-all - redirect to dashboard */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </ConfigProvider>
    </BrowserRouter>
  );
}

export default App;
