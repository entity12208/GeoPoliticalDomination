import type { ChatMessage, GameState, Player } from './types';
import { AuthManager, CloudGameClient } from './firebase';

const INITIAL_PLAYER_COLOR = '#60a5fa';

export class GameClient {
  private auth: AuthManager;
  private cloud: CloudGameClient;
  private gameState: GameState | null = null;
  private pollTimer: number | null = null;
  private subscribers = new Set<() => void>();

  constructor(auth: AuthManager, cloud: CloudGameClient) {
    this.auth = auth;
    this.cloud = cloud;
  }

  getGameState(): GameState | null {
    return this.gameState;
  }

  subscribe(fn: () => void): void {
    this.subscribers.add(fn);
  }

  unsubscribe(fn: () => void): void {
    this.subscribers.delete(fn);
  }

  notify(): void {
    this.subscribers.forEach((fn) => fn());
  }

  getUsername(): string {
    return this.auth.getUsername() ?? 'Guest';
  }

  getCurrentPlayer(): Player | null {
    if (!this.gameState) return null;
    return this.gameState.players[this.gameState.turnIdx] ?? null;
  }

  async createGame(gameId: string): Promise<GameState> {
    const username = this.getUsername();
    const state: GameState = {
      gameId,
      players: [{ name: username, color: INITIAL_PLAYER_COLOR, money: 500 }],
      countries: {},
      turnIdx: 0,
      turnNumber: 1,
      logs: [`${username} created the game.`],
      status: 'playing',
      mode: 'classic',
      mapScope: 'world',
      createdAt: new Date().toISOString()
    };

    await this.cloud.writeGame(gameId, {
      gameId,
      players: state.players,
      turnIdx: state.turnIdx,
      turnNumber: state.turnNumber,
      logs: state.logs,
      status: state.status,
      mode: state.mode,
      mapScope: state.mapScope,
      createdAt: state.createdAt
    });

    this.gameState = state;
    this.startPolling(gameId);
    this.notify();
    return state;
  }

  async joinGame(gameId: string): Promise<GameState | null> {
    const username = this.getUsername();
    const existing = await this.cloud.readGame(gameId);
    if (!existing) return null;

    const rawPlayers = existing.players ?? [];
    const players = Array.isArray(rawPlayers) ? rawPlayers : [];
    const alreadyExists = players.some((p: any) => p.name === username);

    if (!alreadyExists) {
      players.push({ name: username, color: '#34d399', money: 500 });
      await this.cloud.writeGame(gameId, {
        ...existing,
        players
      });
    }

    const state: GameState = {
      gameId,
      players,
      countries: existing.countries ?? {},
      turnIdx: Number(existing.turnIdx ?? 0),
      turnNumber: Number(existing.turnNumber ?? 1),
      logs: Array.isArray(existing.logs) ? existing.logs : [],
      status: existing.status ?? 'playing',
      mode: existing.mode ?? 'classic',
      mapScope: existing.mapScope ?? 'world',
      createdAt: existing.createdAt ?? new Date().toISOString()
    };

    this.gameState = state;
    this.startPolling(gameId);
    this.notify();
    return state;
  }

  private startPolling(gameId: string): void {
    if (this.pollTimer) {
      window.clearInterval(this.pollTimer);
    }

    this.pollTimer = window.setInterval(async () => {
      const result = await this.cloud.readGame(gameId);
      if (!result) return;

      this.gameState = {
        gameId,
        players: Array.isArray(result.players) ? result.players : [],
        countries: result.countries ?? {},
        turnIdx: Number(result.turnIdx ?? 0),
        turnNumber: Number(result.turnNumber ?? 1),
        logs: Array.isArray(result.logs) ? result.logs : [],
        status: result.status ?? 'playing',
        mode: result.mode ?? 'classic',
        mapScope: result.mapScope ?? 'world',
        createdAt: result.createdAt ?? new Date().toISOString()
      };
      this.notify();
    }, 1400);
  }

  async submitAction(action: string): Promise<void> {
    if (!this.gameState) return;

    const nextTurn = (this.gameState.turnIdx + 1) % this.gameState.players.length;
    const nextPlayer = this.gameState.players[nextTurn]?.name ?? this.getUsername();

    const newState: GameState = {
      ...this.gameState,
      turnIdx: nextTurn,
      turnNumber: this.gameState.turnNumber + 1,
      logs: [...this.gameState.logs, `${this.getUsername()} used ${action}. Next up: ${nextPlayer}.`]
    };

    await this.cloud.writeGame(this.gameState.gameId, {
      ...newState,
      players: newState.players
    });

    this.gameState = newState;
    this.notify();
  }

  async sendChat(message: string): Promise<void> {
    if (!this.gameState || !message.trim()) return;
    await this.cloud.sendChat(this.gameState.gameId, this.getUsername(), message.trim());
    const chat = await this.cloud.getChat(this.gameState.gameId);
    this.gameState.logs = [...this.gameState.logs, `${this.getUsername()}: ${message.trim()}`];
    this.notify();
    void chat;
  }

  async getChatMessages(): Promise<ChatMessage[]> {
    if (!this.gameState) return [];
    return this.cloud.getChat(this.gameState.gameId);
  }

  stop(): void {
    if (this.pollTimer) {
      window.clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }
}
