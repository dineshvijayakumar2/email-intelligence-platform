import type { ThemeConfig } from 'antd';

// Design tokens for glassmorphism
export const glassTokens = {
  // Glass backgrounds
  glassBg: 'rgba(255, 255, 255, 0.7)',
  glassBgStrong: 'rgba(255, 255, 255, 0.85)',
  glassBgLight: 'rgba(255, 255, 255, 0.5)',
  glassBorder: 'rgba(255, 255, 255, 0.3)',
  glassBorderStrong: 'rgba(255, 255, 255, 0.5)',

  // Backdrop blur values
  blurSm: '8px',
  blurMd: '16px',
  blurLg: '24px',

  // Shadows
  shadowGlass: '0 8px 32px rgba(31, 38, 135, 0.15)',
  shadowElevated: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
  shadowSoft: '0 4px 20px rgba(102, 126, 234, 0.1)',
  shadowHover: '0 12px 40px rgba(31, 38, 135, 0.2)',

  // Gradients
  gradientPrimary: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
  gradientSecondary: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
  gradientPage: 'linear-gradient(135deg, #f5f7fa 0%, #e4e8f0 100%)',
  gradientAccent: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',

  // Primary colors
  primaryColor: '#667eea',
  primaryColorLight: '#8b9ef5',
  primaryColorDark: '#4c5fd5',
  accentColor: '#764ba2',
  accentColorLight: '#9b6fc2',

  // Semantic colors
  successColor: '#52c41a',
  warningColor: '#faad14',
  errorColor: '#ff4d4f',
  infoColor: '#1890ff',

  // Neutral colors
  textPrimary: '#1f2937',
  textSecondary: '#6b7280',
  textMuted: '#9ca3af',
  bgPage: '#f5f7fa',
};

// Ant Design theme configuration
export const antTheme: ThemeConfig = {
  token: {
    // Primary colors
    colorPrimary: glassTokens.primaryColor,
    colorLink: glassTokens.primaryColor,
    colorLinkHover: glassTokens.primaryColorLight,

    // Border radius
    borderRadius: 8,
    borderRadiusLG: 12,
    borderRadiusSM: 6,

    // Typography
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif",
    fontSize: 14,

    // Shadows
    boxShadow: glassTokens.shadowSoft,
    boxShadowSecondary: glassTokens.shadowGlass,

    // Motion
    motionDurationMid: '0.3s',
    motionEaseInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
  },
  components: {
    Card: {
      borderRadiusLG: 16,
      paddingLG: 24,
    },
    Table: {
      borderRadiusLG: 12,
      headerBg: 'rgba(102, 126, 234, 0.05)',
      rowHoverBg: 'rgba(102, 126, 234, 0.04)',
    },
    Modal: {
      borderRadiusLG: 20,
      paddingContentHorizontalLG: 32,
    },
    Select: {
      borderRadius: 8,
      controlHeight: 40,
    },
    Input: {
      borderRadius: 8,
      controlHeight: 40,
    },
    Button: {
      borderRadius: 8,
      controlHeight: 40,
      primaryShadow: '0 4px 12px rgba(102, 126, 234, 0.3)',
    },
    Tag: {
      borderRadiusSM: 6,
    },
    DatePicker: {
      borderRadius: 8,
      controlHeight: 40,
    },
    Pagination: {
      borderRadius: 8,
    },
  },
};

export default antTheme;
