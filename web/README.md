# GeoPolitical Domination - Web Edition

A fully-functional browser-based version of GeoPolitical Domination that connects to the same Firebase cloud backend as the desktop version. No installation required — just open in your browser!

## Quick Start

### Online (Recommended)
Visit the deployed web version (when available) and sign in with your credentials to play online.

### Local Development

```bash
cd web
npm install
npm run dev
```

The dev server will open at `http://localhost:5173`.

## Building for Production

```bash
cd web
npm install
npm run build
```

Output will be in the `dist/` directory, ready to serve on any static hosting (Vercel, Netlify, GitHub Pages, etc.).

## Features

- ✅ Full game logic (claim, expand, gather, peace)
- ✅ Real-time multiplayer via Firebase
- ✅ User authentication (register & login)
- ✅ In-game chat
- ✅ Player stats and leaderboards
- ✅ Multiple game modes (Classic, Tournament, Challenge)
- ✅ Responsive canvas-based rendering
- ✅ Turn-based turn system

## Architecture

- **Frontend**: TypeScript + Canvas for rendering
- **Backend**: Firebase (same as desktop version)
- **Build Tool**: Vite
- **Styling**: Pure CSS

## Project Structure

```
web/
├── src/
│   ├── main.ts          # Entry point
│   ├── auth.ts          # Firebase authentication
│   ├── firebase.ts      # Firebase Firestore API
│   ├── client.ts        # Game client logic
│   ├── renderer.ts      # Canvas rendering engine
│   ├── types.ts         # TypeScript type definitions
│   ├── index.html       # HTML template
│   └── styles.css       # Global styling
├── package.json
├── tsconfig.json
├── vite.config.ts
└── README.md
```

## Troubleshooting

### "Firebase auth failed"
- Check your internet connection
- Ensure you have created an account in the app
- The app uses anonymous auth if credentials are invalid

### "No games visible"
- Create a new game from the main menu
- Make sure the game is set to "Public"
- Wait a moment for the lobby to refresh

### "Canvas rendering is slow"
- Reduce browser zoom (Ctrl/Cmd + minus)
- Use a more modern browser (Chrome, Firefox, Safari, Edge)
- Disable browser extensions

## Deployment

The web version can be deployed to any static hosting service:

### Vercel
```bash
vercel
```

### Netlify
```bash
netlify deploy --prod --dir dist
```

### GitHub Pages
Push to a `gh-pages` branch or configure in repository settings.

## Contributing

Pull requests welcome! Please ensure TypeScript types are correct and code follows the existing style.
