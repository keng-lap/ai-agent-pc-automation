import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type UiLanguage = 'th' | 'en';
export interface GeminiStatus { configured: boolean; model: string; }
export interface DiagnosticsMode { enabled: boolean; }
export interface GeminiTestResult { connected: boolean; model: string; }
export interface ConversationMessage { role: 'user' | 'assistant'; text: string; }
export interface ConversationHistory { messages: ConversationMessage[]; }

export interface GeminiConversationResponse {
  schema_version: '1.0';
  message: string;
  intent: 'conversation.chat' | 'system.help' | 'software.install' | 'software.install_multiple' | 'software.remove' | 'environment.prepare' | 'environment.inspect';
  status: 'completed' | 'ready' | 'needs_clarification' | 'unsupported';
  data: {
    packages: Array<{
      name: string;
      version: string;
      purpose: string;
      suggested_source: string;
      suggested_method: string;
    }>;
    environment: {
      name: string;
      purpose: string;
      development_type: string;
      framework_version: string;
    } | null;
    checks: string[];
    notes: string[];
  };
  needs_clarification: boolean;
  clarification: string | null;
}

export interface GeminiChatResponse {
  request_id: string;
  gemini_response: GeminiConversationResponse;
  gemini_raw_json: string;
  provider: 'gemini';
  model: string;
  provider_connected: true;
}

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
  publisher_verification: 'NOT_CHECKED' | 'VERIFIED' | 'MISMATCH' | 'UNAVAILABLE';
  official_version: string | null;
  official_release_url: string | null;
  official_asset_sha256: string | null;
  status: 'CONDITIONAL';
  limitations: string[];
}

export interface SoftwareDiscoveryResponse {
  status: 'VERSION_REQUIRED' | 'CONDITIONAL' | 'SOURCE_MISMATCH' | 'SOURCE_CHECK_UNAVAILABLE';
  package_id: string;
  available_versions: string[];
  candidate: SoftwareInstallerCandidate | null;
  source: 'winget-community-repository';
}

export interface SoftwareInstallReadiness {
  platform_supported: boolean;
  authenticode_verification_available: boolean;
  publisher_identity_policy_available: boolean;
  publisher_trust_configured: boolean;
  publisher_trust_mode: 'WINDOWS_AUTHENTICODE_AND_WINGET_PUBLISHER_MATCH';
  real_install_enabled: boolean;
  real_install_release_package_id: string | null;
  real_install_release_version: string | null;
  real_install_release_expires_at: string | null;
  package_allowlist_enabled: boolean;
  supported_package_ids: string[];
  notice: 'NO_INSTALL_IS_STARTED_BY_THIS_ENDPOINT';
}

export interface SoftwareInstallProposalResponse {
  plan_id: string;
  evidence_id: string;
  package_id: string;
  package_name: string;
  publisher: string;
  version: string;
  architecture: 'x86' | 'x64' | 'arm64';
  scope: 'user';
  expires_at: string;
  notice: 'VERIFIED_PROPOSAL_REQUIRES_EXACT_ACTION_TOTP';
}

export interface SoftwareApprovalChallenge {
  plan_id: string;
  challenge_id: string;
  expires_at: number;
  package_id: string;
  package_name: string;
  publisher: string;
  version: string;
  architecture: 'x86' | 'x64' | 'arm64';
  scope: 'user';
  installer_type: 'exe' | 'msi' | 'msix' | 'appx';
  installer_silent_switch: string | null;
  installer_url: string;
  official_release_url: string | null;
  manifest_source_url: string;
  repository_commit: string;
  installer_sha256: string;
  manifest_sha256: string;
  signature_subject: string;
  signature_sha256: string;
  evidence_expires_at: string;
  approval_digest: string;
  notice: 'APPROVAL_REQUIRED_FOR_REAL_INSTALL';
}

export interface SoftwareInstallJobStatus {
  reservation_id: string;
  state: 'QUEUED' | 'CLAIMED' | 'RUNNING' | 'VERIFYING' | 'SUCCEEDED' | 'FAILED' | 'REBOOT_REQUIRED' | 'UNKNOWN';
  attempts: number;
  version: number;
  result_code: string | null;
  lease_expires_at: string | null;
}

export interface SoftwareApprovalResult {
  plan_id: string;
  approved: true;
  approval_digest: string;
  package_id: string;
  version: string;
  reservation_id: string;
  execution_state: 'QUEUED';
  notice: 'APPROVED_QUEUED_NOT_YET_EXECUTED';
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
    tool_id: 'software.install' | 'software.remove';
    mode: 'dry_run';
    live_checks_performed: false;
    expires_at: string;
    programs: PlanReviewProgram[];
  } | null;
  tool_result: { status: 'dry_run'; summary: string } | null;
  approved: boolean;
  questions: string[];
  notice: 'DRY_RUN_ONLY_NO_CHANGES_MADE' | 'PLAN_REVIEW_ONLY_NO_EXECUTION';
  refined_from_plan_id?: string | null;
  clarification?: string | null;
}

export type JobState =
  | 'QUEUED'
  | 'STARTING'
  | 'RUNNING'
  | 'VERIFYING'
  | 'REBOOT_REQUIRED'
  | 'CANCEL_REQUESTED'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELLED'
  | 'UNKNOWN';

export interface JobEvent {
  sequence: number;
  occurred_at: string;
  state: JobState;
  level: 'INFO' | 'WARN' | 'ERROR';
  message: string;
}

export interface JobSummary {
  job_id: string;
  tool_id: string;
  state: JobState;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  progress_message: string | null;
  result_code: string | null;
  reboot_required: boolean;
  recent_events: JobEvent[];
}

export interface JobListResponse {
  jobs: JobSummary[];
  checked_at: string;
}

@Injectable({ providedIn: 'root' })
export class ChatApi {
  private readonly http = inject(HttpClient);

  sendMessage(message: string, language: UiLanguage, conversationId: string): Observable<GeminiChatResponse> {
    return this.http.post<GeminiChatResponse>('/api/chat', {
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

  getSoftwareInstallReadiness(): Observable<SoftwareInstallReadiness> {
    return this.http.get<SoftwareInstallReadiness>('/api/software/install/readiness');
  }

  createSoftwareInstallProposal(
    packageId: string,
    version: string,
    architecture: 'x86' | 'x64' | 'arm64',
  ): Observable<SoftwareInstallProposalResponse> {
    return this.http.post<SoftwareInstallProposalResponse>('/api/software/install/proposals', {
      package_id: packageId,
      version,
      architecture,
    });
  }

  createSoftwareApprovalChallenge(
    planId: string,
    evidenceId: string,
  ): Observable<SoftwareApprovalChallenge> {
    return this.http.post<SoftwareApprovalChallenge>(
      `/api/plans/${encodeURIComponent(planId)}/software-approval`,
      { evidence_id: evidenceId },
    );
  }

  confirmSoftwareApproval(
    planId: string,
    challengeId: string,
    totpCode: string,
  ): Observable<SoftwareApprovalResult> {
    return this.http.post<SoftwareApprovalResult>(
      `/api/plans/${encodeURIComponent(planId)}/software-approval/confirm`,
      { challenge_id: challengeId, totp_code: totpCode },
    );
  }

  getSoftwareInstallJobForPlan(planId: string): Observable<SoftwareInstallJobStatus> {
    return this.http.get<SoftwareInstallJobStatus>(
      `/api/plans/${encodeURIComponent(planId)}/software-approval/reservation`,
    );
  }

  getSoftwareInstallJobStatus(reservationId: string): Observable<SoftwareInstallJobStatus> {
    return this.http.get<SoftwareInstallJobStatus>(
      `/api/software/install/jobs/${encodeURIComponent(reservationId)}`,
    );
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

  getJobs(limit = 25): Observable<JobListResponse> {
    return this.http.get<JobListResponse>('/api/jobs', { params: { limit } });
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

  getDiagnosticsMode(): Observable<DiagnosticsMode> {
    return this.http.get<DiagnosticsMode>('/api/diagnostics');
  }

  setDiagnosticsMode(enabled: boolean): Observable<DiagnosticsMode> {
    return this.http.put<DiagnosticsMode>('/api/diagnostics', { enabled });
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
  authenticator_storage_available?: boolean;
}

export interface GoogleLoginStart {
  authorization_url: string;
}

export interface AuthenticatorEnrollment {
  enrollment_id: string;
  qr_data_uri: string;
  expires_at: number;
}
