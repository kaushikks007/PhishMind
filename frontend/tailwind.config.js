/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#FFFFFF',
        surface: '#F8FAFC',
        border: '#E2E8F0',
        'text-primary': '#1E293B',
        'text-secondary': '#64748B',
        danger: '#DC2626',
        suspicious: '#D97706',
        safe: '#059669',
        accent: '#4F46E5',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
