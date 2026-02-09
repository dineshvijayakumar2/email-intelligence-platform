/**
 * OAuth Callback Page
 *
 * This is a minimal page that OAuth popups land on after authentication.
 * It stays at the callback URL so the parent window's polling can detect it,
 * read the URL parameters, and close the popup.
 *
 * Used for:
 * - Microsoft/Outlook OAuth: /auth/microsoft/callback
 * - Google OAuth: /auth/google/callback
 */

import React from 'react';
import { Spin } from 'antd';

const OAuthCallback: React.FC = () => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        color: 'white',
      }}
    >
      <Spin size="large" />
      <p style={{ marginTop: 16, fontSize: 16 }}>
        Completing authentication...
      </p>
      <p style={{ fontSize: 12, opacity: 0.7 }}>
        This window will close automatically.
      </p>
    </div>
  );
};

export default OAuthCallback;
