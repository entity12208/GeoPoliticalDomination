import { AuthManager, CloudGameClient } from './firebase';
import { GameClient, Renderer } from './client';

const app = document.getElementById('app');
if (!app) throw new Error('App element not found');

const auth = new AuthManager();
const cloud = new CloudGameClient(auth);

function renderAuth(): void {
  app.innerHTML = `
    <div class="auth-screen">
      <div class="auth-card">
        <h1>GPD</h1>
        <p>GeoPolitical Domination Web</p>
        <div id="auth-error" class="error"></div>
        <div class="form-row">
          <label for="username">Username</label>
          <input id="username" type="text" maxlength="20" placeholder="Enter username" />
        </div>
        <div class="form-row">
          <label for="password">Password</label>
          <input id="password" type="password" placeholder="Enter password" />
        </div>
        <div class="button-row">
          <button id="login-btn" class="primary-btn" type="button">Login</button>
          <button id="register-btn" class="secondary-btn" type="button">Register</button>
        </div>
      </div>
    </div>
  `;

  const showError = (message: string) => {
    const errorNode = document.getElementById('auth-error');
    if (!errorNode) return;
    errorNode.textContent = message;
    errorNode.classList.add('visible');
  };

  const usernameInput = document.getElementById('username') as HTMLInputElement;
  const passwordInput = document.getElementById('password') as HTMLInputElement;
  const loginBtn = document.getElementById('login-btn') as HTMLButtonElement;
  const registerBtn = document.getElementById('register-btn') as HTMLButtonElement;

  const runAuth = async (mode: 'login' | 'register') => {
    try {
      if (mode === 'login') {
        await auth.login(usernameInput.value, passwordInput.value);
      } else {
        await auth.register(usernameInput.value, passwordInput.value);
      }
      startGame();
    } catch (error) {
      showError((error as Error).message || 'Authentication failed');
    }
  };

  loginBtn.addEventListener('click', () => void runAuth('login'));
  registerBtn.addEventListener('click', () => void runAuth('register'));
}

async function startGame(): Promise<void> {
  const username = auth.getUsername();
  if (!username) {
    renderAuth();
    return;
  }

  const client = new GameClient(auth, cloud);

  const gameId = 'gpd-web-lobby';
  const loaded = await client.joinGame(gameId);
  if (!loaded) {
    await client.createGame(gameId);
  }

  const renderer = new Renderer(app, client);
  renderer.init();
}

if (auth.getUsername()) {
  void startGame();
} else {
  renderAuth();
}
