/**
 * OAuth Callback Page — minimal page for OAuth popups.
 */
import React from 'react';
import { Spinner } from '@/lib/icons';

const OAuthCallback: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center h-screen bg-gradient-to-br from-primary to-accent text-white">
      <Spinner className="h-8 w-8 animate-spin" />
      <p className="mt-4 text-base">Completing authentication...</p>
      <p className="text-xs opacity-70">This window will close automatically.</p>
    </div>
  );
};

export default OAuthCallback;
