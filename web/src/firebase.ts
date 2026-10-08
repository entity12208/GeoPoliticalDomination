import type { GameState, ChatMessage } from './types';

const FIREBASE_PROJECT_ID = "geopoliticaldomination";
const FIRESTORE_BASE = `https://firestore.googleapis.com/v1/projects/${FIREBASE_PROJECT_ID}/databases/(default)/documents`;

function toFS(value: any): any {
    if (value === null || value === undefined) return { nullValue: null };
    if (typeof value === 'boolean') return { booleanValue: value };
    if (typeof value === 'number') return { integerValue: String(value) };
    if (typeof value === 'string') return { stringValue: value };
    if (Array.isArray(value)) {
        return {
            arrayValue: {
                values: value.map(toFS),
            },
        };
    }
    if (typeof value === 'object') {
        return {
            mapValue: {
                fields: Object.fromEntries(
                    Object.entries(value).map(([k, v]) => [k, toFS(v)])
                ),
            },
        };
    }
    return { stringValue: String(value) };
}

function fromFS(value: any): any {
    if ('nullValue' in value) return null;
    if ('booleanValue' in value) return value.booleanValue;
    if ('integerValue' in value) return parseInt(value.integerValue);
    if ('doubleValue' in value) return value.doubleValue;
    if ('stringValue' in value) return value.stringValue;
    if ('arrayValue' in value) return (value.arrayValue.values || []).map(fromFS);
    if ('mapValue' in value) {
        const fields = value.mapValue.fields || {};
        return Object.fromEntries(
            Object.entries(fields).map(([k, v]: [string, any]) => [k, fromFS(v)])
        );
    }
    return null;
}

export class FirebaseController {
    private authToken: string | null = null;
    private uid: string | null = null;

    constructor(token?: string, uid?: string) {
        this.authToken = token || null;
        this.uid = uid || null;
    }

    async initialize(): Promise<void> {
        // Token should be set by auth manager
    }

    setAuth(token: string, uid: string): void {
        this.authToken = token;
        this.uid = uid;
    }

    private headers(): { [key: string]: string } {
        return {
            'Authorization': `Bearer ${this.authToken}`,
            'Content-Type': 'application/json',
        };
    }

    async getGameState(gameId: string): Promise<GameState | null> {
        try {
            const response = await fetch(`${FIRESTORE_BASE}/games/${gameId}`, {
                headers: this.headers(),
            });
            if (!response.ok) return null;
            const data = await response.json();
            return fromFS(data.fields) as GameState;
        } catch (e) {
            console.error('Failed to get game state:', e);
            return null;
        }
    }

    async updateGameState(gameId: string, updates: Partial<GameState>): Promise<void> {
        try {
            const body = {
                fields: Object.fromEntries(
                    Object.entries(updates).map(([k, v]) => [k, toFS(v)])
                ),
            };
            const response = await fetch(`${FIRESTORE_BASE}/games/${gameId}`, {
                method: 'PATCH',
                headers: this.headers(),
                body: JSON.stringify(body),
            });
            if (!response.ok) {
                console.error('Failed to update game state:', await response.text());
            }
        } catch (e) {
            console.error('Failed to update game state:', e);
        }
    }

    async getChatMessages(gameId: string, limit: number = 50): Promise<ChatMessage[]> {
        try {
            const response = await fetch(`${FIRESTORE_BASE}/games/${gameId}/chat`, {
                headers: this.headers(),
            });
            if (!response.ok) return [];
            const data = await response.json();
            const documents = data.documents || [];
            return documents
                .map((doc: any) => fromFS(doc.fields))
                .sort((a: ChatMessage, b: ChatMessage) => 
                    new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
                )
                .slice(-limit);
        } catch (e) {
            console.error('Failed to get chat messages:', e);
            return [];
        }
    }

    async sendChatMessage(gameId: string, sender: string, message: string): Promise<void> {
        try {
            const data = {
                sender,
                message,
                timestamp: new Date().toISOString(),
            };
            const body = { fields: Object.fromEntries(
                Object.entries(data).map(([k, v]) => [k, toFS(v)])
            ) };
            const response = await fetch(`${FIRESTORE_BASE}/games/${gameId}/chat`, {
                method: 'POST',
                headers: this.headers(),
                body: JSON.stringify(body),
            });
            if (!response.ok) {
                console.error('Failed to send chat message:', await response.text());
            }
        } catch (e) {
            console.error('Failed to send chat message:', e);
        }
    }

    async submitAction(gameId: string, playerName: string, action: string, params: any): Promise<boolean> {
        try {
            const response = await fetch(`${FIRESTORE_BASE}/games/${gameId}`, {
                method: 'PATCH',
                headers: this.headers(),
                body: JSON.stringify({
                    fields: {
                        lastAction: toFS({ type: action, params, player: playerName, timestamp: new Date().toISOString() }),
                    },
                }),
            });
            return response.ok;
        } catch (e) {
            console.error('Failed to submit action:', e);
            return false;
        }
    }

    async listPublicGames(): Promise<any[]> {
        try {
            const response = await fetch(`${FIRESTORE_BASE}/game_lobby`, {
                headers: this.headers(),
            });
            if (!response.ok) return [];
            const data = await response.json();
            return (data.documents || []).map((doc: any) => ({
                id: doc.name.split('/').pop(),
                ...fromFS(doc.fields),
            }));
        } catch (e) {
            console.error('Failed to list public games:', e);
            return [];
        }
    }
}
