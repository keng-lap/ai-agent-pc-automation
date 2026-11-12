import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type UiLanguage = 'th' | 'en';
export interface GeminiStatus { configured: boolean; model: string; }
export interface GeminiTestResult { connected: boolean; model: string; }
export interface ConversationMessage { role: 'user' | 'assistant'; text: string; }
export interface ConversationHistory { messages: ConversationMessage[]; }

export interface SoftwareCatalogCandidate {
  package_id: string;
  name: string;
  moniker: string | null;
  latest_version: string;
}

export interface SoftwareCatalogSearchResponse {
  status: 'CATALOG_MATCHES';
  source: 'microsoft-winget-source2';
  source_version: string;
  source_sha256: string;
  checked_at: string;
  candidates: SoftwareCatalogCandidate[];
}

export interface SoftwareInstallerCandidate {
  package_id: string;
  package_name: string;
  publisher: string;
  version: string;
  architecture: 'x86' | 'x64' | 'arm64';
  scope: 'user';
  installer_type: string;
  installer_url: string;
  installer_domain: string;
  installer_sha256: string;
  manifest_sha256: string;
  repository_commit: string;
  manifest_source_url: string;
  checked_at: string;
  status: 'CONDITIONAL';
  limitations: string[];
}

export interface SoftwareDiscoveryResponse {
  status: 'VERSION_REQUIRED' | 'CONDITIONAL';
  package_id: string;
  available_versions: string[];
  candidate: SoftwareInstallerCandidate | null;
  source: 'winget-community-repository';
}

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

export interface PlanApprovalResponse { plan_id: string; approved: true; tool_result: { status: 'dry_run'; summary: string }; notice: 'DRY_RUN_ONLY_NO_CHANGES_MADE'; }
export interface StepUpChallenge { challenge_id: string; plan_id: string; expires_at: number; }

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
  approved: boolean;
  questions: string[];
  notice: 'DRY_RUN_ONLY_NO_CHANGES_MADE';
  refined_from_plan_id?: string | null;
  clarification?: string | null;
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

  searchSoftwareCatalog(query: string, limit = 10): Observable<SoftwareCatalogSearchResponse> {
    return this.http.post<SoftwareCatalogSearchResponse>('/api/software/discovery/search', {
      query,
      limit,
    });
  }

  discoverSoftware(
    packageId: string,
    version: string | null,
    architecture: 'x86' | 'x64' | 'arm64' = 'x64',
  ): Observable<SoftwareDiscoveryResponse> {
    return this.http.post<SoftwareDiscoveryResponse>('/api/software/discovery', {
      package_id: packageId,
      version,
      architecture,
    });
  }

  createPlan(request: string, language: UiLanguage): Observable<PlanReviewResponse> {
    return this.http.post<PlanReviewResponse>('/api/plans', { request, language });
  }

  getPlan(planId: string): Observable<PlanReviewResponse['dry_run_plan']> {
    return this.http.get<PlanReviewResponse['dry_run_plan']>(`/api/plans/${encodeURIComponent(planId)}`);
  }

  createPlanStepUpChallenge(planId: string): Observable<StepUpChallenge> {
    return this.http.post<StepUpChallenge>(
      `/api/plans/${encodeURIComponent(planId)}/step-up`,
      {},
    );
  }

  approvePlan(planId: string, challengeId: string, totpCode: string): Observable<PlanApprovalResponse> {
    return this.http.post<PlanApprovalResponse>(
      `/api/plans/${encodeURIComponent(planId)}/approve`,
      { challenge_id: challengeId, totp_code: totpCode },
    );
  }

  refinePlan(
    planId: string,
    request: string,
    clarification: string,
    language: UiLanguage,
  ): Observable<PlanReviewResponse> {
    return this.http.post<PlanReviewResponse>(
      `/api/plans/${encodeURIComponent(planId)}/refine`,
      { request, clarification, language },
    );
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

  getAuthSession(): Observable<AuthSession> {
    return this.http.get<AuthSession>('/api/auth/session');
  }

  startGoogleLogin(): Observable<GoogleLoginStart> {
    return this.http.get<GoogleLoginStart>('/api/auth/google/start');
  }

  beginAuthenticatorEnrollment(): Observable<AuthenticatorEnrollment> {
    return this.http.post<AuthenticatorEnrollment>('/api/authenticator/enrollment', {});
  }

  confirmAuthenticatorEnrollment(enrollmentId: string, code: string): Observable<{ enrolled: boolean }> {
    return this.http.post<{ enrolled: boolean }>('/api/authenticator/enrollment/confirm', {
      enrollment_id: enrollmentId,
      code,
    });
  }

  logout(): Observable<{ logged_out: boolean }> {
    return this.http.post<{ logged_out: boolean }>('/api/auth/logout', {});
  }
}


export interface AuthSession {
  enabled: boolean;
  authenticated: boolean;
  authenticator_enrolled: boolean;
}

export interface GoogleLoginStart {
  authorization_url: string;
}

export interface AuthenticatorEnrollment {
  enrollment_id: string;
  qr_data_uri: string;
  expires_at: number;
}
