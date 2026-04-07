/**
 * Login Page — Invite-only. No sign-up tab. Zero antd.
 */
import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, useLocation } from 'react-router-dom';
import { isSupabaseConfigured } from '../lib/supabase';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import { Mail, Lock, User, Globe } from 'lucide-react';
import { Spinner } from '@/lib/icons';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';

// Microsoft icon (Lucide doesn't have one)
const MicrosoftIcon = () => (
  <svg className="h-4 w-4" viewBox="0 0 21 21" fill="none"><rect x="1" y="1" width="9" height="9" fill="#f25022"/><rect x="11" y="1" width="9" height="9" fill="#7fba00"/><rect x="1" y="11" width="9" height="9" fill="#00a4ef"/><rect x="11" y="11" width="9" height="9" fill="#ffb900"/></svg>
);

export const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [forgotOpen, setForgotOpen] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [resetSent, setResetSent] = useState(false);

  const { signInWithEmail, signInWithGoogle, signInWithMicrosoft, resetPasswordRequest, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const isConfigured = isSupabaseConfigured();

  useEffect(() => {
    if (isAuthenticated) {
      const from = (location.state as any)?.from?.pathname || '/';
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, navigate, location]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) { setError('Please enter email and password'); return; }
    setLoading(true); setError(null);
    try {
      await signInWithEmail(email, password);
      navigate((location.state as any)?.from?.pathname || '/', { replace: true });
    } catch (err: any) {
      setError(err.message || 'Login failed. Please check your credentials.');
    } finally { setLoading(false); }
  };

  const handleGoogle = async () => {
    setError(null);
    try { await signInWithGoogle(); } catch (err: any) { setError(err.message || 'Google login failed'); }
  };

  const handleMicrosoft = async () => {
    setError(null);
    try { await signInWithMicrosoft(); } catch (err: any) { setError(err.message || 'Microsoft login failed'); }
  };

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetEmail) return;
    setLoading(true);
    try {
      await resetPasswordRequest(resetEmail);
      setResetSent(true);
      toast.success('Reset email sent! Check your inbox.');
    } catch (err: any) { toast.error(err.message || 'Failed to send reset email'); }
    finally { setLoading(false); }
  };

  if (!isConfigured) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 p-4">
        <div className="w-full max-w-md rounded-xl border bg-white shadow-lg p-8 text-center">
          <Mail className="h-12 w-12 text-primary mx-auto mb-4" />
          <h1 className="text-xl font-bold text-slate-900 mb-2">Configuration Required</h1>
          <p className="text-sm text-slate-500 mb-4">Supabase authentication is not configured.</p>
          <div className="rounded-lg bg-warning-subtle p-3 text-sm text-left">
            <p className="font-mono text-xs text-slate-600">VITE_SUPABASE_URL</p>
            <p className="font-mono text-xs text-slate-600">VITE_SUPABASE_ANON_KEY</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-white to-slate-100 p-4">
      <div className="w-full max-w-sm">
        {/* Card */}
        <div className="rounded-xl border bg-white shadow-lg overflow-hidden">
          {/* Brand header */}
          <div className="bg-gradient-to-r from-primary to-accent px-6 py-8 text-center">
            <div className="w-12 h-12 rounded-xl bg-white/20 flex items-center justify-center mx-auto mb-3">
              <Mail className="h-6 w-6 text-white" />
            </div>
            <h1 className="text-lg font-bold text-white">Email Intelligence</h1>
            <p className="text-sm text-white/70 mt-1">Sign in to your account</p>
          </div>

          <div className="p-6">
            {/* Error */}
            {error && (
              <div className="rounded-lg bg-destructive-subtle p-3 mb-4">
                <p className="text-sm text-destructive">{error}</p>
              </div>
            )}

            {/* OAuth buttons */}
            <div className="space-y-2.5 mb-5">
              <button onClick={handleGoogle}
                className="w-full h-10 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-sm font-medium text-slate-700 inline-flex items-center justify-center gap-2.5 transition-colors">
                <Globe className="h-4 w-4" />
                Continue with Google
              </button>
              <button onClick={handleMicrosoft}
                className="w-full h-10 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-sm font-medium text-slate-700 inline-flex items-center justify-center gap-2.5 transition-colors">
                <MicrosoftIcon />
                Continue with Microsoft
              </button>
            </div>

            {/* Divider */}
            <div className="flex items-center gap-3 mb-5">
              <div className="flex-1 h-px bg-slate-200" />
              <span className="text-xs text-slate-400">or sign in with email</span>
              <div className="flex-1 h-px bg-slate-200" />
            </div>

            {/* Email form */}
            <form onSubmit={handleLogin} className="space-y-3">
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="Email address" autoFocus required
                  className="w-full h-10 pl-10 pr-4 text-sm rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary" />
              </div>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="Password" required
                  className="w-full h-10 pl-10 pr-4 text-sm rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary" />
              </div>
              <div className="text-right">
                <button type="button" onClick={() => { setForgotOpen(true); setResetSent(false); setResetEmail(''); }}
                  className="text-xs text-primary hover:underline">Forgot Password?</button>
              </div>
              <button type="submit" disabled={loading}
                className="w-full h-10 rounded-lg bg-primary hover:bg-primary-dark text-white text-sm font-medium transition-colors disabled:opacity-50 inline-flex items-center justify-center gap-2">
                {loading && <Spinner className="h-4 w-4 animate-spin" />}
                Sign In
              </button>
            </form>

            {/* Invite-only notice */}
            <p className="text-xs text-slate-400 text-center mt-4">
              This platform is invite-only. Contact your administrator for access.
            </p>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-slate-400 mt-4">Powered by Newbound Intelligence</p>
      </div>

      {/* Forgot Password Dialog */}
      <Dialog open={forgotOpen} onOpenChange={setForgotOpen}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader><DialogTitle>{resetSent ? 'Check Your Email' : 'Reset Password'}</DialogTitle></DialogHeader>
          {resetSent ? (
            <div className="text-center py-4">
              <Mail className="h-12 w-12 text-success mx-auto mb-3" />
              <p className="text-sm text-slate-600">We've sent reset instructions to your email. Check your inbox.</p>
              <button onClick={() => setForgotOpen(false)} className="mt-4 h-9 px-4 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark w-full">Back to Login</button>
            </div>
          ) : (
            <form onSubmit={handleForgotPassword} className="space-y-4">
              <p className="text-sm text-slate-500">Enter your email and we'll send reset instructions.</p>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input type="email" value={resetEmail} onChange={e => setResetEmail(e.target.value)}
                  placeholder="Email address" autoFocus required
                  className="w-full h-10 pl-10 pr-4 text-sm rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20" />
              </div>
              <DialogFooter>
                <button type="button" onClick={() => setForgotOpen(false)} className="h-9 px-4 text-sm rounded-lg border border-slate-200 hover:bg-slate-50">Cancel</button>
                <button type="submit" disabled={loading} className="h-9 px-4 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark disabled:opacity-50 inline-flex items-center gap-2">
                  {loading && <Spinner className="h-3.5 w-3.5 animate-spin" />}Send Reset Link
                </button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};
