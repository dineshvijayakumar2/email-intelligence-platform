import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    './node_modules/@tremor/**/*.{js,ts,jsx,tsx}',
  ],
  // Disable preflight during migration — Ant Design styles need to coexist
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        // ── shadcn CSS variable tokens ──
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
        popover: { DEFAULT: 'hsl(var(--popover))', foreground: 'hsl(var(--popover-foreground))' },
        secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--secondary-foreground))' },
        muted: { DEFAULT: '#f1f5f9', foreground: '#64748b' },

        // ── Semantic tokens — ONE color per meaning ──
        // Never use raw colors (red-500, green-600) in components.
        // Change these to retheme the entire app.
        primary: {
          DEFAULT: '#667eea',
          foreground: '#ffffff',
          light: '#8b9ef5',
          dark: '#4c5fd5',
          subtle: '#eef0fd',  // bg tint for primary highlights
        },
        accent: {
          DEFAULT: '#764ba2',
          foreground: '#ffffff',
          light: '#9b6fc2',
          subtle: '#f3eef8',
        },
        destructive: {
          DEFAULT: '#ef4444',
          foreground: '#ffffff',
          subtle: '#fef2f2',  // bg tint for danger alerts
        },
        warning: {
          DEFAULT: '#f59e0b',
          foreground: '#ffffff',
          subtle: '#fffbeb',
        },
        success: {
          DEFAULT: '#10b981',
          foreground: '#ffffff',
          subtle: '#f0fdf4',
        },
        // Alias: "risk" = destructive but semantically distinct
        risk: {
          DEFAULT: '#dc2626',
          subtle: '#fef2f2',
          foreground: '#ffffff',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
};

export default config;
