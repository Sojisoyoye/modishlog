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

  it('emits dismissed on × button click when no confirmLabel', () => {
    let dismissed = false;
    fixture.componentInstance.dismissed.subscribe(() => (dismissed = true));
    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('button');
    btn.click();
    expect(dismissed).toBe(true);
  });

  describe('with confirmLabel set', () => {
    beforeEach(() => {
      fixture.componentRef.setInput('confirmLabel', 'Delete');
      fixture.detectChanges();
    });

    it('renders Cancel and confirm buttons instead of ×', () => {
      const el: HTMLElement = fixture.nativeElement;
      const buttons = el.querySelectorAll<HTMLButtonElement>('button');
      const labels = Array.from(buttons).map((b) => b.textContent?.trim());
      expect(labels).toContain('Cancel');
      expect(labels).toContain('Delete');
      // × icon button should not be present
      expect(el.querySelector('.pi-times')).toBeNull();
    });

    it('uses custom cancelLabel when provided', () => {
      fixture.componentRef.setInput('cancelLabel', 'No thanks');
      fixture.detectChanges();
      const el: HTMLElement = fixture.nativeElement;
      expect(el.textContent).toContain('No thanks');
    });

    it('emits dismissed when Cancel is clicked', () => {
      let dismissed = false;
      fixture.componentInstance.dismissed.subscribe(() => (dismissed = true));
      const buttons = fixture.nativeElement.querySelectorAll<HTMLButtonElement>('button');
      const cancelBtn = Array.from(buttons).find((b) => b.textContent?.trim() === 'Cancel');
      cancelBtn!.click();
      expect(dismissed).toBe(true);
    });

    it('emits confirmed when confirm button is clicked', () => {
      let confirmed = false;
      fixture.componentInstance.confirmed.subscribe(() => (confirmed = true));
      const buttons = fixture.nativeElement.querySelectorAll<HTMLButtonElement>('button');
      const confirmBtn = Array.from(buttons).find((b) => b.textContent?.trim() === 'Delete');
      confirmBtn!.click();
      expect(confirmed).toBe(true);
    });
  });
});
