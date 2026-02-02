/**
 * Auth Context
 *
 * Provides authentication state and methods using Supabase Auth.
 * Supports email/password, Google, and Microsoft OAuth login.
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { User, Session } from '@supabase/supabase-js';
import { supabase, getAccessToken } from '../lib/supabase';
import config from '../config';

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  roles: Array<'admin' | 'client_manager' | 'account_manager'>;
  isActive: boolean;
  avatarUrl?: string;
  accessibleMailboxIds: string[];
}

interface AuthContextType {
  user: User | null;
  session: Session | null;
  profile: UserProfile | null;
  loading: boolean;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signInWithMicrosoft: () => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isClientManager: boolean;
  isAccountManager: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const loadProfile = useCallback(async (accessToken: string) => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/auth/me`, {
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const data = await response.json();
        setProfile({
          id: data.id,
          email: data.email,
          name: data.name,
          roles: data.roles || ['account_manager'],
          isActive: data.is_active,
          avatarUrl: data.avatar_url,
          accessibleMailboxIds: data.accessible_mailbox_ids || [],
        });
      } else {
        console.error('Failed to load profile:', response.status);
        setProfile(null);
      }
    } catch (error) {
      console.error('Failed to load profile:', error);
      setProfile(null);
    }
  }, []);

  const refreshProfile = useCallback(async () => {
    const token = await getAccessToken();
    if (token) {
      await loadProfile(token);
    }
  }, [loadProfile]);

  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setUser(session?.user ?? null);
      if (session?.access_token) {
        loadProfile(session.access_token);
      }
      setLoading(false);
    });

    // Listen for auth changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, session) => {
      setSession(session);
      setUser(session?.user ?? null);

      if (session?.access_token) {
        await loadProfile(session.access_token);
      } else {
        setProfile(null);
      }

      if (event === 'SIGNED_OUT') {
        setProfile(null);
      }
    });

    return () => subscription.unsubscribe();
  }, [loadProfile]);

  const signInWithEmail = async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (error) throw error;
  };

  const signInWithGoogle = async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/`,
      },
    });
    if (error) throw error;
  };

  const signInWithMicrosoft = async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'azure',
      options: {
        redirectTo: `${window.location.origin}/`,
        scopes: 'email openid profile',
      },
    });
    if (error) throw error;
  };

  const signUp = async (email: string, password: string, name: string) => {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { name, full_name: name },
      },
    });
    if (error) throw error;
  };

  const signOut = async () => {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
    setProfile(null);
  };

  const value: AuthContextType = {
    user,
    session,
    profile,
    loading,
    signInWithEmail,
    signInWithGoogle,
    signInWithMicrosoft,
    signUp,
    signOut,
    refreshProfile,
    isAuthenticated: !!user,
    isAdmin: profile?.roles?.includes('admin') ?? false,
    isClientManager: profile?.roles?.includes('client_manager') ?? false,
    isAccountManager: profile?.roles?.includes('account_manager') ?? false,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;
