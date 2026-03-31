import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { LoginPageComponent } from './login-page.component';

describe('LoginPageComponent', () => {
  let fixture: ComponentFixture<LoginPageComponent>;
  let component: LoginPageComponent;
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [LoginPageComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    fixture = TestBed.createComponent(LoginPageComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    fixture.detectChanges();
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('displays sign in form', () => {
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('Sign In');
    expect(el.querySelector('input[type="email"]')).toBeTruthy();
    expect(el.querySelector('input[type="password"]')).toBeTruthy();
  });

  it('does not submit when fields are empty', () => {
    component.onLogin();
    httpMock.expectNone(() => true);
  });

  it('navigates on successful login', () => {
    vi.spyOn(router, 'navigate');
    component.email = 'test@test.com';
    component.password = 'password123';
    component.onLogin();
    const req = httpMock.expectOne((r) => r.url.includes('/auth/login'));
    req.flush({ access_token: 'tok', refresh_token: 'rt', token_type: 'bearer' });
    expect(router.navigate).toHaveBeenCalledWith(['/']);
  });

  it('shows error message on 401', () => {
    component.email = 'test@test.com';
    component.password = 'wrong';
    component.onLogin();
    const req = httpMock.expectOne((r) => r.url.includes('/auth/login'));
    req.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });
    expect(component.errorMessage()).toContain('Invalid');
  });

  it('shows lockout message on 429', () => {
    component.email = 'test@test.com';
    component.password = 'password';
    component.onLogin();
    const req = httpMock.expectOne((r) => r.url.includes('/auth/login'));
    req.flush('Too Many', { status: 429, statusText: 'Too Many Requests' });
    expect(component.errorMessage()).toContain('locked');
  });
});
