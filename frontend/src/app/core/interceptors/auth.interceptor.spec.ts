import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors, HttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from '../services/auth.service';

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let authService: AuthService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    authService = TestBed.inject(AuthService);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('adds Authorization header when token exists', () => {
    localStorage.setItem('modishlog_token', 'test-jwt');
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
    localStorage.setItem('modishlog_token', 'expired-token');
    localStorage.setItem('modishlog_refresh_token', 'valid-refresh-token');

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
    localStorage.setItem('modishlog_token', 'expired-token');
    localStorage.setItem('modishlog_refresh_token', 'invalid-refresh-token');

    let errorReceived = false;
    http.get('/api/protected').subscribe({ error: () => (errorReceived = true) });

    // First request fails with 401
    const firstReq = httpMock.expectOne('/api/protected');
    firstReq.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    // Refresh also fails
    const refreshReq = httpMock.expectOne((r) => r.url.includes('/auth/refresh'));
    refreshReq.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

    expect(errorReceived).toBe(true);
    expect(localStorage.getItem('modishlog_token')).toBeNull();
    expect(localStorage.getItem('modishlog_refresh_token')).toBeNull();
  });

  it('does not attempt refresh when no refresh token is stored', () => {
    localStorage.setItem('modishlog_token', 'expired-token');
    // No refresh token in localStorage

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
});
