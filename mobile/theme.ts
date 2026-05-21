/**
 * theme.ts
 * --------
 * Central design tokens. Import Colors, Typography, and Spacing
 * everywhere instead of hardcoding values in each screen.
 */

export const Colors = {
  navy:        '#1E3A8A',
  indigo:      '#6366F1',
  indigoDark:  '#4F46E5',
  bg:          '#EEF2FF',
  text:        '#1F2937',
  muted:       '#6B7280',
  border:      '#E5E7EB',
  placeholder: '#C4C4C4',
  success:     '#10B981',
  danger:      '#EF4444',
  warning:     '#F59E0B',

  // Department accent colours
  hr:      { bg: '#FFF1F2', accent: '#E11D48' },
  it:      { bg: '#EFF6FF', accent: '#2563EB' },
  finance: { bg: '#F0FDF4', accent: '#16A34A' },
  legal:   { bg: '#FAF5FF', accent: '#9333EA' },
  admin:   { bg: '#FFF7ED', accent: '#EA580C' },
} as const;

export const Typography = {
  h1:      { fontSize: 24, fontWeight: '800' as const },
  h2:      { fontSize: 20, fontWeight: '700' as const },
  h3:      { fontSize: 17, fontWeight: '700' as const },
  body:    { fontSize: 15, fontWeight: '400' as const },
  caption: { fontSize: 13, fontWeight: '400' as const },
  label:   { fontSize: 12, fontWeight: '600' as const, color: '#6B7280', textTransform: 'uppercase' as const, letterSpacing: 0.5 },
};

export const Spacing = {
  xs: 4, sm: 8, md: 16, lg: 24, xl: 32,
};

export const Shadow = {
  card: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
  },
};
