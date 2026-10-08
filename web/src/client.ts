import { FirebaseController } from './firebase';
import type { GameState, Player, Country, ChatMessage } from './types';

const CLAIM_COST = 200;
const TROOP_COST = 50;

export class GameClient {
    private firebase: FirebaseController;
    private username: string;
    private gameState: GameState | null = null;
    private pollInterval: number | null = null;
    private updateCallbacks: Set<() => void> = new Set();

    constructor(firebase: FirebaseController, username: string) {
        this.firebase = firebase;
        this.username = username;
    }

    async createGame(
        gameId: string,
        mode: string = 'classic',
        mapScope: string = 'world',
        isPrivate: boolean = false
    ): Promise<GameState> {
        const gameState: GameState = {
            players: [
                {
                    name: this.username,
                    isBot: false,
                    color: '#C85050',
                    money: 500,
                    vulnerable: false,
                    wasAttacked: false,
                    troopBuyLimit: 20,
                },
            ],
            countries: {},
            turnIdx: 0,
            turnNumber: 1,
            logs: [`Game created by ${this.username}`],
            status: 'waiting',
            gameId,
            mode,
            mapScope,
            isPrivate,
            createdAt: new Date().toISOString(),
        };

        await this.firebase.updateGameState(gameId, gameState);
        this.gameState = gameState;
        this.startPolling(gameId);
        return gameState;
    }

    async joinGame(gameId: string): Promise<GameState | null> {
        const state = await this.firebase.getGameState(gameId);
        if (!state) return null;

        // Add player to game
        const existingPlayer = state.players.find(p => p.name === this.username);
        if (!existingPlayer) {
            state.players.push({
                name: this.username,
                isBot: false,
                color: `#${Math.floor(Math.random() * 16777215).toString(16)}`,
                money: 500,
                vulnerable: false,
                wasAttacked: false,
                troopBuyLimit: 20,
            });
            await this.firebase.updateGameState(gameId, state);
        }

        this.gameState = state;
        this.startPolling(gameId);
        return state;
    }

    private startPolling(gameId: string): void {
        if (this.pollInterval) clearInterval(this.pollInterval);
        this.pollInterval = window.setInterval(async () => {
            const newState = await this.firebase.getGameState(gameId);
            if (newState) {
                this.gameState = newState;
                this.notifyUpdates();
            }
        }, 1000);
    }

    stopPolling(): void {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    getGameState(): GameState | null {
        return this.gameState;
    }

    getCurrentPlayer(): Player | null {
        if (!this.gameState) return null;
        return this.gameState.players[this.gameState.turnIdx] || null;
    }

    isMyTurn(): boolean {
        const current = this.getCurrentPlayer();
        return current?.name === this.username;
    }

    async submitAction(action: string, params: any): Promise<boolean> {
        if (!this.gameState || !this.isMyTurn()) return false;
        return this.firebase.submitAction(this.gameState.gameId, this.username, action, params);
    }

    async sendChatMessage(message: string): Promise<void> {
        if (!this.gameState) return;
        await this.firebase.sendChatMessage(this.gameState.gameId, this.username, message);
    }

    async getChatMessages(): Promise<ChatMessage[]> {
        if (!this.gameState) return [];
        return this.firebase.getChatMessages(this.gameState.gameId);
    }

    subscribe(callback: () => void): void {
        this.updateCallbacks.add(callback);
    }

    unsubscribe(callback: () => void): void {
        this.updateCallbacks.delete(callback);
    }

    private notifyUpdates(): void {
        this.updateCallbacks.forEach(cb => cb());
    }
}
