/**
 * Reset Password Page — set new password after clicking reset link.
 */
import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../lib/supabase';
import { toast } from '@/lib/toast';
import { Lock, CheckCircle2, Mail } from 'lucide-react';
import { Spinner } from '@/lib/icons';

export const ResetPasswordPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isValidSession, setIsValidSession] = useState<boolean | null>(null);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const { resetPassword, signOut } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setIsValidSession(!!session);
    });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password || password.length < 6) { setError('Password must be at least 6 characters'); return; }
    if (password !== confirmPassword) { setError('Passwords do not match'); return; }
    setLoading(true); setError(null);
    try {
      await resetPassword(password);
      setSuccess(true);
      setTimeout(() => navigate('/', { replace: true }), 3000);
    } catch (err: any) {
      setError(err.message || 'Failed to reset password');
    } finally { setLoading(false); }
  };

  const handleCancel = async () => {
    try { await signOut(); toast.success('Signed out'); navigate('/login', { replace: true }); }
    catch { toast.error('Failed to sign out'); }
  };

  // Shared card wrapper
  const Card = ({ children }: { children: React.ReactNode }) => (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 p-4">
      <div className="w-full max-w-md">
        <div className="rounded-xl border bg-white shadow-lg p-8">{children}</div>
        <p className="text-center text-xs text-slate-400 mt-4">Powered by Newbound Intelligence</p>
      </div>
    </div>
  );

  if (isValidSession === null) return <Card><div className="text-center py-8"><Spinner className="h-6 w-6 animate-spin text-primary mx-auto" /><p className="text-sm text-slate-500 mt-3">Loading...</p></div></Card>;

  if (!isValidSession) return (
    <Card>
      <div className="text-center mb-6"><Mail className="h-10 w-10 text-primary mx-auto mb-3" /><h1 className="text-xl font-semibold text-slate-900">Invalid or Expired Link</h1></div>
      <div className="rounded-lg bg-destructive-subtle p-3 mb-6"><p className="text-sm text-destructive">This link is invalid or has expired. Please request a new one from the login page.</p></div>
      <button onClick={() => navigate('/login')} className="w-full h-10 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark transition-colors">Back to Login</button>
    </Card>
  );

  if (success) return (
    <Card>
      <div className="text-center py-4">
        <CheckCircle2 className="h-16 w-16 text-success mx-auto mb-4" />
        <h1 className="text-xl font-semibold text-slate-900 mb-2">Password Reset Successful!</h1>
        <p className="text-sm text-slate-500">Your password has been updated. Redirecting to dashboard...</p>
      </div>
    </Card>
  );

  return (
    <Card>
      <div className="text-center mb-6">
        <Mail className="h-10 w-10 text-primary mx-auto mb-3" />
        <h1 className="text-xl font-semibold text-slate-900">Set New Password</h1>
        <p className="text-sm text-slate-500 mt-1">Enter a new password for your account</p>
      </div>

      {error && (
        <div className="rounded-lg bg-destructive-subtle p-3 mb-4">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="text-sm font-medium text-slate-700 block mb-1">New Password</label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="Enter new password" autoFocus
              className="w-full h-10 pl-10 pr-4 text-sm rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary" />
          </div>
        </div>

        <div>
          <label className="text-sm font-medium text-slate-700 block mb-1">Confirm Password</label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
              placeholder="Confirm new password"
              className="w-full h-10 pl-10 pr-4 text-sm rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary" />
          </div>
        </div>

        <div className="space-y-2 pt-2">
          <button type="submit" disabled={loading}
            className="w-full h-10 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark disabled:opacity-50 transition-colors inline-flex items-center justify-center gap-2">
            {loading && <Spinner className="h-4 w-4 animate-spin" />}
            Reset Password
          </button>
          <button type="button" onClick={handleCancel}
            className="w-full h-10 text-sm font-medium text-slate-600 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors">
            Cancel & Sign Out
          </button>
        </div>
      </form>
    </Card>
  );
};
