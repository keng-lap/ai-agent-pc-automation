import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type UiLanguage = 'th' | 'en';
export interface GeminiStatus { configured: boolean; model: string; }
export interface GeminiTestResult { connected: boolean; model: string; }

@Injectable({ providedIn: 'root' })
export class ChatApi {
  private readonly http = inject(HttpClient);

  sendMessage(message: string, language: UiLanguage): Observable<unknown> {
    return this.http.post<unknown>('/api/chat', { message, language });
  }

  getGeminiStatus(): Observable<GeminiStatus> {
    return this.http.get<GeminiStatus>('/api/settings/gemini');
  }

  saveGeminiKey(apiKey: string): Observable<GeminiStatus> {
    return this.http.put<GeminiStatus>('/api/settings/gemini', { api_key: apiKey });
  }

  testGeminiConnection(): Observable<GeminiTestResult> {
    return this.http.post<GeminiTestResult>('/api/settings/gemini/test', {});
  }
}
