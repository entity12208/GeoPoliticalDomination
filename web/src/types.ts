export interface Player {
    name: string;
    isBot: boolean;
    color: string;
    money: number;
    vulnerable: boolean;
    wasAttacked: boolean;
    troopBuyLimit: number;
    elo?: number;
    eliminated?: boolean;
    isSpectator?: boolean;
}

export interface Country {
    id: string;
    owner: string | null;
    troops: number;
    continent: string;
    coordinates: [number, number];
}

export interface GameState {
    players: Player[];
    countries: { [key: string]: Country };
    turnIdx: number;
    turnNumber: number;
    logs: string[];
    status: 'waiting' | 'playing' | 'finished';
    gameId: string;
    mode: string;
    mapScope: string;
    isPrivate: boolean;
    joinCode?: string;
    createdAt: string;
}

export interface ChatMessage {
    sender: string;
    message: string;
    timestamp: string;
}

export interface GameAction {
    type: 'PEACE' | 'EXPAND' | 'GATHER' | 'NOTHING';
    params: { [key: string]: any };
}
