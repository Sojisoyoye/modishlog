import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AlertBannerComponent } from './alert-banner.component';

describe('AlertBannerComponent', () => {
  let fixture: ComponentFixture<AlertBannerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AlertBannerComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(AlertBannerComponent);
    fixture.componentRef.setInput('message', 'Test alert');
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('displays message', () => {
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('Test alert');
  });

  it('applies warning border for warning severity', () => {
    fixture.componentRef.setInput('severity', 'warning');
    fixture.detectChanges();
    expect(fixture.componentInstance.bannerClass()).toContain('warning');
  });

  it('emits dismissed event on close click', () => {
    let dismissed = false;
    fixture.componentInstance.dismissed.subscribe(() => (dismissed = true));
    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('button');
    btn.click();
    expect(dismissed).toBe(true);
  });
});
