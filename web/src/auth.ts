const FIREBASE_SIGNUP_URL = 'https://identitytoolkit.googleapis.com/v1/accounts:signUp';
const FIREBASE_SIGNIN_URL = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword';
const FIREBASE_API_KEY = 'AIzaSyA0QGbUDzgp3a3XkP1WGTXsW-JM0r2S36s';
const PROJECT_ID = 'geopoliticaldomination';
const FIRESTORE_BASE = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)/documents`;

export class AuthManager {
  private tokenKey = 'gpd-auth-token';
  private token: { idToken: string; refreshToken: string; uid: string; username: string } | null = null;

  constructor() {
    const stored = localStorage.getItem(this.tokenKey);
    if (stored) {
      try {
        this.token = JSON.parse(stored);
      } catch {
        this.token = null;
      }
    }
  }

  private persist() {
    if (!this.token) {
      localStorage.removeItem(this.tokenKey);
      return;
    }
    localStorage.setItem(this.tokenKey, JSON.stringify(this.token));
  }

  private usernameToEmail(username: string): string {
    return `${username.trim().toLowerCase()}@gpd.local`;
  }

  async register(username: string, password: string): Promise<void> {
    if (!username || username.length < 3 || username.length > 20) {
      throw new Error('Username must be 3 to 20 characters.');
    }
    if (!password || password.length < 4) {
      throw new Error('Password must be at least 4 characters.');
    }

    const response = await fetch(`${FIREBASE_SIGNUP_URL}?key=${FIREBASE_API_KEY}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: this.usernameToEmail(username),
        password,
        returnSecureToken: true
      })
    });

    const data = await response.json();
    if (!response.ok) {
      const message = data?.error?.message ?? 'Registration failed';
      throw new Error(message);
    }

    this.token = {
      idToken: data.idToken,
      refreshToken: data.refreshToken,
      uid: data.localId,
      username
    };
    this.persist();
  }

  async login(username: string, password: string): Promise<void> {
    if (!username || !password) {
      throw new Error('Username and password are required.');
    }

    const response = await fetch(`${FIREBASE_SIGNIN_URL}?key=${FIREBASE_API_KEY}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: this.usernameToEmail(username),
        password,
        returnSecureToken: true
      })
    });

    const data = await response.json();
    if (!response.ok) {
      const message = data?.error?.message ?? 'Login failed';
      throw new Error(message);
    }

    this.token = {
      idToken: data.idToken,
      refreshToken: data.refreshToken,
      uid: data.localId,
      username
    };
    this.persist();
  }

  logout(): void {
    this.token = null;
    localStorage.removeItem(this.tokenKey);
  }

  getUsername(): string | null {
    return this.token?.username ?? null;
  }

  getUid(): string | null {
    return this.token?.uid ?? null;
  }

  getAuthHeader(): Record<string, string> {
    return {
      Authorization: `Bearer ${this.token?.idToken ?? ''}`,
      'Content-Type': 'application/json'
    };
  }

  getSignedInUser(): { username: string; uid: string } | null {
    if (!this.token) return null;
    return {
      username: this.token.username,
      uid: this.token.uid
    };
  }
}

export class CloudGameClient {
  private auth: AuthManager;

  constructor(auth: AuthManager) {
    this.auth = auth;
  }

  private async fetchJson(path: string, init?: RequestInit): Promise<any> {
    const response = await fetch(`${FIRESTORE_BASE}${path}`, {
      ...init,
      headers: {
        ...this.auth.getAuthHeader(),
        ...(init?.headers ?? {})
      }
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Cloud request failed (${response.status}): ${text}`);
    }

    return response.json();
  }

  async readGame(gameId: string): Promise<any | null> {
    try {
      const result = await this.fetchJson(`/games/${encodeURIComponent(gameId)}`);
      return result;
    } catch {
      return null;
    }
  }

  async writeGame(gameId: string, document: Record<string, unknown>): Promise<void> {
    const body = { fields: Object.fromEntries(Object.entries(document).map(([key, value]) => [key, { stringValue: String(value) }])) };
    await this.fetchJson(`/games/${encodeURIComponent(gameId)}`, {
      method: 'PATCH',
      body: JSON.stringify(body)
    });
  }

  async listPublicGames(): Promise<any[]> {
    try {
      const doc = await this.fetchJson('/game_lobby');
      const docs = doc.documents ?? [];
      return docs.map((item: any) => ({
        id: item.name.split('/').pop(),
        ...item.fields ?? {}
      }));
    } catch {
      return [];
    }
  }

  async getChat(gameId: string): Promise<any[]> {
    try {
      const doc = await this.fetchJson(`/games/${encodeURIComponent(gameId)}/chat`);
      const documents = doc.documents ?? [];
      return documents.map((item: any) => {
        const fields = item.fields ?? {};
        return {
          sender: fields.sender?.stringValue ?? '',
          message: fields.message?.stringValue ?? '',
          timestamp: fields.timestamp?.stringValue ?? new Date().toISOString()
        };
      });
    } catch {
      return [];
    }
  }

  async sendChat(gameId: string, sender: string, message: string): Promise<void> {
    const body = {
      fields: {
        sender: { stringValue: sender },
        message: { stringValue: message },
        timestamp: { stringValue: new Date().toISOString() }
      }
    };

    await this.fetchJson(`/games/${encodeURIComponent(gameId)}/chat`, {
      method: 'POST',
      body: JSON.stringify(body)
    });
  }

  async createOrJoinGame(gameId: string, username: string): Promise<Record<string, unknown>> {
    const payload = {
      gameId,
      players: {
        arrayValue: {
          values: [
            { mapValue: { fields: { name: { stringValue: username }, color: { stringValue: '#60a5fa' }, money: { integerValue: '500' } } } }
          ]
        }
      },
      turnIdx: { integerValue: '0' },
      turnNumber: { integerValue: '1' },
      logs: { arrayValue: { values: [{ stringValue: `${username} created the game.` }] } },
      status: { stringValue: 'playing' },
      mode: { stringValue: 'classic' },
      mapScope: { stringValue: 'world' },
      createdAt: { stringValue: new Date().toISOString() }
    };

    await this.fetchJson(`/games/${encodeURIComponent(gameId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ fields: payload })
    });

    return payload;
  }
}
