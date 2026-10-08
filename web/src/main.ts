import { AuthManager } from './auth';
import { GameRenderer } from './renderer';
import { GameClient } from './client';
import { FirebaseController } from './firebase';

class App {
    private authManager: AuthManager;
    private gameRenderer: GameRenderer | null = null;
    private gameClient: GameClient | null = null;
    private firebaseController: FirebaseController | null = null;
    private appContainer: HTMLElement;

    constructor() {
        this.appContainer = document.getElementById('app')!;
        this.authManager = new AuthManager();
        this.setupUI();
    }

    private setupUI(): void {
        if (!this.authManager.isLoggedIn) {
            this.showAuthScreen();
        } else {
            this.startGame();
        }
    }

    private showAuthScreen(): void {
        this.appContainer.innerHTML = '';
        this.authManager.renderAuthScreen(this.appContainer, () => {
            this.setupUI();
        });
    }

    private async startGame(): Promise<void> {
        const username = this.authManager.getUsername();
        if (!username) {
            this.showAuthScreen();
            return;
        }

        // Initialize Firebase controller
        this.firebaseController = new FirebaseController();
        await this.firebaseController.initialize();

        // Initialize game client
        this.gameClient = new GameClient(this.firebaseController, username);

        // Initialize renderer
        this.gameRenderer = new GameRenderer(this.appContainer, this.gameClient);
        await this.gameRenderer.initialize();
        this.gameRenderer.render();
    }
}

// Start the app when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        new App();
    });
} else {
    new App();
}
