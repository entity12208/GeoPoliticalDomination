import { GameClient } from './client';
import type { GameState } from './types';

export class GameRenderer {
    private container: HTMLElement;
    private gameClient: GameClient;
    private canvas: HTMLCanvasElement | null = null;
    private ctx: CanvasRenderingContext2D | null = null;
    private cameraX: number = 0;
    private cameraY: number = 0;
    private cameraScale: number = 1;
    private chatMessages: string[] = [];
    private lastChatCheck: number = 0;

    constructor(container: HTMLElement, gameClient: GameClient) {
        this.container = container;
        this.gameClient = gameClient;
    }

    async initialize(): Promise<void> {
        // Create canvas
        this.canvas = document.createElement('canvas');
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.container.appendChild(this.canvas);
        this.ctx = this.canvas.getContext('2d')!;

        // Create HUD
        this.createHUD();

        // Subscribe to game updates
        this.gameClient.subscribe(() => this.render());

        // Handle window resize
        window.addEventListener('resize', () => {
            if (this.canvas) {
                this.canvas.width = window.innerWidth;
                this.canvas.height = window.innerHeight;
            }
        });

        // Handle mouse and keyboard
        this.setupInputHandlers();
    }

    private createHUD(): void {
        const hudHTML = `
            <div class="hud">
                <div class="top-hud">
                    <div class="game-info">
                        <div class="game-info-row">
                            <span class="game-info-label">Players</span>
                            <span class="game-info-value" id="playerCount">0/6</span>
                        </div>
                        <div class="game-info-row">
                            <span class="game-info-label">Turn</span>
                            <span class="game-info-value" id="turnNumber">1</span>
                        </div>
                    </div>
                    <div class="turn-indicator">
                        <div class="player-name" id="currentPlayerName">-</div>
                        <div class="turn-number" id="turnValue">Turn 1</div>
                    </div>
                </div>

                <div class="left-panel">
                    <div class="panel-header">Players</div>
                    <div class="panel-content" id="playersList"></div>
                </div>

                <div class="right-panel">
                    <div class="panel-header">Actions</div>
                    <div class="action-buttons" id="actionButtons"></div>
                    <div class="chat-box">
                        <div class="chat-messages" id="chatMessages"></div>
                        <div class="chat-input-group">
                            <input type="text" class="chat-input" id="chatInput" placeholder="Message...">
                            <button class="chat-send-btn" id="chatSendBtn">Send</button>
                        </div>
                    </div>
                </div>

                <div class="chat-log">
                    <div id="gameLog"></div>
                </div>
            </div>
        `;

        const hud = document.createElement('div');
        hud.innerHTML = hudHTML;
        this.container.appendChild(hud);

        // Setup chat
        const chatInput = this.container.querySelector('#chatInput') as HTMLInputElement;
        const chatSendBtn = this.container.querySelector('#chatSendBtn') as HTMLButtonElement;

        chatSendBtn.addEventListener('click', async () => {
            if (chatInput.value.trim()) {
                await this.gameClient.sendChatMessage(chatInput.value);
                chatInput.value = '';
            }
        });
    }

    private setupInputHandlers(): void {
        if (!this.canvas) return;

        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const delta = e.deltaY > 0 ? 1.1 : 0.9;
            this.cameraScale *= delta;
            this.cameraScale = Math.max(0.5, Math.min(4, this.cameraScale));
        });

        let isDragging = false;
        let dragStartX = 0;
        let dragStartY = 0;

        this.canvas.addEventListener('mousedown', (e) => {
            if (e.button === 2) {
                isDragging = true;
                dragStartX = e.clientX;
                dragStartY = e.clientY;
            }
        });

        this.canvas.addEventListener('mousemove', (e) => {
            if (isDragging) {
                const dx = e.clientX - dragStartX;
                const dy = e.clientY - dragStartY;
                this.cameraX -= dx / this.cameraScale;
                this.cameraY -= dy / this.cameraScale;
                dragStartX = e.clientX;
                dragStartY = e.clientY;
            }
        });

        this.canvas.addEventListener('mouseup', () => {
            isDragging = false;
        });

        this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    }

    render(): void {
        if (!this.ctx || !this.canvas) return;

        const gameState = this.gameClient.getGameState();
        if (!gameState) return;

        // Clear canvas
        this.ctx.fillStyle = '#1e2a3a';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        // Draw grid background
        this.drawBackground();

        // Draw countries (placeholder)
        this.drawCountries(gameState);

        // Update HUD
        this.updateHUD(gameState);
    }

    private drawBackground(): void {
        if (!this.ctx || !this.canvas) return;

        const gridSize = 50 * this.cameraScale;
        const startX = Math.floor(this.cameraX / gridSize) * gridSize;
        const startY = Math.floor(this.cameraY / gridSize) * gridSize;

        this.ctx.strokeStyle = '#2a3a4a';
        this.ctx.lineWidth = 1;

        for (
            let x = startX;
            x < this.canvas.width / this.cameraScale + this.cameraX;
            x += gridSize / this.cameraScale
        ) {
            this.ctx.beginPath();
            this.ctx.moveTo(x - this.cameraX, 0);
            this.ctx.lineTo(x - this.cameraX, this.canvas.height);
            this.ctx.stroke();
        }

        for (
            let y = startY;
            y < this.canvas.height / this.cameraScale + this.cameraY;
            y += gridSize / this.cameraScale
        ) {
            this.ctx.beginPath();
            this.ctx.moveTo(0, y - this.cameraY);
            this.ctx.lineTo(this.canvas.width, y - this.cameraY);
            this.ctx.stroke();
        }
    }

    private drawCountries(gameState: GameState): void {
        if (!this.ctx) return;

        // TODO: Implement proper country drawing with GeoJSON
        // For now, just draw placeholder circles

        Object.values(gameState.countries).forEach((country: any, index: number) => {
            const x = 100 + (index % 10) * 150 - this.cameraX;
            const y = 100 + Math.floor(index / 10) * 150 - this.cameraY;

            // Draw country circle
            this.ctx!.fillStyle = country.owner ? country.color || '#666' : '#444';
            this.ctx!.beginPath();
            this.ctx!.arc(x, y, 30 * this.cameraScale, 0, Math.PI * 2);
            this.ctx!.fill();

            // Draw border
            this.ctx!.strokeStyle = '#fff';
            this.ctx!.lineWidth = 2;
            this.ctx!.stroke();

            // Draw troops
            if (country.troops > 0) {
                this.ctx!.fillStyle = '#fff';
                this.ctx!.font = `${14 * this.cameraScale}px Arial`;
                this.ctx!.textAlign = 'center';
                this.ctx!.textBaseline = 'middle';
                this.ctx!.fillText(String(country.troops), x, y);
            }
        });
    }

    private updateHUD(gameState: GameState): void {
        const playerCount = this.container.querySelector('#playerCount');
        if (playerCount) {
            playerCount.textContent = `${gameState.players.length}/6`;
        }

        const turnNumber = this.container.querySelector('#turnNumber');
        if (turnNumber) {
            turnNumber.textContent = String(gameState.turnNumber);
        }

        const currentPlayerName = this.container.querySelector('#currentPlayerName');
        const currentPlayer = this.gameClient.getCurrentPlayer();
        if (currentPlayerName && currentPlayer) {
            currentPlayerName.textContent = currentPlayer.name;
        }

        const turnValue = this.container.querySelector('#turnValue');
        if (turnValue) {
            turnValue.textContent = `Turn ${gameState.turnNumber}`;
        }

        // Update players list
        const playersList = this.container.querySelector('#playersList');
        if (playersList) {
            playersList.innerHTML = gameState.players
                .map(
                    (player) => `
                <div class="player-item">
                    <div class="player-name-label">
                        <span class="player-color" style="background: ${player.color}"></span>
                        ${player.name}${player.isBot ? ' (BOT)' : ''}
                    </div>
                    <div class="player-stat">Money: <span class="player-stat-value">$${player.money}</span></div>
                    <div class="player-stat">Status: <span class="player-stat-value">${player.vulnerable ? 'VULNERABLE' : 'Safe'}</span></div>
                </div>
            `
                )
                .join('');
        }

        // Update action buttons
        const actionButtons = this.container.querySelector('#actionButtons');
        if (actionButtons && this.gameClient.isMyTurn()) {
            actionButtons.innerHTML = `
                <button class="action-btn" id="actionPeace">PEACE (Earn $100 per country)</button>
                <button class="action-btn" id="actionExpand">EXPAND (Attack/Claim)</button>
                <button class="action-btn" id="actionGather">GATHER (Buy troops)</button>
                <button class="action-btn" id="actionNothing">NOTHING (Skip turn)</button>
            `;

            actionButtons.querySelectorAll('.action-btn').forEach((btn) => {
                btn.addEventListener('click', async () => {
                    const action = (btn as HTMLElement).id.replace('action', '');
                    await this.gameClient.submitAction(action, {});
                });
            });
        } else if (actionButtons) {
            actionButtons.innerHTML = '<p style="text-align: center; color: #96a0b4; padding: 10px;">Waiting for your turn...</p>';
        }

        // Update game log
        const gameLog = this.container.querySelector('#gameLog');
        if (gameLog) {
            gameLog.innerHTML = gameState.logs
                .slice(-10)
                .map((log) => `<div class="log-item">${log}</div>`)
                .join('');
        }
    }
}
