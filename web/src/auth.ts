const FIREBASE_API_KEY = "AIzaSyA0QGbUDzgp3a3XkP1WGTXsW-JM0r2S36s";
const SIGN_UP_URL = `https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=${FIREBASE_API_KEY}`;
const SIGN_IN_URL = `https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${FIREBASE_API_KEY}`;
const EMAIL_DOMAIN = "gpd.local";

interface AuthToken {
    idToken: string;
    refreshToken: string;
    uid: string;
    username: string;
}

export class AuthManager {
    private token: AuthToken | null = null;

    constructor() {
        this.loadToken();
    }

    private loadToken(): void {
        const stored = localStorage.getItem('gpd_auth_token');
        if (stored) {
            try {
                this.token = JSON.parse(stored);
            } catch (e) {
                this.token = null;
            }
        }
    }

    private saveToken(): void {
        if (this.token) {
            localStorage.setItem('gpd_auth_token', JSON.stringify(this.token));
        }
    }

    private usernameToEmail(username: string): string {
        return `${username.trim().toLowerCase()}@${EMAIL_DOMAIN}`;
    }

    async register(username: string, password: string): Promise<void> {
        if (!username || username.length < 3 || username.length > 20) {
            throw new Error('Username must be 3-20 characters.');
        }
        if (!password || password.length < 4) {
            throw new Error('Password must be at least 4 characters.');
        }

        const email = this.usernameToEmail(username);
        const response = await fetch(SIGN_UP_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email,
                password,
                returnSecureToken: true,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            const message = error.error?.message || 'Registration failed';
            if (message.includes('EMAIL_EXISTS')) {
                throw new Error('That username is already taken.');
            }
            throw new Error(message);
        }

        const data = await response.json();
        this.token = {
            idToken: data.idToken,
            refreshToken: data.refreshToken,
            uid: data.localId,
            username,
        };
        this.saveToken();
    }

    async login(username: string, password: string): Promise<void> {
        if (!username || !password) {
            throw new Error('Username and password are required.');
        }

        const email = this.usernameToEmail(username);
        const response = await fetch(SIGN_IN_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email,
                password,
                returnSecureToken: true,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            const message = error.error?.message || 'Login failed';
            if (message.includes('EMAIL_NOT_FOUND')) {
                throw new Error('Account not found.');
            }
            if (message.includes('INVALID_PASSWORD')) {
                throw new Error('Incorrect password.');
            }
            throw new Error(message);
        }

        const data = await response.json();
        this.token = {
            idToken: data.idToken,
            refreshToken: data.refreshToken,
            uid: data.localId,
            username,
        };
        this.saveToken();
    }

    logout(): void {
        this.token = null;
        localStorage.removeItem('gpd_auth_token');
    }

    get isLoggedIn(): boolean {
        return !!this.token;
    }

    getUsername(): string | null {
        return this.token?.username || null;
    }

    getToken(): string | null {
        return this.token?.idToken || null;
    }

    getUID(): string | null {
        return this.token?.uid || null;
    }

    renderAuthScreen(container: HTMLElement, onSuccess: () => void): void {
        container.innerHTML = `
            <div class="auth-container">
                <div class="auth-box">
                    <h1>GeoPolitical Domination</h1>
                    <p>Web Edition - Play Online</p>
                    <div class="error-message" id="errorMsg"></div>
                    <form id="authForm">
                        <div class="form-group">
                            <label for="username">Username</label>
                            <input type="text" id="username" name="username" required>
                        </div>
                        <div class="form-group">
                            <label for="password">Password</label>
                            <input type="password" id="password" name="password" required>
                        </div>
                        <button type="button" class="button" id="loginBtn">Login</button>
                        <button type="button" class="button button-secondary" id="registerBtn">Create Account</button>
                    </form>
                </div>
            </div>
        `;

        const loginBtn = container.querySelector('#loginBtn') as HTMLButtonElement;
        const registerBtn = container.querySelector('#registerBtn') as HTMLButtonElement;
        const usernameInput = container.querySelector('#username') as HTMLInputElement;
        const passwordInput = container.querySelector('#password') as HTMLInputElement;
        const errorMsg = container.querySelector('#errorMsg') as HTMLDivElement;

        const showError = (message: string) => {
            errorMsg.textContent = message;
            errorMsg.classList.add('show');
        };

        const hideError = () => {
            errorMsg.classList.remove('show');
        };

        loginBtn.addEventListener('click', async () => {
            hideError();
            loginBtn.disabled = true;
            try {
                await this.login(usernameInput.value, passwordInput.value);
                onSuccess();
            } catch (error) {
                showError((error as Error).message);
            } finally {
                loginBtn.disabled = false;
            }
        });

        registerBtn.addEventListener('click', async () => {
            hideError();
            registerBtn.disabled = true;
            try {
                await this.register(usernameInput.value, passwordInput.value);
                onSuccess();
            } catch (error) {
                showError((error as Error).message);
            } finally {
                registerBtn.disabled = false;
            }
        });
    }
}
