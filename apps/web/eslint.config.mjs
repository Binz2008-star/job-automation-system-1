import nextVitals from 'eslint-config-next/core-web-vitals';

const config = [
  ...nextVitals,
  {
    ignores: [
      'tsconfig.tsbuildinfo',
    ],
  },
];

export default config;
