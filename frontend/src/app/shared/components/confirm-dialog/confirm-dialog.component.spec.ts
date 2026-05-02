import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ConfirmDialogComponent } from './confirm-dialog.component';

/** p-dialog renders footer template content into its own internal view tree,
 *  so we query document.body to reach buttons regardless of encapsulation. */
function findButton(label: string): HTMLButtonElement | undefined {
  return Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).find(
    (b) => b.textContent?.trim() === label,
  );
}

describe('ConfirmDialogComponent', () => {
  let fixture: ComponentFixture<ConfirmDialogComponent>;
  let component: ConfirmDialogComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConfirmDialogComponent, NoopAnimationsModule],
    }).compileComponents();
    fixture = TestBed.createComponent(ConfirmDialogComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('header', 'Delete Item');
    fixture.componentRef.setInput('message', 'Are you sure?');
    fixture.componentRef.setInput('visible', true);
    fixture.detectChanges();
  });

  afterEach(() => fixture.destroy());

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('uses "Delete" as the default confirmLabel', () => {
    expect(component.confirmLabel()).toBe('Delete');
  });

  it('accepts a custom confirmLabel', () => {
    fixture.componentRef.setInput('confirmLabel', 'Remove');
    fixture.detectChanges();
    expect(component.confirmLabel()).toBe('Remove');
  });

  it('emits confirmed when the confirm button is clicked', () => {
    let emitted = false;
    component.confirmed.subscribe(() => (emitted = true));

    const btn = findButton('Delete');
    expect(btn).toBeTruthy();
    btn!.click();

    expect(emitted).toBe(true);
  });

  it('emits cancelled when the cancel button is clicked', () => {
    let emitted = false;
    component.cancelled.subscribe(() => (emitted = true));

    const btn = findButton('Cancel');
    expect(btn).toBeTruthy();
    btn!.click();

    expect(emitted).toBe(true);
  });
});
