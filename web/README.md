# GeoPolitical Domination - Web Edition

This directory contains the browser-based version of GeoPolitical Domination for deployment on Netlify.

## Local development

```bash
cd web
npm install
npm run dev
```

## Production build

```bash
cd web
npm run build:prod
```

## Netlify deployment

1. Connect the GitHub repo to Netlify.
2. Set base directory to `web`.
3. Build command: `npm run build:prod`
4. Publish directory: `dist`
5. Add env vars from `.env.example` if needed.

## Features

- Firebase auth/login/register flow
- Firebase Firestore-backed cloud state
- lobby/game state polling
- in-game chat
- TypeScript + Vite build for deployment
