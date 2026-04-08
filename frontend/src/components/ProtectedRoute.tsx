/**
 * Protected Route Component — zero antd
 */

import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Spinner } from '@/lib/icons';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRoles?: Array<'admin' | 'client_manager' | 'account_manager'>;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, requiredRoles }) => {
  const { isAuthenticated, profile, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-gradient-to-br from-slate-50 to-slate-100 gap-4">
        <Spinner className="h-8 w-8 text-primary animate-spin" />
        <span className="text-primary text-sm font-medium">Loading...</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (requiredRoles && requiredRoles.length > 0 && profile) {
    const hasRequiredRole = profile.roles?.some(role => requiredRoles.includes(role));
    if (!hasRequiredRole) {
      return <Navigate to="/" state={{ error: 'Insufficient permissions' }} replace />;
    }
  }

  return <>{children}</>;
};

export const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ProtectedRoute requiredRoles={['admin']}>{children}</ProtectedRoute>
);

export const ManagerRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ProtectedRoute requiredRoles={['admin', 'client_manager']}>{children}</ProtectedRoute>
);

export default ProtectedRoute;
