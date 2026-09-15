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
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        // A real 'login' route so router.navigate(['/login']) (called by
        // logout()) resolves instead of rejecting with NG04002.
        provideRouter([{ path: 'login', component: class {} as any }]),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
    sessionStorage.clear();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('isAuthenticated returns false when no token', () => {
    expect(service.isAuthenticated()).toBe(false);
  });

  it('isAuthenticated returns true when token exists', () => {
    service.setToken('test-token');
    expect(service.isAuthenticated()).toBe(true);
  });

  it('login stores both access_token and refresh_token', () => {
    service.login({ email: 'test@test.com', password: 'password123' }).subscribe();
    const req = httpMock.expectOne((r) => r.url.includes('/auth/login'));
    req.flush({ access_token: 'jwt-token', refresh_token: 'rt-value', token_type: 'bearer' });
    expect(service.getToken()).toBe('jwt-token');
    expect(service.getRefreshToken()).toBe('rt-value');
    expect(service.isAuthenticated()).toBe(true);
  });

  it('logout clears both tokens and navigates to login', () => {
    service.login({ email: 'test@test.com', password: 'password123' }).subscribe();
    httpMock
      .expectOne((r) => r.url.includes('/auth/login'))
      .flush({ access_token: 'jwt-token', refresh_token: 'rt-value', token_type: 'bearer' });

    vi.spyOn(router, 'navigate');
    service.logout();

    // logout() always notifies the backend (with the refresh token in the
    // body when one exists) so any HttpOnly server-side session is revoked.
    const req = httpMock.expectOne((r) => r.url.includes('/auth/logout'));
    req.flush({ message: 'Logged out.' });

    expect(service.getToken()).toBeNull();
    expect(service.getRefreshToken()).toBeNull();
    expect(service.isAuthenticated()).toBe(false);
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
  });

  it('logout still notifies the backend when no refresh token is stored', () => {
    service.setToken('jwt-token');
    vi.spyOn(router, 'navigate');
    service.logout();

    // logout() posts to /auth/logout regardless -- with an empty body when
    // there's no refresh token -- so any HttpOnly cookie session still gets
    // revoked server-side even if the client never had a refresh token.
    const req = httpMock.expectOne((r) => r.url.includes('/auth/logout'));
    expect(req.request.body).toEqual({});
    req.flush({ message: 'Logged out.' });

    expect(service.getToken()).toBeNull();
    expect(service.isAuthenticated()).toBe(false);
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
  });

  it('getToken returns stored token', () => {
    service.setToken('my-token');
    expect(service.getToken()).toBe('my-token');
  });

  it('getToken returns null when no token', () => {
    expect(service.getToken()).toBeNull();
  });

  it('getRefreshToken returns stored refresh token', () => {
    service.login({ email: 'test@test.com', password: 'password123' }).subscribe();
    httpMock
      .expectOne((r) => r.url.includes('/auth/login'))
      .flush({ access_token: 'a', refresh_token: 'my-refresh-token', token_type: 'bearer' });
    expect(service.getRefreshToken()).toBe('my-refresh-token');
  });

  it('getRefreshToken returns null when no refresh token', () => {
    expect(service.getRefreshToken()).toBeNull();
  });

  it('setToken updates the stored access token and sets authenticated', () => {
    service.setToken('new-access-token');
    expect(service.getToken()).toBe('new-access-token');
    expect(service.isAuthenticated()).toBe(true);
  });

  it('clearTokens removes both tokens and sets unauthenticated', () => {
    service.login({ email: 'test@test.com', password: 'password123' }).subscribe();
    httpMock
      .expectOne((r) => r.url.includes('/auth/login'))
      .flush({ access_token: 'tok', refresh_token: 'rt', token_type: 'bearer' });

    service.clearTokens();
    expect(service.getToken()).toBeNull();
    expect(service.getRefreshToken()).toBeNull();
    expect(service.isAuthenticated()).toBe(false);
  });

  it('register does not store any tokens (onboarding no longer auto-logs-in)', () => {
    service
      .register({
        full_name: 'Owner',
        email: 'owner@example.com',
        password: 'Str0ng!Pass#99',
        business_name: 'Test Corp',
        currency: 'NGN',
        timezone: 'Africa/Lagos',
        fiscal_year_start_month: 1,
        ndpr_consent: true,
      })
      .subscribe();
    const req = httpMock.expectOne((r) => r.url.includes('/auth/onboard'));
    req.flush({
      message: 'Check your email to verify your account before logging in.',
      user_id: 'u1',
      business_id: 'b1',
    });
    expect(service.getToken()).toBeNull();
    expect(service.isAuthenticated()).toBe(false);
  });

  it('verifyEmail posts the token to /auth/verify-email', () => {
    let result: { message: string } | null = null;
    service.verifyEmail('tok123').subscribe((r) => (result = r));
    const req = httpMock.expectOne((r) => r.url.includes('/auth/verify-email'));
    expect(req.request.body).toEqual({ token: 'tok123' });
    req.flush({ message: 'Email verified successfully.' });
    expect(result).toEqual({ message: 'Email verified successfully.' });
  });

  it('resendVerification posts the email to /auth/resend-verification', () => {
    let result: { message: string } | null = null;
    service.resendVerification('user@example.com').subscribe((r) => (result = r));
    const req = httpMock.expectOne((r) => r.url.includes('/auth/resend-verification'));
    expect(req.request.body).toEqual({ email: 'user@example.com' });
    req.flush({ message: 'If that email is registered and unverified, a link has been sent.' });
    expect(result).toBeTruthy();
  });

  it('refreshToken calls /auth/refresh and stores new access token', () => {
    service.login({ email: 'test@test.com', password: 'password123' }).subscribe();
    httpMock
      .expectOne((r) => r.url.includes('/auth/login'))
      .flush({ access_token: 'a', refresh_token: 'existing-rt', token_type: 'bearer' });

    let result: { access_token: string; refresh_token: string; token_type: string } | null = null;
    service.refreshToken().subscribe((r) => (result = r));
    const req = httpMock.expectOne((r) => r.url.includes('/auth/refresh'));
    expect(req.request.body).toEqual({ refresh_token: 'existing-rt' });
    req.flush({ access_token: 'fresh-token', refresh_token: '', token_type: 'bearer' });
    expect(service.getToken()).toBe('fresh-token');
    expect(result).toBeTruthy();
  });

  it('checkSession populates currentUser on success', () => {
    service.checkSession().subscribe();
    const req = httpMock.expectOne((r) => r.url.includes('/auth/me'));
    req.flush({ id: '1', email: 'owner@test.com', full_name: 'Owner', role: 'owner' });
    expect(service.currentUser()?.email).toBe('owner@test.com');
  });

  it('closeBusiness posts to /auth/business/close and updates currentUser.business_purge_at', () => {
    service.checkSession().subscribe();
    httpMock
      .expectOne((r) => r.url.includes('/auth/me'))
      .flush({ id: '1', email: 'owner@test.com', full_name: 'Owner', role: 'owner' });

    let result: { message: string; purge_at: string | null } | null = null;
    service.closeBusiness().subscribe((r) => (result = r));
    const req = httpMock.expectOne((r) => r.url.includes('/auth/business/close'));
    expect(req.request.method).toBe('POST');
    req.flush({ message: 'Deletion scheduled.', purge_at: '2026-10-15T00:00:00Z' });

    expect(result).toBeTruthy();
    expect(service.currentUser()?.business_purge_at).toBe('2026-10-15T00:00:00Z');
  });

  it('cancelBusinessDeletion posts to /auth/business/cancel-deletion and clears currentUser.business_purge_at', () => {
    service.checkSession().subscribe();
    httpMock
      .expectOne((r) => r.url.includes('/auth/me'))
      .flush({
        id: '1',
        email: 'owner@test.com',
        full_name: 'Owner',
        role: 'owner',
        business_deletion_requested_at: '2026-09-15T00:00:00Z',
        business_purge_at: '2026-10-15T00:00:00Z',
      });

    let result: { message: string; purge_at: string | null } | null = null;
    service.cancelBusinessDeletion().subscribe((r) => (result = r));
    const req = httpMock.expectOne((r) => r.url.includes('/auth/business/cancel-deletion'));
    expect(req.request.method).toBe('POST');
    req.flush({ message: 'Deletion cancelled.', purge_at: null });

    expect(result).toBeTruthy();
    expect(service.currentUser()?.business_purge_at).toBeNull();
    expect(service.currentUser()?.business_deletion_requested_at).toBeNull();
  });
});
