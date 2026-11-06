import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type UiLanguage = 'th' | 'en';
export interface GeminiStatus { configured: boolean; model: string; }
export interface GeminiTestResult { connected: boolean; model: string; }
export interface ConversationMessage { role: 'user' | 'assistant'; text: string; }
export interface ConversationHistory { messages: ConversationMessage[]; }

export interface PlanReviewProgram {
  order: number;
  program: string;
  version: string;
  purpose: string;
  reason: string;
  source: string;
  source_verification: 'NOT_CHECKED';
  dependencies: string[];
  dependencies_verification: 'NOT_CHECKED';
  disk_space_estimate: string | null;
  impact: string;
  status: 'PLANNED' | 'NEEDS_CLARIFICATION' | 'BLOCKED' | 'UNSUPPORTED';
}

export interface PlanReviewResponse {
  request: string;
  interpretation: { category: string; goal: string; target: string | null };
  task_plan: {
    steps: Array<{ order: number; kind: string; title: string; detail: string }>;
    prerequisites: Array<{ id: string; order: number; title: string; reason: string; status: string }>;
  };
  dry_run_plan: {
    plan_id: string;
    mode: 'dry_run';
    live_checks_performed: false;
    expires_at: string;
    programs: PlanReviewProgram[];
  } | null;
  tool_result: { status: 'dry_run'; summary: string } | null;
  questions: string[];
  notice: 'DRY_RUN_ONLY_NO_CHANGES_MADE';
}

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

  createPlan(request: string, language: UiLanguage): Observable<PlanReviewResponse> {
    return this.http.post<PlanReviewResponse>('/api/plans', { request, language });
  }

  getPlan(planId: string): Observable<PlanReviewResponse['dry_run_plan']> {
    return this.http.get<PlanReviewResponse['dry_run_plan']>(`/api/plans/${encodeURIComponent(planId)}`);
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
