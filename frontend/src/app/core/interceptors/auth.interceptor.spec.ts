import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideHttpClient, withInterceptors, HttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from '../services/auth.service';

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let authService: AuthService;
  let router: Router;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        // A real 'login' route so router.navigate(['/login']) (called on
        // refresh failure) resolves instead of rejecting with NG04002.
        provideRouter([{ path: 'login', component: class {} as any }]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    authService = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
    sessionStorage.clear();
  });

  it('adds Authorization header when token exists', () => {
    authService.setToken('test-jwt');
    http.get('/api/test').subscribe();
    const req = httpMock.expectOne('/api/test');
    expect(req.request.headers.get('Authorization')).toBe('Bearer test-jwt');
    req.flush({});
  });

  it('does not add header when no token', () => {
    http.get('/api/test').subscribe();
    const req = httpMock.expectOne('/api/test');
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({});
  });

  it('silently refreshes access token on 401 and retries original request', () => {
    authService.login({ email: 'test@test.com', password: 'password123' }).subscribe();
    httpMock
      .expectOne((r) => r.url.includes('/auth/login'))
      .flush({ access_token: 'expired-token', refresh_token: 'valid-refresh-token', token_type: 'bearer' });

    let result: unknown = null;
    http.get('/api/protected').subscribe((r) => (result = r));

    // First request fails with 401
    const firstReq = httpMock.expectOne('/api/protected');
    expect(firstReq.request.headers.get('Authorization')).toBe('Bearer expired-token');
    firstReq.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    // Interceptor should call /auth/refresh
    const refreshReq = httpMock.expectOne((r) => r.url.includes('/auth/refresh'));
    expect(refreshReq.request.method).toBe('POST');
    refreshReq.flush({ access_token: 'new-access-token', refresh_token: '', token_type: 'bearer' });

    // Original request is retried with new token
    const retryReq = httpMock.expectOne('/api/protected');
    expect(retryReq.request.headers.get('Authorization')).toBe('Bearer new-access-token');
    retryReq.flush({ data: 'success' });

    expect(result).toEqual({ data: 'success' });
  });

  it('redirects to login when refresh also fails', () => {
    authService.login({ email: 'test@test.com', password: 'password123' }).subscribe();
    httpMock
      .expectOne((r) => r.url.includes('/auth/login'))
      .flush({ access_token: 'expired-token', refresh_token: 'invalid-refresh-token', token_type: 'bearer' });

    let errorReceived = false;
    http.get('/api/protected').subscribe({ error: () => (errorReceived = true) });

    // First request fails with 401
    const firstReq = httpMock.expectOne('/api/protected');
    firstReq.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    // Refresh also fails
    const refreshReq = httpMock.expectOne((r) => r.url.includes('/auth/refresh'));
    refreshReq.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    expect(errorReceived).toBe(true);
    expect(authService.getToken()).toBeNull();
    expect(authService.getRefreshToken()).toBeNull();
  });

  it('does not attempt refresh when no refresh token is stored', () => {
    authService.setToken('expired-token');
    // No refresh token stored

    let errorReceived = false;
    http.get('/api/protected').subscribe({ error: () => (errorReceived = true) });

    const firstReq = httpMock.expectOne('/api/protected');
    firstReq.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    // No refresh call should be made
    httpMock.expectNone((r) => r.url.includes('/auth/refresh'));
    expect(errorReceived).toBe(true);
  });

  it('does not attempt refresh for /auth/login 401', () => {
    // Log in should fail without triggering refresh
    let errorReceived = false;
    http.post('/api/v1/auth/login', {}).subscribe({ error: () => (errorReceived = true) });

    const loginReq = httpMock.expectOne('/api/v1/auth/login');
    loginReq.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    httpMock.expectNone((r) => r.url.includes('/auth/refresh'));
    expect(errorReceived).toBe(true);
  });

  it('does not redirect to /login when /auth/me 401s with no refresh token (session probe)', () => {
    // /auth/me is how public pages like the landing page quietly check
    // "am I logged in?" (AuthService.checkSession(), task #269). A logged-
    // out visitor's 401 here must not force-navigate them off whatever
    // public page they're on -- that's the whole point of checkSession()
    // catching the error into `null` instead of propagating it.
    const navigateSpy = vi.spyOn(router, 'navigate');

    let errorReceived = false;
    http.get('/api/v1/auth/me').subscribe({ error: () => (errorReceived = true) });

    const req = httpMock.expectOne('/api/v1/auth/me');
    req.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    httpMock.expectNone((r) => r.url.includes('/auth/refresh'));
    expect(errorReceived).toBe(true);
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it('does not redirect to /login when /auth/me 401s and refresh also fails', () => {
    authService.login({ email: 'test@test.com', password: 'password123' }).subscribe();
    httpMock
      .expectOne((r) => r.url.includes('/auth/login'))
      .flush({ access_token: 'expired-token', refresh_token: 'invalid-refresh-token', token_type: 'bearer' });

    const navigateSpy = vi.spyOn(router, 'navigate');
    let errorReceived = false;
    http.get('/api/v1/auth/me').subscribe({ error: () => (errorReceived = true) });

    httpMock.expectOne('/api/v1/auth/me').flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });
    httpMock
      .expectOne((r) => r.url.includes('/auth/refresh'))
      .flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    expect(errorReceived).toBe(true);
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it('still attempts silent refresh for /auth/me when a refresh token is present', () => {
    // Session restoration on page reload (authGuard's fallback path) relies
    // on checkSession() transparently benefiting from the same silent-
    // refresh-and-retry every other call gets -- only the final "give up
    // and redirect" step is special-cased for /auth/me, not the refresh
    // attempt itself.
    authService.login({ email: 'test@test.com', password: 'password123' }).subscribe();
    httpMock
      .expectOne((r) => r.url.includes('/auth/login'))
      .flush({ access_token: 'expired-token', refresh_token: 'valid-refresh-token', token_type: 'bearer' });

    let result: unknown = null;
    http.get('/api/v1/auth/me').subscribe((r) => (result = r));

    httpMock.expectOne('/api/v1/auth/me').flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    const refreshReq = httpMock.expectOne((r) => r.url.includes('/auth/refresh'));
    refreshReq.flush({ access_token: 'new-access-token', refresh_token: '', token_type: 'bearer' });

    const retryReq = httpMock.expectOne('/api/v1/auth/me');
    expect(retryReq.request.headers.get('Authorization')).toBe('Bearer new-access-token');
    retryReq.flush({ id: '1', email: 'test@test.com', full_name: 'Test', role: 'owner' });

    expect(result).toEqual({ id: '1', email: 'test@test.com', full_name: 'Test', role: 'owner' });
  });
});
