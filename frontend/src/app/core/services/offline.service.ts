import { Injectable } from '@angular/core';
import { fromEvent, merge, Observable } from 'rxjs';
import { map, startWith } from 'rxjs/operators';
import { toSignal } from '@angular/core/rxjs-interop';

@Injectable({ providedIn: 'root' })
export class OfflineService {
  private readonly online$: Observable<boolean> = merge(
    fromEvent(window, 'online').pipe(map(() => true)),
    fromEvent(window, 'offline').pipe(map(() => false)),
  ).pipe(startWith(navigator.onLine));

  readonly isOnline = toSignal(this.online$, { initialValue: navigator.onLine });
  readonly isOffline = toSignal(
    this.online$.pipe(map(online => !online)),
    { initialValue: !navigator.onLine },
  );
}
