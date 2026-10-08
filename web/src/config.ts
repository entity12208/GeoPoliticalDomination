export const config = {
  firebase: {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY || 'AIzaSyA0QGbUDzgp3a3XkP1WGTXsW-JM0r2S36s',
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || 'geopoliticaldomination',
    databaseUrl: import.meta.env.VITE_FIREBASE_DATABASE_URL || 'https://geopoliticaldomination.firebaseio.com'
  },
  game: {
    mode: (import.meta.env.VITE_GAME_MODE || 'classic') as 'classic' | 'tournament' | 'challenge',
    mapScope: (import.meta.env.VITE_MAP_SCOPE || 'world') as 'world' | 'europe' | 'asia' | 'africa' | 'north_america' | 'south_america'
  }
};
