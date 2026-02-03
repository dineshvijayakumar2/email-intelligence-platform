/**
 * Protected Route Component
 *
 * Wraps routes that require authentication.
 * Redirects to login page if user is not authenticated.
 * Can optionally require specific roles.
 */

import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuth } from '../contexts/AuthContext';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRoles?: Array<'admin' | 'client_manager' | 'account_manager'>;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, requiredRoles }) => {
  const { isAuthenticated, profile, loading } = useAuth();
  const location = useLocation();

  // Show loading spinner while checking authentication
  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          background: 'linear-gradient(135deg, #f5f7fa 0%, #e4e8f0 100%)',
          gap: '16px',
        }}
      >
        <Spin size="large" />
        <div style={{ color: '#667eea', fontSize: '16px' }}>Loading...</div>
      </div>
    );
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Check role requirements if specified
  if (requiredRoles && requiredRoles.length > 0 && profile) {
    // Check if user has any of the required roles
    const hasRequiredRole = profile.roles?.some(role => requiredRoles.includes(role));
    if (!hasRequiredRole) {
      // Redirect to home with insufficient permissions
      return <Navigate to="/" state={{ error: 'Insufficient permissions' }} replace />;
    }
  }

  return <>{children}</>;
};

/**
 * Admin-only route component
 */
export const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ProtectedRoute requiredRoles={['admin']}>{children}</ProtectedRoute>
);

/**
 * Route for admins and client managers
 */
export const ManagerRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ProtectedRoute requiredRoles={['admin', 'client_manager']}>{children}</ProtectedRoute>
);

export default ProtectedRoute;
