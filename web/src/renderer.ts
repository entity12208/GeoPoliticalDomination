import type { ChatMessage, Country, GameState, Player } from './types';
import { AuthManager, CloudGameClient } from './firebase';

const COLORS = ['#60a5fa', '#34d399', '#fbbf24', '#f87171', '#a78bfa', '#f472b6'];

export class Renderer {
  private app: HTMLElement;
  private canvas: HTMLCanvasElement;
  private context: CanvasRenderingContext2D;
  private gameClient: GameClient;
  private selectedAction: string | null = null;

  constructor(app: HTMLElement, gameClient: GameClient) {
    this.app = app;
    this.gameClient = gameClient;
    this.canvas = document.createElement('canvas');
    this.context = this.canvas.getContext('2d') as CanvasRenderingContext2D;
  }

  init(): void {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;

    const shell = document.createElement('div');
    shell.className = 'game-shell';
    shell.innerHTML = `
      <div class="topbar">
        <div class="game-title">GeoPolitical Domination</div>
        <div class="topbar-actions">
          <span class="badge" id="turn-badge">Turn 1</span>
          <button class="secondary-btn" id="logout-btn" type="button">Logout</button>
        </div>
      </div>
      <div class="canvas-wrap">
        <canvas id="game-canvas"></canvas>
        <div class="hud">
          <div class="hud-panel left-panel">
            <h3 class="panel-title">Players</h3>
            <div id="player-list" class="player-list"></div>
          </div>

          <div class="hud-panel right-panel">
            <h3 class="panel-title">Actions</h3>
            <div class="action-stack">
              <button class="action-btn" data-action="PEACE" type="button">Peace</button>
              <button class="action-btn" data-action="GATHER" type="button">Gather</button>
              <button class="action-btn" data-action="EXPAND" type="button">Expand</button>
              <button class="action-btn" data-action="NOTHING" type="button">Nothing</button>
            </div>

            <div class="chat-box">
              <div id="chat-output" class="chat-output"></div>
              <form id="chat-form" class="chat-form">
                <input id="chat-input" type="text" maxlength="160" placeholder="Say something..." />
                <button type="submit" class="primary-btn">Send</button>
              </form>
            </div>
          </div>

          <div id="log-box" class="log-box"></div>
        </div>
      </div>
    `;

    this.app.innerHTML = '';
    this.app.appendChild(shell);

    const canvasEl = shell.querySelector('canvas') as HTMLCanvasElement;
    this.canvas = canvasEl;
    this.context = this.canvas.getContext('2d') as CanvasRenderingContext2D;

    const chatForm = shell.querySelector('#chat-form') as HTMLFormElement;
    const chatInput = shell.querySelector('#chat-input') as HTMLInputElement;
    const logoutBtn = shell.querySelector('#logout-btn') as HTMLButtonElement;
    const actionButtons = shell.querySelectorAll('[data-action]');

    logoutBtn.addEventListener('click', () => {
      this.gameClient.stop();
      localStorage.removeItem('gpd-auth-token');
      window.location.reload();
    });

    actionButtons.forEach((button) => {
      button.addEventListener('click', () => {
        this.selectedAction = (button as HTMLElement).dataset.action ?? null;
        actionButtons.forEach((btn) => {
          (btn as HTMLElement).style.borderColor = 'rgba(148, 163, 184, 0.3)';
          (btn as HTMLElement).style.background = 'rgba(30, 41, 59, 0.9)';
        });
        if (this.selectedAction) {
          (button as HTMLElement).style.borderColor = '#60a5fa';
          (button as HTMLElement).style.background = 'rgba(37, 99, 235, 0.2)';
        }

        if (this.selectedAction) {
          void this.gameClient.submitAction(this.selectedAction);
        }
      });
    });

    chatForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const message = chatInput.value.trim();
      if (!message) return;
      await this.gameClient.sendChat(message);
      chatInput.value = '';
      this.render();
    });

    window.addEventListener('resize', () => {
      this.canvas.width = window.innerWidth;
      this.canvas.height = window.innerHeight;
      this.render();
    });

    this.gameClient.subscribe(() => this.render());
    this.render();
  }

  render(): void {
    const state = this.gameClient.getGameState();
    if (!state) return;

    const canvas = this.canvas;
    const context = this.context;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = '#111827';
    context.fillRect(0, 0, canvas.width, canvas.height);

    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = Math.min(canvas.width, canvas.height) * 0.22;

    const countries = Object.values(state.countries);
    if (countries.length > 0) {
      countries.forEach((country, index) => {
        const angle = (index / countries.length) * Math.PI * 2;
        const x = centerX + Math.cos(angle) * radius;
        const y = centerY + Math.sin(angle) * radius;

        context.beginPath();
        context.fillStyle = country.owner ? (country.color ?? '#60a5fa') : '#1f2937';
        context.arc(x, y, 18, 0, Math.PI * 2);
        context.fill();

        context.fillStyle = '#e2e8f0';
        context.font = '12px sans-serif';
        context.textAlign = 'center';
        context.fillText(String(country.troops || 0), x, y + 4);
      });
    } else {
      context.fillStyle = '#dbeafe';
      context.font = '18px sans-serif';
      context.textAlign = 'center';
      context.fillText('Waiting for world map data...', centerX, centerY);
    }

    this.renderPlayerList(state);
    this.renderLogs(state);
    this.renderChat();

    const badge = document.getElementById('turn-badge');
    if (badge) badge.textContent = `Turn ${state.turnNumber}`;
  }

  private renderPlayerList(state: GameState): void {
    const container = document.getElementById('player-list');
    if (!container) return;

    container.innerHTML = (state.players ?? []).map((player: Player, idx: number) => {
      const isCurrent = idx === state.turnIdx;
      return `
        <div class="player-item">
          <div class="player-meta">
            <span class="player-swatch" style="background:${player.color};"></span>
            <span>${player.name}${isCurrent ? ' •' : ''}</span>
          </div>
          <span class="player-money">$${player.money ?? 0}</span>
        </div>
      `;
    }).join('') || '<div class="empty-state">No players yet.</div>';
  }

  private renderLogs(state: GameState): void {
    const box = document.getElementById('log-box');
    if (!box) return;
    if (!state.logs || state.logs.length === 0) {
      box.innerHTML = '<div class="empty-state">No events yet.</div>';
      return;
    }

    box.innerHTML = state.logs.slice(-8).reverse().map((entry) => `<div class="log-entry">${entry}</div>`).join('');
  }

  private async renderChat(): Promise<void> {
    const output = document.getElementById('chat-output');
    if (!output) return;
    const messages = await this.gameClient.getChatMessages();
    if (!messages || messages.length === 0) {
      output.innerHTML = '<div class="empty-state">No chat messages.</div>';
      return;
    }
    output.innerHTML = messages.slice(-8).map((msg: ChatMessage) => `
      <div class="chat-line"><strong>${msg.sender}</strong>: ${msg.message}</div>
    `).join('');
  }
}

export class GameClient {
  private auth: AuthManager;
  private cloud: CloudGameClient;
  private state: GameState | null = null;
  private subscribers = new Set<() => void>();
  private poller: number | null = null;

  constructor(auth: AuthManager, cloud: CloudGameClient) {
    this.auth = auth;
    this.cloud = cloud;
  }

  setState(state: GameState | null): void {
    this.state = state;
    this.notify();
  }

  getGameState(): GameState | null {
    return this.state;
  }

  subscribe(fn: () => void): void {
    this.subscribers.add(fn);
  }

  notify(): void {
    this.subscribers.forEach((fn) => fn());
  }

  async createGame(gameId: string): Promise<GameState> {
    const username = this.auth.getUsername() ?? 'Player';
    const initial: GameState = {
      gameId,
      players: [{ name: username, color: '#60a5fa', money: 500 }],
      countries: {
        c1: { id: 'c1', name: 'North Sea', owner: username, troops: 5, continent: 'Europe', x: 0, y: 0, color: '#60a5fa' },
        c2: { id: 'c2', name: 'Caspian', owner: null, troops: 2, continent: 'Asia', x: 120, y: 80, color: '#64748b' },
        c3: { id: 'c3', name: 'Tundra', owner: null, troops: 1, continent: 'North America', x: 220, y: 0, color: '#64748b' }
      },
      turnIdx: 0,
      turnNumber: 1,
      logs: [`${username} created the game.`],
      status: 'playing',
      mode: 'classic',
      mapScope: 'world',
      createdAt: new Date().toISOString()
    };

    const payload = {
      ...initial,
      players: initial.players.map((player) => ({ name: player.name, color: player.color, money: player.money }))
    };

    await this.cloud.writeGame(gameId, payload as Record<string, unknown>);
    this.state = initial;
    this.startPolling(gameId);
    this.notify();
    return initial;
  }

  async joinGame(gameId: string): Promise<GameState | null> {
    const result = await this.cloud.readGame(gameId);
    if (!result) return null;

    const players = Array.isArray(result.players) ? result.players : [];
    const username = this.auth.getUsername() ?? 'Player';
    if (!players.some((item: any) => item.name === username)) {
      players.push({ name: username, color: '#34d399', money: 500 });
      await this.cloud.writeGame(gameId, { ...result, players });
    }

    const next: GameState = {
      gameId,
      players,
      countries: result.countries ?? {},
      turnIdx: Number(result.turnIdx ?? 0),
      turnNumber: Number(result.turnNumber ?? 1),
      logs: Array.isArray(result.logs) ? result.logs : [],
      status: result.status ?? 'playing',
      mode: result.mode ?? 'classic',
      mapScope: result.mapScope ?? 'world',
      createdAt: result.createdAt ?? new Date().toISOString()
    };

    this.state = next;
    this.startPolling(gameId);
    this.notify();
    return next;
  }

  private startPolling(gameId: string): void {
    if (this.poller) window.clearInterval(this.poller);
    this.poller = window.setInterval(async () => {
      const result = await this.cloud.readGame(gameId);
      if (!result) return;
      this.state = {
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
    }, 1500);
  }

  async submitAction(action: string): Promise<void> {
    if (!this.state) return;
    const nextTurn = (this.state.turnIdx + 1) % Math.max(this.state.players.length, 1);
    this.state = {
      ...this.state,
      turnIdx: nextTurn,
      turnNumber: this.state.turnNumber + 1,
      logs: [...this.state.logs, `${this.auth.getUsername() ?? 'Player'} chose ${action}.`]
    };
    await this.cloud.writeGame(this.state.gameId, {
      ...this.state,
      players: this.state.players
    } as Record<string, unknown>);
    this.notify();
  }

  async sendChat(message: string): Promise<void> {
    if (!this.state) return;
    await this.cloud.sendChat(this.state.gameId, this.auth.getUsername() ?? 'Player', message.trim());
  }

  async getChatMessages(): Promise<ChatMessage[]> {
    if (!this.state) return [];
    return this.cloud.getChat(this.state.gameId);
  }

  stop(): void {
    if (this.poller) {
      window.clearInterval(this.poller);
      this.poller = null;
    }
  }
}
