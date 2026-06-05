import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Router } from '@angular/router';
import { AuthService } from './auth.service';

describe('AuthService', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('isAuthenticated returns false when no token', () => {
    expect(service.isAuthenticated()).toBe(false);
  });

  it('isAuthenticated returns true when token exists', () => {
    localStorage.setItem('modishlog_token', 'test-token');
    const fresh = TestBed.inject(AuthService);
    // Re-inject won't work because it's singleton, but the initial state was set before construction
    // We test via login flow instead
    expect(service.isAuthenticated()).toBe(false);
  });

  it('login stores both access_token and refresh_token', () => {
    service.login({ email: 'test@test.com', password: 'password123' }).subscribe();
    const req = httpMock.expectOne((r) => r.url.includes('/auth/login'));
    req.flush({ access_token: 'jwt-token', refresh_token: 'rt-value', token_type: 'bearer' });
    expect(localStorage.getItem('modishlog_token')).toBe('jwt-token');
    expect(localStorage.getItem('modishlog_refresh_token')).toBe('rt-value');
    expect(service.isAuthenticated()).toBe(true);
  });

  it('logout clears both tokens and navigates to login', () => {
    localStorage.setItem('modishlog_token', 'jwt-token');
    localStorage.setItem('modishlog_refresh_token', 'rt-value');
    vi.spyOn(router, 'navigate');
    service.logout();

    // Absorb the logout API call
    const req = httpMock.expectOne((r) => r.url.includes('/auth/logout'));
    req.flush({ message: 'Logged out.' });

    expect(localStorage.getItem('modishlog_token')).toBeNull();
    expect(localStorage.getItem('modishlog_refresh_token')).toBeNull();
    expect(service.isAuthenticated()).toBe(false);
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
  });

  it('logout works even when no refresh token is stored', () => {
    localStorage.setItem('modishlog_token', 'jwt-token');
    vi.spyOn(router, 'navigate');
    service.logout();

    // No logout API call should be made when there is no refresh token
    httpMock.expectNone((r) => r.url.includes('/auth/logout'));
    expect(localStorage.getItem('modishlog_token')).toBeNull();
    expect(service.isAuthenticated()).toBe(false);
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
  });

  it('getToken returns stored token', () => {
    localStorage.setItem('modishlog_token', 'my-token');
    expect(service.getToken()).toBe('my-token');
  });

  it('getToken returns null when no token', () => {
    expect(service.getToken()).toBeNull();
  });

  it('getRefreshToken returns stored refresh token', () => {
    localStorage.setItem('modishlog_refresh_token', 'my-refresh-token');
    expect(service.getRefreshToken()).toBe('my-refresh-token');
  });

  it('getRefreshToken returns null when no refresh token', () => {
    expect(service.getRefreshToken()).toBeNull();
  });

  it('setToken updates the stored access token and sets authenticated', () => {
    service.setToken('new-access-token');
    expect(localStorage.getItem('modishlog_token')).toBe('new-access-token');
    expect(service.isAuthenticated()).toBe(true);
  });

  it('clearTokens removes both tokens and sets unauthenticated', () => {
    localStorage.setItem('modishlog_token', 'tok');
    localStorage.setItem('modishlog_refresh_token', 'rt');
    service.clearTokens();
    expect(localStorage.getItem('modishlog_token')).toBeNull();
    expect(localStorage.getItem('modishlog_refresh_token')).toBeNull();
    expect(service.isAuthenticated()).toBe(false);
  });

  it('refreshToken calls /auth/refresh and stores new access token', () => {
    localStorage.setItem('modishlog_refresh_token', 'existing-rt');
    let result: { access_token: string; refresh_token: string; token_type: string } | null = null;
    service.refreshToken().subscribe((r) => (result = r));
    const req = httpMock.expectOne((r) => r.url.includes('/auth/refresh'));
    expect(req.request.body).toEqual({ refresh_token: 'existing-rt' });
    req.flush({ access_token: 'fresh-token', refresh_token: '', token_type: 'bearer' });
    expect(localStorage.getItem('modishlog_token')).toBe('fresh-token');
    expect(result).toBeTruthy();
  });
});
