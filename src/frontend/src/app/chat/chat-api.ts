import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type UiLanguage = 'th' | 'en';
export interface GeminiStatus { configured: boolean; model: string; }
export interface GeminiTestResult { connected: boolean; model: string; }
export interface ConversationMessage { role: 'user' | 'assistant'; text: string; }
export interface ConversationHistory { messages: ConversationMessage[]; }

@Injectable({ providedIn: 'root' })
export class ChatApi {
  private readonly http = inject(HttpClient);

  sendMessage(message: string, language: UiLanguage, conversationId: string): Observable<unknown> {
    return this.http.post<unknown>('/api/chat', {
      conversation_id: conversationId,
      message,
      language,
    });
  }

  getConversation(conversationId: string): Observable<ConversationHistory> {
    return this.http.get<ConversationHistory>(`/api/chat/${encodeURIComponent(conversationId)}`);
  }

  clearConversation(conversationId: string): Observable<void> {
    return this.http.delete<void>(`/api/chat/${encodeURIComponent(conversationId)}`, { body: {} });
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
