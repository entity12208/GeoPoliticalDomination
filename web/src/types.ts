export type GameMode = 'classic' | 'tournament' | 'challenge';
export type MapScope = 'world' | 'europe' | 'asia' | 'africa' | 'north_america' | 'south_america';

export interface Player {
  name: string;
  color: string;
  money: number;
  isBot?: boolean;
  vulnerable?: boolean;
  eliminated?: boolean;
  spectator?: boolean;
}

export interface Country {
  id: string;
  name: string;
  owner: string | null;
  troops: number;
  continent: string;
  x: number;
  y: number;
  color?: string;
}

export interface GameState {
  gameId: string;
  players: Player[];
  countries: Record<string, Country>;
  turnIdx: number;
  turnNumber: number;
  logs: string[];
  status: 'waiting' | 'playing' | 'finished';
  mode: GameMode;
  mapScope: MapScope;
  joinCode?: string;
  createdAt: string;
}

export interface ChatMessage {
  sender: string;
  message: string;
  timestamp: string;
}
