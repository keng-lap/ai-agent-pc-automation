import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type UiLanguage = 'th' | 'en';

/** Sends chat requests through the same-origin Angular development proxy. */
@Injectable({ providedIn: 'root' })
export class ChatApi {
  private readonly http = inject(HttpClient);
  sendMessage(message: string, language: UiLanguage): Observable<unknown> {
    return this.http.post<unknown>('/api/chat', { message, language });
  }
}
