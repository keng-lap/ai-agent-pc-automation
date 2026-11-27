import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class RuntimeDiagnosticsState {
  private readonly enabledState = new BehaviorSubject(false);
  readonly workflowId = globalThis.crypto.randomUUID();

  get enabled(): boolean {
    return this.enabledState.value;
  }

  setEnabled(enabled: boolean): void {
    this.enabledState.next(enabled);
  }
}
