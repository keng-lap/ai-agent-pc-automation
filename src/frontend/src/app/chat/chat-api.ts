import { Injectable } from '@angular/core';
import { Observable, throwError } from 'rxjs';

export type UiLanguage = 'th' | 'en';

/**
 * T-202 intentionally ships a disconnected adapter. The real HTTP adapter
 * belongs to T-204; this placeholder never contacts the network.
 */
@Injectable({ providedIn: 'root' })
export class ChatApi {
  sendMessage(_message: string, _language: UiLanguage): Observable<unknown> {
    return throwError(() => ({ status: 0 }));
  }
}
