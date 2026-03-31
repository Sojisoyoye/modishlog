import { ComponentFixture, TestBed } from '@angular/core/testing';
import { StatusBadgeComponent } from './status-badge.component';

describe('StatusBadgeComponent', () => {
  let fixture: ComponentFixture<StatusBadgeComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [StatusBadgeComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(StatusBadgeComponent);
    fixture.componentRef.setInput('label', 'Active');
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('displays label text', () => {
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('Active');
  });

  it('applies success class for success status', () => {
    fixture.componentRef.setInput('status', 'success');
    fixture.detectChanges();
    expect(fixture.componentInstance.badgeClass()).toContain('green');
  });

  it('applies danger class for danger status', () => {
    fixture.componentRef.setInput('status', 'danger');
    fixture.detectChanges();
    expect(fixture.componentInstance.badgeClass()).toContain('red');
  });

  it('defaults to neutral class', () => {
    expect(fixture.componentInstance.badgeClass()).toContain('gray');
  });
});
