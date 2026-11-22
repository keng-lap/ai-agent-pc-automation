import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Observable, Subject, of, throwError } from 'rxjs';
import { map } from 'rxjs/operators';
import { TimeoutError } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './app';
import { ChatApi, GeminiChatResponse, PlanReviewResponse, SoftwareCatalogSearchResponse, SoftwareDiscoveryResponse, UiLanguage } from './chat/chat-api';

function geminiResponse(message: string): GeminiChatResponse {
  const contract: GeminiChatResponse['gemini_response'] = {
    schema_version: '1.0',
    message,
    intent: 'conversation.chat',
    status: 'completed',
    data: { packages: [], environment: null, checks: [], notes: [] },
    needs_clarification: false,
    clarification: null,
  };
  return {
    request_id: '123e4567-e89b-42d3-a456-426614174000',
    gemini_response: contract,
    gemini_raw_json: JSON.stringify(contract),
    provider: 'gemini',
    model: 'test-model',
    provider_connected: true,
  };
}

class FakeChatApi {
  calls: Array<{ message: string; language: UiLanguage; conversationId: string }> = [];
  catalogCalls: string[] = [];
  discoveryCalls: Array<{ packageId: string; version: string | null; architecture: string }> = [];
  catalogResponder: (query: string) => Observable<SoftwareCatalogSearchResponse> = () => of({
    status: 'CATALOG_MATCHES',
    source: 'microsoft-winget-source2',
    source_version: '1.0.0.0',
    source_sha256: 'a'.repeat(64),
    checked_at: '2026-11-12T00:00:00Z',
    candidates: [
      { package_id: 'DBeaver.DBeaver.Community', name: 'DBeaver Community Edition', moniker: 'dbeaver', latest_version: '25.3.0' },
      { package_id: 'DBeaverCorp.DBeaverEnterpriseEdition', name: 'DBeaver Enterprise Edition', moniker: null, latest_version: '25.3.0' },
    ],
  });
  readiness = {
    platform_supported: true,
    authenticode_verification_available: true,
    publisher_trust_configured: false,
    supported_package_ids: [] as string[],
    notice: 'NO_INSTALL_IS_STARTED_BY_THIS_ENDPOINT' as const,
  };
  proposalCalls: Array<{ packageId: string; version: string; architecture: string }> = [];
  approvalChallengeCalls: Array<{ planId: string; evidenceId: string }> = [];
  softwareApprovalCalls: Array<{ planId: string; challengeId: string; code: string }> = [];
  jobStatusCalls: string[] = [];
  discoveryResponder: (packageId: string, version: string | null) => Observable<SoftwareDiscoveryResponse> = (packageId, version) => of(
    version === null
      ? {
        status: 'VERSION_REQUIRED',
        package_id: packageId,
        available_versions: ['25.2.0', '25.3.0'],
        candidate: null,
        source: 'winget-community-repository',
      }
      : {
        status: 'CONDITIONAL',
        package_id: packageId,
        available_versions: ['25.2.0', '25.3.0'],
        candidate: {
          package_id: packageId,
          package_name: 'DBeaver Community Edition',
          publisher: 'DBeaver Corp',
          version,
          architecture: 'x64',
          scope: 'user',
          installer_type: 'exe',
          installer_url: 'https://github.com/dbeaver/dbeaver/releases/download/' + version + '/dbeaver-ce-' + version + '-windows-x86_64.exe',
          installer_domain: 'github.com',
          installer_sha256: 'b'.repeat(64),
          manifest_sha256: 'c'.repeat(64),
          repository_commit: 'd'.repeat(40),
          manifest_source_url: 'https://github.com/microsoft/winget-pkgs/tree/main',
          checked_at: '2026-11-12T00:00:00Z',
          publisher_verification: 'VERIFIED',
          official_version: version,
          official_release_url: 'https://github.com/dbeaver/dbeaver/releases/tag/' + version,
          official_asset_sha256: 'b'.repeat(64),
          status: 'CONDITIONAL',
          limitations: ['installer_authenticode_signature_not_yet_verified'],
        },
        source: 'winget-community-repository',
      },
  );
  restoredConversationIds: string[] = [];
  clearedConversationIds: string[] = [];
  refineCalls: Array<{ planId: string; request: string; clarification: string; language: UiLanguage }> = [];
  approvalCalls: string[] = [];
  stepUpCalls: string[] = [];
  authSession: {
    enabled: boolean;
    authenticated: boolean;
    authenticator_enrolled: boolean;
    authenticator_storage_available?: boolean;
  } = { enabled: false, authenticated: false, authenticator_enrolled: false };
  refineResponder: (planId: string, request: string, clarification: string, language: UiLanguage) => Observable<PlanReviewResponse> = (_planId, request, clarification) => of({
    request,
    interpretation: { category: 'development_task', goal: request, target: 'Java' },
    task_plan: { steps: [], prerequisites: [] },
    dry_run_plan: null,
    tool_result: null,
    questions: [],
    approved: false,
    notice: 'DRY_RUN_ONLY_NO_CHANGES_MADE',
    refined_from_plan_id: 'a'.repeat(32),
    clarification,
  });
  approveResponder: (planId: string) => Observable<{ plan_id: string; approved: true; tool_result: { status: 'dry_run'; summary: string }; notice: 'DRY_RUN_ONLY_NO_CHANGES_MADE' }> = (planId) => of({
    plan_id: planId,
    approved: true,
    tool_result: { status: 'dry_run', summary: 'Dry run only; no changes made.' },
    notice: 'DRY_RUN_ONLY_NO_CHANGES_MADE',
  });
  history: { messages: Array<{ role: 'user' | 'assistant'; text: string }> } = { messages: [] };
  historyError: unknown;
  clearError: unknown;
  configured = false;
  testError: unknown;
  responder: (message: string, language: UiLanguage) => Observable<unknown> = () => of({ reply: 'Mock reply' });
  planResponder: (message: string, language: UiLanguage) => Observable<PlanReviewResponse> = (message) => of({
    request: message,
    interpretation: { category: 'general_task', goal: message, target: null },
    task_plan: { steps: [], prerequisites: [] },
    dry_run_plan: null,
    tool_result: null,
    questions: [],
    approved: false,
    notice: 'DRY_RUN_ONLY_NO_CHANGES_MADE',
  });

  getAuthSession(): Observable<{ enabled: boolean; authenticated: boolean; authenticator_enrolled: boolean }> {
    return of(this.authSession);
  }

  startGoogleLogin(): Observable<{ authorization_url: string }> {
    return of({ authorization_url: 'https://accounts.google.com/test' });
  }

  beginAuthenticatorEnrollment(): Observable<{ enrollment_id: string; qr_data_uri: string; expires_at: number }> {
    return of({ enrollment_id: 'a'.repeat(32), qr_data_uri: 'data:image/svg+xml;base64,PHN2Zy8+', expires_at: 0 });
  }

  confirmAuthenticatorEnrollment(): Observable<{ enrolled: boolean }> {
    return of({ enrolled: true });
  }

  logout(): Observable<{ logged_out: boolean }> {
    return of({ logged_out: true });
  }

  searchSoftwareCatalog(query: string): Observable<SoftwareCatalogSearchResponse> {
    this.catalogCalls.push(query);
    return this.catalogResponder(query);
  }

  discoverSoftware(packageId: string, version: string | null, architecture: 'x86' | 'x64' | 'arm64' = 'x64'): Observable<SoftwareDiscoveryResponse> {
    this.discoveryCalls.push({ packageId, version, architecture });
    return this.discoveryResponder(packageId, version);
  }

  getSoftwareInstallReadiness(): Observable<typeof this.readiness> {
    return of(this.readiness);
  }

  createSoftwareInstallProposal(packageId: string, version: string, architecture: string): Observable<unknown> {
    this.proposalCalls.push({ packageId, version, architecture });
    return of({
      plan_id: 'f'.repeat(32),
      evidence_id: 'e'.repeat(32),
      package_id: packageId,
      package_name: 'DBeaver Community Edition',
      publisher: 'DBeaver Corp',
      version,
      architecture,
      scope: 'user',
      expires_at: '2026-11-22T00:10:00Z',
      notice: 'VERIFIED_PROPOSAL_REQUIRES_EXACT_ACTION_TOTP',
    });
  }

  createSoftwareApprovalChallenge(planId: string, evidenceId: string): Observable<unknown> {
    this.approvalChallengeCalls.push({ planId, evidenceId });
    return of({
      plan_id: planId,
      challenge_id: 'c'.repeat(32),
      expires_at: 1_800_000_120,
      package_id: 'DBeaver.DBeaver.Community',
      package_name: 'DBeaver Community Edition',
      publisher: 'DBeaver Corp',
      version: '25.3.0',
      architecture: 'x64',
      scope: 'user',
      installer_type: 'exe',
      installer_url: 'https://github.com/dbeaver/dbeaver/releases/download/25.3.0/dbeaver.exe',
      official_release_url: 'https://github.com/dbeaver/dbeaver/releases/tag/25.3.0',
      manifest_source_url: 'https://github.com/microsoft/winget-pkgs/tree/main',
      repository_commit: 'd'.repeat(40),
      installer_sha256: 'b'.repeat(64),
      manifest_sha256: 'c'.repeat(64),
      signature_subject: 'CN=DBeaver Corporation',
      signature_sha256: 'd'.repeat(64),
      evidence_expires_at: '2026-11-22T00:10:00Z',
      approval_digest: 'a'.repeat(64),
      notice: 'APPROVAL_REQUIRED_FOR_REAL_INSTALL',
    });
  }

  confirmSoftwareApproval(planId: string, challengeId: string, code: string): Observable<unknown> {
    this.softwareApprovalCalls.push({ planId, challengeId, code });
    return of({
      plan_id: planId,
      approved: true,
      approval_digest: 'a'.repeat(64),
      package_id: 'DBeaver.DBeaver.Community',
      version: '25.3.0',
      reservation_id: 'a'.repeat(32),
      execution_state: 'QUEUED',
      notice: 'APPROVED_QUEUED_NOT_YET_EXECUTED',
    });
  }
  getSoftwareInstallJobStatus(reservationId: string): Observable<unknown> {
    this.jobStatusCalls.push(reservationId);
    return of({
      reservation_id: reservationId,
      state: 'SUCCEEDED',
      attempts: 1,
      version: 3,
      result_code: 'EXACT_PACKAGE_VERIFIED',
      lease_expires_at: null,
    });
  }

  sendMessage(message: string, language: UiLanguage, conversationId: string): Observable<GeminiChatResponse> {
    this.calls.push({ message, language, conversationId });
    return this.responder(message, language).pipe(map((value) => {
      if (typeof value !== 'object' || value === null) {
        return value as GeminiChatResponse;
      }
      if ('gemini_response' in value) return value as GeminiChatResponse;
      if (!('reply' in value) || typeof (value as { reply: unknown }).reply !== 'string') {
        return value as GeminiChatResponse;
      }
      const reply = (value as { reply: string }).reply;
      const isJava = /java/i.test(message);
      const isDotNet = /\.net|dotnet/i.test(message);
      const isEnvironment = /เตรียมเครื่องพัฒนา|prepare.*environment|development environment/i.test(message);
      const isInstall = /install|ติดตั้ง/i.test(message);
      const intent: GeminiChatResponse['gemini_response']['intent'] = isEnvironment
        ? 'environment.prepare'
        : isInstall ? 'software.install' : 'conversation.chat';
      const packages = isEnvironment
        ? isDotNet
          ? [
            { name: '.NET SDK', version: 'latest LTS', purpose: 'Build .NET applications', suggested_source: 'Microsoft', suggested_method: 'WinGet if verified' },
            { name: 'Visual Studio Code', version: 'latest', purpose: 'Code editor', suggested_source: 'Microsoft', suggested_method: 'WinGet if verified' },
            { name: 'C# Dev Kit', version: 'latest', purpose: 'C# development extension', suggested_source: 'VS Code Marketplace', suggested_method: 'Marketplace extension install after verification' },
          ]
          : [
            { name: 'JDK', version: '21 LTS', purpose: 'Java compiler and runtime', suggested_source: 'OpenJDK vendor', suggested_method: 'WinGet if verified' },
            { name: 'Visual Studio Code', version: 'latest', purpose: 'Code editor', suggested_source: 'Microsoft', suggested_method: 'WinGet if verified' },
          ]
        : isInstall
          ? [{ name: message.replace(/^.*?(?:install(?:ation)?|ติดตั้ง)\s*(?:of\s+)?/i, '').trim() || 'Requested software', version: 'latest', purpose: 'User-requested software', suggested_source: 'Official vendor source', suggested_method: 'WinGet if verified' }]
          : [];
      const contract = {
        schema_version: '1.0' as const,
        message: reply,
        intent,
        status: intent === 'conversation.chat' ? 'completed' as const : 'ready' as const,
        data: {
          packages,
          environment: isEnvironment ? {
            name: isDotNet ? '.NET development' : isJava ? 'Java development' : 'Development environment',
            purpose: 'Prepare tools to build and test applications',
            development_type: isDotNet ? ' .NET' : isJava ? 'Java' : 'General',
            framework_version: 'LTS',
          } : null,
          checks: [],
          notes: [],
        },
        needs_clarification: false,
        clarification: null,
      };
      return {
        request_id: '123e4567-e89b-42d3-a456-426614174000',
        gemini_response: contract,
        gemini_raw_json: JSON.stringify(contract),
        provider: 'gemini' as const,
        model: 'test-model',
        provider_connected: true as const,
      };
    }));
  }

  createPlan(message: string, language: UiLanguage): Observable<PlanReviewResponse> {
    return this.planResponder(message, language);
  }

  createPlanStepUpChallenge(planId: string): Observable<{ challenge_id: string; plan_id: string; expires_at: number }> {
    this.stepUpCalls.push(planId);
    return of({ challenge_id: 'b'.repeat(32), plan_id: planId, expires_at: 1_800_000_120 });
  }

  approvePlan(planId: string, _challengeId: string, _totpCode: string): Observable<{ plan_id: string; approved: true; tool_result: { status: 'dry_run'; summary: string }; notice: 'DRY_RUN_ONLY_NO_CHANGES_MADE' }> {
    this.approvalCalls.push(planId);
    return this.approveResponder(planId);
  }

  refinePlan(planId: string, request: string, clarification: string, language: UiLanguage): Observable<PlanReviewResponse> {
    this.refineCalls.push({ planId, request, clarification, language });
    return this.refineResponder(planId, request, clarification, language);
  }

  getConversation(conversationId: string): Observable<unknown> {
    this.restoredConversationIds.push(conversationId);
    if (this.historyError !== undefined) return throwError(() => this.historyError);
    return of(this.history);
  }

  clearConversation(conversationId: string): Observable<void> {
    this.clearedConversationIds.push(conversationId);
    if (this.clearError !== undefined) return throwError(() => this.clearError);
    return of(undefined);
  }

  getGeminiStatus(): Observable<{ configured: boolean; model: string }> {
    return of({ configured: this.configured, model: 'gemini-3.1-flash-lite' });
  }

  saveGeminiKey(_apiKey: string): Observable<{ configured: boolean; model: string }> {
    this.configured = true;
    return of({ configured: true, model: 'gemini-3.1-flash-lite' });
  }

  testGeminiConnection(): Observable<{ connected: boolean; model: string }> {
    if (this.testError !== undefined) return throwError(() => this.testError);
    return of({ connected: true, model: 'gemini-3.1-flash-lite' });
  }
}

describe('App baseline', () => {
  beforeEach(async () => {
    localStorage.clear();
    sessionStorage.clear();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatApi, useClass: FakeChatApi }],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('should render title', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('AI Agent PC Automation');
  });
});

function validChatResponse(message: string): GeminiChatResponse {
  const contract: GeminiChatResponse['gemini_response'] = {
    schema_version: '1.0',
    message,
    intent: 'conversation.chat',
    status: 'completed',
    data: { packages: [], environment: null, checks: [], notes: [] },
    needs_clarification: false,
    clarification: null,
  };
  return {
    request_id: '123e4567-e89b-42d3-a456-426614174000',
    gemini_response: contract,
    gemini_raw_json: JSON.stringify(contract),
    provider: 'gemini',
    model: 'test-model',
    provider_connected: true,
  };
}

describe('App chat UI (T-202)', () => {
  let fixture!: ComponentFixture<App>;
  let api: FakeChatApi;
  let httpTestingController: HttpTestingController | null = null;

  async function render(): Promise<void> {
    fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    if (httpTestingController) {
      const authRequest = httpTestingController.expectOne('/api/auth/session');
      authRequest.flush({ enabled: false, authenticated: false, authenticator_enrolled: false });
      await fixture.whenStable();
      fixture.detectChanges();
      const statusRequest = httpTestingController.expectOne('/api/settings/gemini');
      statusRequest.flush({ configured: false, model: 'gemini-3.1-flash-lite' });
    }
    await fixture.whenStable();
    fixture.detectChanges();
  }

  function inputText(value: string): HTMLTextAreaElement {
    const input = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    input.value = value;
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    return input;
  }

  function sendButton(): HTMLButtonElement {
    return fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement;
  }

  function languageButton(label: 'ไทย' | 'EN'): HTMLButtonElement {
    const buttons = Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[];
    const match = buttons.find((btn) => btn.textContent?.trim() === label);
    if (!match) {
      throw new Error(`Button "${label}" not found`);
    }
    return match;
  }

  function send(value = 'hello'): void {
    inputText(value);
    sendButton().click();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    localStorage.clear();
    sessionStorage.clear();
    api = new FakeChatApi();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatApi, useValue: api }],
    }).compileComponents();
  });

  afterEach(() => {
    fixture?.destroy();
    httpTestingController?.verify();
    httpTestingController = null;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });



  it('routes AI-interpreted install intents to WinGet discovery instead of legacy Dry Run', async () => {
    await render();
    api.planResponder = (request) => of({
      request,
      interpretation: { category: 'software_install', goal: request, target: 'Google Chrome' },
      task_plan: { steps: [], prerequisites: [] },
      dry_run_plan: null,
      tool_result: null,
      approved: false,
      questions: [],
      notice: 'PLAN_REVIEW_ONLY_NO_EXECUTION',
    });

    send('Prepare installation of Google Chrome');
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.calls.map((item) => item.message)).toEqual(['Prepare installation of Google Chrome']);
    expect(api.catalogCalls).toEqual(['Google Chrome']);
    expect(fixture.nativeElement.textContent).toContain('ค้นหาจาก Microsoft WinGet Catalog');
    expect(fixture.nativeElement.textContent).not.toContain('ผลการจำลอง');
    expect(fixture.nativeElement.textContent).not.toContain('ยืนยันตัวตนเพื่ออนุมัติ');
    expect(api.stepUpCalls).toEqual([]);
    expect(api.approvalCalls).toEqual([]);
  });

  it('uses Gemini to understand install requests while Backend independently resolves Package IDs', async () => {
    await render();

    send('ติดตั้ง DBeaver Community Edition');
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.catalogCalls).toEqual(['DBeaver Community Edition']);
    expect(api.calls.map((item) => item.message)).toEqual(['ติดตั้ง DBeaver Community Edition']);
    expect(fixture.nativeElement.textContent).toContain('DBeaver Community Edition');
    expect(fixture.nativeElement.textContent).toContain('DBeaver.DBeaver.Community');
    expect(fixture.nativeElement.textContent).toContain('DBeaverCorp.DBeaverEnterpriseEdition');

    const community = Array.from(
      fixture.nativeElement.querySelectorAll('.software-candidate') as NodeListOf<HTMLButtonElement>,
    ).find((button) => button.textContent?.includes('DBeaver.DBeaver.Community'));
    if (!community) throw new Error('Community package candidate was not rendered');
    community.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.discoveryCalls).toEqual([
      { packageId: 'DBeaver.DBeaver.Community', version: null, architecture: 'x64' },
    ]);
    expect(fixture.nativeElement.textContent).toContain('เลือกเวอร์ชันที่ต้องการ');
    expect(fixture.nativeElement.textContent).toContain('25.3.0');

    const version = Array.from(
      fixture.nativeElement.querySelectorAll('.software-version') as NodeListOf<HTMLButtonElement>,
    ).find((button) => button.textContent?.trim() === '25.3.0');
    if (!version) throw new Error('Exact version choice was not rendered');
    version.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.discoveryCalls[1]).toEqual({
      packageId: 'DBeaver.DBeaver.Community',
      version: '25.3.0',
      architecture: 'x64',
    });
    expect(fixture.nativeElement.textContent).toContain('CONDITIONAL');
    expect(fixture.nativeElement.textContent).toContain('DBeaver Corp');
    expect(fixture.nativeElement.textContent).toContain('github.com');
    expect(fixture.nativeElement.textContent).toContain('ยังไม่ใช่หลักฐานอนุญาตติดตั้ง');
    expect(fixture.nativeElement.textContent).toContain('installer_authenticode_signature_not_yet_verified');
    expect(fixture.nativeElement.textContent).not.toContain('ยืนยันตัวตนเพื่ออนุมัติ');
  });

  it('queues a verified real install only after exact TOTP approval', async () => {
    api.authSession = { enabled: true, authenticated: true, authenticator_enrolled: true };
    api.readiness.publisher_trust_configured = true;
    api.readiness.supported_package_ids = ['DBeaver.DBeaver.Community'];
    await render();

    send('install DBeaver Community Edition');
    await fixture.whenStable();
    fixture.detectChanges();
    const community = Array.from(
      fixture.nativeElement.querySelectorAll('.software-candidate') as NodeListOf<HTMLButtonElement>,
    ).find((button) => button.textContent?.includes('DBeaver.DBeaver.Community'));
    if (!community) throw new Error('Community package candidate was not rendered');
    community.click();
    await fixture.whenStable();
    fixture.detectChanges();

    const version = Array.from(
      fixture.nativeElement.querySelectorAll('.software-version') as NodeListOf<HTMLButtonElement>,
    ).find((button) => button.textContent?.trim() === '25.3.0');
    if (!version) throw new Error('Exact version choice was not rendered');
    version.click();
    await fixture.whenStable();
    fixture.detectChanges();

    const prepare = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>,
    ).find((button) => button.textContent?.includes('ตรวจสอบไฟล์และเตรียม Approval'));
    if (!prepare) throw new Error('Real install preparation button was not rendered');
    prepare.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.proposalCalls).toEqual([{
      packageId: 'DBeaver.DBeaver.Community',
      version: '25.3.0',
      architecture: 'x64',
    }]);
    expect(fixture.nativeElement.textContent).toContain('DBeaver Community Edition');

    const requestApproval = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>,
    ).find((button) => button.textContent?.includes('ยืนยันตัวตนและขออนุมัติ'));
    if (!requestApproval) throw new Error('Exact-action approval button was not rendered');
    requestApproval.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.approvalChallengeCalls).toEqual([{ planId: 'f'.repeat(32), evidenceId: 'e'.repeat(32) }]);
    const codeInput = fixture.nativeElement.querySelector('input[id^="install-totp-"]') as HTMLInputElement;
    expect(codeInput).not.toBeNull();
    codeInput.value = '123456';
    codeInput.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    const confirm = Array.from(
      fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>,
    ).find((button) => button.textContent?.includes('อนุมัติและเข้าคิวติดตั้งจริง'));
    if (!confirm) throw new Error('Real install approval button was not rendered');
    confirm.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.softwareApprovalCalls).toEqual([{
      planId: 'f'.repeat(32),
      challengeId: 'c'.repeat(32),
      code: '123456',
    }]);
    expect(fixture.nativeElement.textContent).toContain('อนุมัติแล้วและเข้าคิวติดตั้งจริง');
    expect(fixture.nativeElement.textContent).toContain('a'.repeat(32));
    expect(api.jobStatusCalls).toEqual(['a'.repeat(32)]);
    expect(fixture.nativeElement.textContent).toContain('ติดตั้งและตรวจสอบ Package ผ่านแล้ว');
  });

  it('blocks a WinGet manifest version that differs from the vendor official release', async () => {
    api.catalogResponder = () => of({
      status: 'CATALOG_MATCHES',
      source: 'microsoft-winget-source2',
      source_version: '1.0.0.0',
      source_sha256: 'a'.repeat(64),
      checked_at: '2026-11-12T00:00:00Z',
      candidates: [
        { package_id: 'DBeaver.DBeaver.Community', name: 'DBeaver Community Edition', moniker: 'dbeaver', latest_version: '7.3.5' },
      ],
    });
    api.discoveryResponder = (packageId, version) => of(version === null
      ? {
        status: 'VERSION_REQUIRED',
        package_id: packageId,
        available_versions: ['7.3.5'],
        candidate: null,
        source: 'winget-community-repository',
      }
      : {
      status: 'SOURCE_MISMATCH',
      package_id: packageId,
      available_versions: ['7.3.5'],
      source: 'winget-community-repository',
      candidate: {
        package_id: packageId,
        package_name: 'DBeaver Community Edition',
        publisher: 'DBeaver Corp',
        version: version ?? '7.3.5',
        architecture: 'x64',
        scope: 'user',
        installer_type: 'exe',
        installer_url: 'https://github.com/dbeaver/dbeaver/releases/download/7.3.5/dbeaver-ce-7.3.5-windows-x86_64.exe',
        installer_domain: 'github.com',
        installer_sha256: 'b'.repeat(64),
        manifest_sha256: 'c'.repeat(64),
        repository_commit: 'd'.repeat(40),
        manifest_source_url: 'https://github.com/microsoft/winget-pkgs/tree/main',
        checked_at: '2026-11-12T00:00:00Z',
        publisher_verification: 'MISMATCH',
        official_version: '26.2.4',
        official_release_url: 'https://github.com/dbeaver/dbeaver/releases/tag/26.2.4',
        official_asset_sha256: 'e'.repeat(64),
        status: 'CONDITIONAL',
        limitations: ['publisher_official_release_mismatch', 'installer_authenticode_signature_not_yet_verified'],
      },
    });
    await render();

    send('ติดตั้ง DBeaver Community Edition');
    await fixture.whenStable();
    fixture.detectChanges();
    const packageButton = fixture.nativeElement.querySelector('.software-candidate') as HTMLButtonElement;
    packageButton.click();
    await fixture.whenStable();
    fixture.detectChanges();
    const versionButton = Array.from(
      fixture.nativeElement.querySelectorAll('.software-version') as NodeListOf<HTMLButtonElement>,
    ).find((button) => button.textContent?.trim() === '7.3.5');
    if (!versionButton) throw new Error('Stale manifest version was not rendered');
    versionButton.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('SOURCE MISMATCH');
    expect(fixture.nativeElement.textContent).toContain('7.3.5');
    expect(fixture.nativeElement.textContent).toContain('26.2.4');
    expect(fixture.nativeElement.textContent).toContain('บล็อก: Manifest ไม่ตรงกับ Release ทางการ');
    expect(fixture.nativeElement.textContent).not.toContain('ยืนยันตัวตนเพื่ออนุมัติ');
  });

  it('F-01: starts in Thai with the empty hint and disabled Send', async () => {
    await render();
    expect(fixture.nativeElement.textContent).toContain('เชื่อมต่อ Gemini เพื่อสนทนาได้โดยตรง');
    expect(sendButton().disabled).toBe(true);
    expect(document.documentElement.lang).toBe('th');
    expect(fixture.nativeElement.querySelector('textarea')?.getAttribute('placeholder')).toContain('พิมพ์');
  });

  it('F-02: whitespace-only input keeps Send disabled', async () => {
    await render();
    inputText('   \n  ');
    expect(sendButton().disabled).toBe(true);
  });

  it('shows a safe Gemini quota reason when the connection test fails', async () => {
    api.configured = true;
    api.testError = { status: 502, error: { detail: { code: 'quota_exceeded' } } };
    await render();
    const buttons = Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[];
    buttons.find((button) => button.textContent?.includes('ทดสอบการเชื่อมต่อ'))?.click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('โควตา Gemini เต็มหรือเกินขีดจำกัด');
  });

  it('shows only the safe error type for an unclassified Gemini failure', async () => {
    await render();
    api.responder = () => throwError(() => ({
      status: 502,
      error: { detail: { code: 'unknown', error_type: 'RuntimeError' } },
    }));
    send();
    expect(fixture.nativeElement.textContent).toContain('(RuntimeError)');
    expect(fixture.nativeElement.textContent).not.toContain('sensitive');
  });

  it('shows the safe SDK error type when Gemini reports an SDK runtime error', async () => {
    await render();
    api.responder = () => throwError(() => ({
      status: 502,
      error: { detail: {
        code: 'sdk_runtime_error',
        error_type: 'RuntimeError',
        stage: 'provider_request',
        trace: 'models.generate_content',
      } },
    }));
    send();
    expect(fixture.nativeElement.textContent).toContain('Gemini SDK เกิดข้อผิดพลาดภายใน');
    expect(fixture.nativeElement.textContent).toContain('(RuntimeError · provider_request · models.generate_content)');
  });

  it('F-03/F-04: sends trimmed text, shows user and Agent entries, and clears the composer', async () => {
    await render();
    send('  hello Agent  ');
    expect(api.calls).toHaveLength(1);
    expect(api.calls[0]).toMatchObject({ message: 'hello Agent', language: 'th' });
    expect(fixture.nativeElement.textContent).toContain('hello Agent');
    expect(fixture.nativeElement.textContent).toContain('Mock reply');
    expect(fixture.nativeElement.textContent).toContain('คุณ');
    expect(fixture.nativeElement.querySelector('textarea')?.value).toBe('');
    expect(sendButton().disabled).toBe(true);
  });

  it('F-05: ignores a second send while a request is pending', async () => {
    const response = new Subject<unknown>();
    api.responder = () => response;
    await render();
    send('first');
    expect(fixture.nativeElement.textContent).toContain('กำลังรอคำตอบจาก Agent');
    expect(sendButton().disabled).toBe(true);
    sendButton().click();
    expect(api.calls).toHaveLength(1);
    response.next({ reply: 'done' });
    response.complete();
    fixture.detectChanges();
  });

  it('F-06: Enter sends; Shift+Enter and IME composition do not send', async () => {
    await render();
    const input = inputText('line');
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true }));
    expect(api.calls).toHaveLength(0);
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true }));
    expect(api.calls).toHaveLength(0);
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    fixture.detectChanges();
    expect(api.calls).toHaveLength(1);
  });

  it('F-07: enforces the 2000-character input limit', async () => {
    await render();
    const input = inputText('x'.repeat(2001));
    expect(input.value).toHaveLength(2000);
    expect(fixture.nativeElement.textContent).toContain('2000/2000');
    sendButton().click();
    expect(api.calls[0]?.message).toHaveLength(2000);
  });

  it('F-08/F-16: maps every specified backend, proxy, malformed-body and timeout error class', async () => {
    const cases: Array<{ error: unknown; thai: string; english: string }> = [
      { error: { status: 0 }, thai: 'เชื่อมต่อ Backend ไม่ได้', english: 'Cannot reach the backend' },
      { error: { status: 400 }, thai: 'Backend ปฏิเสธคำขอ', english: 'security check' },
      { error: { status: 403 }, thai: 'Backend ปฏิเสธคำขอ', english: 'security check' },
      { error: { status: 415 }, thai: 'Backend ปฏิเสธคำขอ', english: 'security check' },
      { error: { status: 413 }, thai: 'ข้อความมีขนาดใหญ่เกินไป', english: 'message is too large' },
      { error: { status: 422 }, thai: 'ไม่รับข้อความนี้', english: '1 to 2000 characters' },
      { error: { status: 500, detail: 'internal' }, thai: 'Backend พบข้อผิดพลาดภายใน', english: 'internal error' },
      { error: { status: 501, error: { detail: 'internal' } }, thai: 'Backend', english: 'internal error' },
      { error: { status: 500, error: { detail: 42 } }, thai: 'Backend', english: 'Cannot reach the backend' },
      { error: { status: 502 }, thai: 'Backend พบข้อผิดพลาดภายใน', english: 'internal error' },
      { error: { status: 502, error: { detail: { code: 'key_or_access' } } }, thai: 'Gemini ปฏิเสธ API Key', english: 'Gemini rejected the API key' },
      { error: { status: 502, error: { detail: { code: 'quota_exceeded' } } }, thai: 'โควตา Gemini เต็ม', english: 'Gemini quota is exhausted' },
      { error: { status: 502, error: { detail: { code: 'model_unavailable' } } }, thai: 'ไม่พบโมเดล Gemini', english: 'configured Gemini model is unavailable' },
      { error: { status: 502, error: { detail: { code: 'provider_unavailable' } } }, thai: 'บริการ Gemini ขัดข้อง', english: 'Gemini is temporarily unavailable' },
      { error: { status: 409 }, thai: 'กรุณาตั้งค่า Gemini API Key', english: 'configure your Gemini API key' },
      { error: { status: 503 }, thai: 'เชื่อมต่อ Backend ไม่ได้', english: 'Cannot reach the backend' },
      { error: { status: 504 }, thai: 'เชื่อมต่อ Backend ไม่ได้', english: 'Cannot reach the backend' },
      { error: { status: 500 }, thai: 'เชื่อมต่อ Backend ไม่ได้', english: 'Cannot reach the backend' },
      { error: { status: 404 }, thai: 'เกิดข้อผิดพลาดที่ไม่คาดคิด (HTTP 404)', english: 'Unexpected error (HTTP 404)' },
    ];
    await render();
    for (const item of cases) {
      api.responder = () => throwError(() => item.error);
      send('test');
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain('ข้อผิดพลาด');
      expect(fixture.nativeElement.textContent).toContain(item.thai);
      expect(sendButton().disabled).toBe(true);
      languageButton('EN').click();
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain('Error');
      expect(fixture.nativeElement.textContent).toContain(item.english);
      languageButton('ไทย').click();
      fixture.detectChanges();
      inputText('next');
      expect(sendButton().disabled).toBe(false);
    }
  });

  it('F-16: an HTTP 200 parse error is an unexpected response', async () => {
    await render();
    api.responder = () => throwError(() => ({ status: 200, error: 'invalid JSON' }));
    send('malformed');
    expect(fixture.nativeElement.textContent).not.toContain('Cannot reach the backend');
    languageButton('EN').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('unexpected response');
  });

  it('F-09: timeout shows MSG-07 and allows a new send', async () => {
    await render();
    api.responder = () => throwError(() => new TimeoutError());
    send('slow');
    expect(fixture.nativeElement.textContent).toContain('ข้อผิดพลาด');
    expect(fixture.nativeElement.textContent).toContain('Agent ไม่ตอบกลับภายในเวลาที่กำหนด');
    languageButton('EN').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Error');
    expect(fixture.nativeElement.textContent).toContain('Agent did not respond in time');
    languageButton('ไทย').click();
    fixture.detectChanges();
    send('again');
    expect(api.calls).toHaveLength(2);
  });

  it('F-10 / ST-24: renders user and reply HTML as literal text', async () => {
    api.responder = () => of({ reply: '<img src=x onerror=alert(1)>' });
    await render();
    send('<script>alert(1)</script>');
    const log = fixture.nativeElement.querySelector('[role="log"]') as HTMLElement;
    expect(log.querySelector('script')).toBeNull();
    expect(log.querySelector('img')).toBeNull();
    expect(log.textContent).toContain('<script>alert(1)</script>');
    expect(log.textContent).toContain('<img src=x onerror=alert(1)>');
  });

  it('F-11/F-12: preserves order, scrolls the log, and exposes accessible labels', async () => {
    await render();
    send('first');
    send('second');
    const log = fixture.nativeElement.querySelector('[role="log"]') as HTMLElement;
    const text = log.textContent ?? '';
    expect(text.indexOf('first')).toBeLessThan(text.indexOf('second'));
    expect(log.getAttribute('aria-live')).toBe('polite');
    expect(fixture.nativeElement.querySelector('label[for="message-input"]')).not.toBeNull();
    expect(log.scrollTop).toBe(log.scrollHeight);
  });

  it('stores only the conversation ID in session storage, never chat messages', async () => {
    await render();
    send('private test message');
    expect(localStorage.length).toBe(0);
    expect(localStorage.getItem('private test message')).toBeNull();
    expect(sessionStorage.length).toBe(1);
    expect(sessionStorage.getItem('private test message')).toBeNull();
    expect(sessionStorage.getItem('ai-agent-pc-automation.conversation-id')).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  });

  it('restores backend history after refresh using only the session-stored ID', async () => {
    const conversationId = '123e4567-e89b-42d3-a456-426614174000';
    sessionStorage.setItem('ai-agent-pc-automation.conversation-id', conversationId);
    api.history = {
      messages: [
        { role: 'user', text: 'previous question' },
        { role: 'assistant', text: 'previous answer' },
      ],
    };
    await render();
    expect(api.restoredConversationIds).toEqual([conversationId]);
    expect(fixture.nativeElement.textContent).toContain('previous question');
    expect(fixture.nativeElement.textContent).toContain('previous answer');
    expect(sessionStorage.length).toBe(1);
  });

  it('starts a new conversation and clears the previous backend history', async () => {
    await render();
    send('old message');
    const oldConversationId = sessionStorage.getItem('ai-agent-pc-automation.conversation-id');
    const newChatButton = fixture.nativeElement.querySelector('.new-chat-button') as HTMLButtonElement;
    newChatButton.click();
    fixture.detectChanges();
    expect(api.clearedConversationIds).toEqual([oldConversationId]);
    expect(fixture.nativeElement.textContent).not.toContain('old message');
    expect(sessionStorage.getItem('ai-agent-pc-automation.conversation-id')).not.toBe(oldConversationId);
  });

  it('replaces an expired conversation ID after backend restart', async () => {
    const expiredId = '123e4567-e89b-42d3-a456-426614174000';
    sessionStorage.setItem('ai-agent-pc-automation.conversation-id', expiredId);
    api.historyError = { status: 404 };
    await render();
    expect(fixture.nativeElement.textContent).toContain('บริบทเดิมหมดอายุ');
    expect(sessionStorage.getItem('ai-agent-pc-automation.conversation-id')).not.toBe(expiredId);
  });

  it('F-15: the HTTP ChatApi posts the message, language and conversation ID', async () => {
    await TestBed.resetTestingModule();
    localStorage.clear();
    sessionStorage.clear();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    httpTestingController = TestBed.inject(HttpTestingController);
    await render();
    languageButton('EN').click();
    fixture.detectChanges();
    send('hello');
    const request = httpTestingController.expectOne('/api/chat');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      conversation_id: sessionStorage.getItem('ai-agent-pc-automation.conversation-id'),
      message: 'hello',
      language: 'en',
    });
    request.flush(validChatResponse('Mock reply'));
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Mock reply');
    httpTestingController.expectNone('/api/plans');
    expect(fixture.nativeElement.textContent).toContain('Mock reply');

    const conversationId = sessionStorage.getItem('ai-agent-pc-automation.conversation-id')!;
    TestBed.inject(ChatApi).getConversation(conversationId).subscribe();
    const historyRequest = httpTestingController.expectOne(`/api/chat/${conversationId}`);
    expect(historyRequest.request.method).toBe('GET');
    historyRequest.flush({ messages: [] });
    TestBed.inject(ChatApi).clearConversation(conversationId).subscribe();
    const clearRequest = httpTestingController.expectOne(`/api/chat/${conversationId}`);
    expect(clearRequest.request.method).toBe('DELETE');
    expect(clearRequest.request.body).toEqual({});
    clearRequest.flush(null);
  });

  it('F-23: the request keeps the language selected when Send was pressed', async () => {
    await TestBed.resetTestingModule();
    localStorage.clear();
    sessionStorage.clear();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    httpTestingController = TestBed.inject(HttpTestingController);
    await render();
    send('Thai request');
    const thaiRequest = httpTestingController.expectOne('/api/chat');
    expect(thaiRequest.request.body).toMatchObject({ message: 'Thai request', language: 'th' });
    languageButton('EN').click();
    fixture.detectChanges();
    thaiRequest.flush(validChatResponse('Thai reply'));
    fixture.detectChanges();
    httpTestingController.expectNone('/api/plans');
    send('English request');
    const englishRequest = httpTestingController.expectOne('/api/chat');
    expect(englishRequest.request.body).toMatchObject({ message: 'English request', language: 'en' });
    englishRequest.flush(validChatResponse('English reply'));
    fixture.detectChanges();
    httpTestingController.expectNone('/api/plans');
  });

  it('F-17/F-18: language switch updates the UI and document language', async () => {
    await render();
    languageButton('EN').click();
    fixture.detectChanges();
    expect(document.documentElement.lang).toBe('en');
    expect(fixture.nativeElement.textContent).toContain('Start a conversation');
    expect(fixture.nativeElement.querySelector('textarea')?.getAttribute('placeholder')).toBe('Type your message...');
    expect(sendButton().textContent).toContain('Send');
    languageButton('ไทย').click();
    fixture.detectChanges();
    expect(document.documentElement.lang).toBe('th');
    expect(fixture.nativeElement.textContent).toContain('เริ่มต้นบทสนทนา');
  });

  it('F-19: saves and restores only the selected language', async () => {
    await render();
    languageButton('EN').click();
    fixture.detectChanges();
    expect(localStorage.length).toBe(1);
    expect(localStorage.getItem('ai-agent-pc-automation.language')).toBe('en');
    fixture.destroy();
    await render();
    expect(document.documentElement.lang).toBe('en');
    expect(fixture.nativeElement.textContent).toContain('Start a conversation');
  });

  it('F-20: invalid or unavailable saved language falls back to Thai without breaking the UI', async () => {
    localStorage.setItem('ai-agent-pc-automation.language', 'fr');
    await render();
    expect(document.documentElement.lang).toBe('th');
    fixture.destroy();
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    await render();
    expect(fixture.nativeElement.textContent).toContain('เริ่มต้นบทสนทนา');
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    languageButton('EN').click();
    fixture.detectChanges();
    expect(document.documentElement.lang).toBe('en');
  });

  it('F-21: every MSG-01 to MSG-11 text and entry labels exist in Thai and English', async () => {
    await render();
    // MSG-01
    expect(fixture.nativeElement.textContent).toContain('เชื่อมต่อ Gemini เพื่อสนทนาได้โดยตรง');
    languageButton('EN').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Chat with Gemini directly');
    languageButton('ไทย').click();
    fixture.detectChanges();

    // MSG-02
    const pendingSubject = new Subject<unknown>();
    api.responder = () => pendingSubject;
    send('pending test');
    expect(fixture.nativeElement.textContent).toContain('กำลังรอคำตอบจาก Agent');
    languageButton('EN').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Waiting for the Agent');
    languageButton('ไทย').click();
    fixture.detectChanges();
    pendingSubject.next({ reply: 'ok' });
    pendingSubject.complete();
    fixture.detectChanges();

    // MSG-03 to MSG-11
    const cases: Array<{ error: unknown; thai: string; english: string }> = [
      { error: { status: 0 }, thai: 'เชื่อมต่อ Backend ไม่ได้', english: 'Cannot reach the backend' },
      { error: { status: 422 }, thai: 'ไม่รับข้อความนี้', english: '1 to 2000 characters' },
      { error: { status: 403 }, thai: 'Backend ปฏิเสธคำขอ', english: 'security check' },
      { error: { status: 500, detail: 'x' }, thai: 'Backend พบข้อผิดพลาดภายใน', english: 'internal error' },
      { error: new TimeoutError(), thai: 'Agent ไม่ตอบกลับ', english: 'Agent did not respond in time' },
      { error: { status: 200, malformed: true }, thai: 'รูปแบบที่ไม่คาดคิด', english: 'unexpected response' },
      { error: { status: 413 }, thai: 'ข้อความมีขนาดใหญ่เกินไป', english: 'message is too large' },
      { error: { status: 404 }, thai: 'HTTP 404', english: 'HTTP 404' },
      { error: { status: 409 }, thai: 'กรุณาตั้งค่า Gemini API Key', english: 'configure your Gemini API key' },
      { error: { status: 502 }, thai: 'Backend พบข้อผิดพลาดภายใน', english: 'internal error' },
    ];
    for (const item of cases) {
      api.responder = () => item.error instanceof TimeoutError ? throwError(() => item.error) : item.error && typeof item.error === 'object' && 'malformed' in item.error ? of(item.error) : throwError(() => item.error);
      send('error case');
      expect(fixture.nativeElement.textContent).toContain(item.thai);
      languageButton('EN').click();
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain(item.english);
      languageButton('ไทย').click();
      fixture.detectChanges();
      inputText('again');
    }
  });

  it('F-22: changing language relabels errors but does not alter existing messages or replies', async () => {
    api.responder = () => of({ reply: 'ตอบกลับภาษาไทย' });
    await render();
    send('ข้อความของฉัน');
    api.responder = () => throwError(() => ({ status: 403 }));
    send('อีกข้อความ');
    languageButton('EN').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Error');
    expect(fixture.nativeElement.textContent).toContain('ข้อความของฉัน');
    expect(fixture.nativeElement.textContent).toContain('ตอบกลับภาษาไทย');
    expect(fixture.nativeElement.textContent).toContain('security check');
  });


});


describe('Structured Agent response (T-404)', () => {
  it('shows the Gemini JSON response as escaped text and never treats it as approval', async () => {
    localStorage.clear();
    sessionStorage.clear();
    const api = new FakeChatApi();
    api.responder = () => of({ reply: 'Hello <script>alert(1)</script>' });
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatApi, useValue: api }],
    }).compileComponents();
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    await fixture.whenStable();
    const input = fixture.nativeElement.querySelector('#message-input') as HTMLTextAreaElement;
    input.value = 'สวัสดี';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();

    const view = fixture.nativeElement as HTMLElement;
    expect(view.textContent).toContain('Hello <script>alert(1)</script>');
    expect(view.querySelector('script')).toBeNull();
    expect(view.textContent).toContain('ดู JSON ที่ Gemini ส่งกลับมา');
    expect(view.textContent).toContain('conversation.chat');
    const log = view.querySelector('[role="log"]') as HTMLElement;
    expect(log.textContent).not.toMatch(/อนุมัติ|ติดตั้งจริง/);
    fixture.destroy();
  });
  it('renders Gemini clarification using the same universal response envelope', async () => {
    localStorage.clear();
    sessionStorage.clear();
    const api = new FakeChatApi();
    const contract = {
      schema_version: '1.0' as const,
      message: 'ต้องการทราบว่าจะพัฒนา .NET Web API หรือ Desktop Application?',
      intent: 'environment.prepare' as const,
      status: 'needs_clarification' as const,
      data: {
        packages: [{ name: '.NET SDK', version: 'LTS', purpose: 'Build .NET apps', suggested_source: 'Microsoft', suggested_method: 'WinGet after backend verification' }],
        environment: { name: '.NET development', purpose: 'Prepare tools', development_type: 'Unspecified', framework_version: 'LTS' },
        checks: [],
        notes: [],
      },
      needs_clarification: true,
      clarification: 'ต้องการพัฒนา .NET Web API หรือ Desktop Application?',
    };
    api.responder = () => of({
      request_id: '123e4567-e89b-42d3-a456-426614174000',
      gemini_response: contract,
      gemini_raw_json: JSON.stringify(contract),
      provider: 'gemini',
      model: 'test-model',
      provider_connected: true,
    });
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatApi, useValue: api }],
    }).compileComponents();
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    await fixture.whenStable();
    const input = fixture.nativeElement.querySelector('#message-input') as HTMLTextAreaElement;
    input.value = 'เตรียมเครื่องพัฒนา .NET';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain(contract.message);
    expect(fixture.nativeElement.textContent).toContain('.NET SDK');
    expect(fixture.nativeElement.textContent).toContain('Request ID');
    expect(fixture.nativeElement.textContent).toContain('ดู JSON ที่ Gemini ส่งกลับมา');
    expect(fixture.nativeElement.textContent).not.toContain('Dry Run');
    fixture.destroy();
  });
  it('shows a multi-package .NET environment proposal without starting installation', async () => {
    localStorage.clear();
    sessionStorage.clear();
    const api = new FakeChatApi();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatApi, useValue: api }],
    }).compileComponents();
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    await fixture.whenStable();
    const input = fixture.nativeElement.querySelector('#message-input') as HTMLTextAreaElement;
    input.value = 'เตรียมเครื่องพัฒนาด้วย .NET';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();

    const view = fixture.nativeElement as HTMLElement;
    expect(view.textContent).toContain('.NET SDK');
    expect(view.textContent).toContain('Visual Studio Code');
    expect(view.textContent).toContain('C# Dev Kit');
    expect(view.textContent).toContain('VS Code Marketplace');
    expect(view.textContent).toContain('WinGet if verified');
    expect(view.textContent).toContain('ดู JSON ที่ Gemini ส่งกลับมา');
    expect(api.catalogCalls).toEqual([]);
    expect(api.proposalCalls).toEqual([]);
    expect(view.querySelector('button[aria-label*="อนุมัติ"]')).toBeNull();
    fixture.destroy();
  });

  it('does not render a Dry Run plan for multi-package Java setup', async () => {
    localStorage.clear();
    sessionStorage.clear();
    const api = new FakeChatApi();
    api.responder = () => of({ reply: 'ควรเริ่มจาก JDK และเลือก IDE ที่ต้องการ' });
    api.planResponder = (message) => of({
      request: message,
      interpretation: { category: 'development_task', goal: message, target: 'Java' },
      task_plan: {
        steps: [{ order: 1, kind: 'present_plan', title: 'แสดงแผน', detail: 'ตรวจสอบรายการก่อน' }],
        prerequisites: [{ id: 'runtime_toolchain', order: 1, title: 'เลือก JDK', reason: 'ต้องระบุเวอร์ชัน', status: 'user_confirmation_needed' }],
      },
      dry_run_plan: null,
      tool_result: null,
      questions: ['ต้องการ JDK เวอร์ชันใด?', 'ต้องการ IDE ใด?'],
      approved: false,
      notice: 'PLAN_REVIEW_ONLY_NO_EXECUTION',
    });
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatApi, useValue: api }],
    }).compileComponents();
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    await fixture.whenStable();
    const input = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    input.value = 'เตรียมเครื่องพัฒนา Java';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement).click();
    fixture.detectChanges();

    const view = fixture.nativeElement as HTMLElement;
    expect(view.textContent).toContain('ควรเริ่มจาก JDK และเลือก IDE ที่ต้องการ');
    expect(view.textContent).not.toContain('DRY RUN ONLY');
    expect(view.textContent).not.toContain('ผลการจำลอง');
    expect(view.querySelector('button[aria-label*="execute"]')).toBeNull();
    expect(view.querySelector('button[aria-label*="อนุมัติ"]')).toBeNull();
    fixture.destroy();
  });

  it('rejects an invalid Gemini status before displaying a model response', async () => {
    localStorage.clear();
    sessionStorage.clear();
    const api = new FakeChatApi();
    const invalid = {
      schema_version: '1.0',
      message: 'Install Chrome',
      intent: 'software.install',
      status: 'UNRECOGNIZED_STATUS',
      data: { packages: [], environment: null, checks: [], notes: [] },
      needs_clarification: false,
      clarification: null,
    };
    api.responder = () => of({
      request_id: '123e4567-e89b-42d3-a456-426614174000',
      gemini_response: invalid,
      gemini_raw_json: JSON.stringify(invalid),
      provider: 'gemini',
      model: 'test-model',
      provider_connected: true,
    });
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatApi, useValue: api }],
    }).compileComponents();
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    await fixture.whenStable();
    const input = fixture.nativeElement.querySelector('#message-input') as HTMLTextAreaElement;
    input.value = 'ติดตั้ง Chrome';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.gemini-json-details')).toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('UNRECOGNIZED_STATUS');
    expect(api.catalogCalls).toEqual([]);
    fixture.destroy();
  });
  it('rejects a Gemini package item missing required contract fields', async () => {
    localStorage.clear();
    sessionStorage.clear();
    const api = new FakeChatApi();
    const invalid = {
      schema_version: '1.0',
      message: 'Install Chrome',
      intent: 'software.install',
      status: 'ready',
      data: { packages: [{ name: 'Chrome' }], environment: null, checks: [], notes: [] },
      needs_clarification: false,
      clarification: null,
    };
    api.responder = () => of({
      request_id: '123e4567-e89b-42d3-a456-426614174000',
      gemini_response: invalid,
      gemini_raw_json: JSON.stringify(invalid),
      provider: 'gemini',
      model: 'test-model',
      provider_connected: true,
    });
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatApi, useValue: api }],
    }).compileComponents();
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    await fixture.whenStable();
    const input = fixture.nativeElement.querySelector('#message-input') as HTMLTextAreaElement;
    input.value = 'ติดตั้ง Chrome';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.gemini-json-details')).toBeNull();
    expect(fixture.nativeElement.querySelector('textarea')).not.toBeNull();
    expect(api.catalogCalls).toEqual([]);
    fixture.destroy();
  });
  it('Q30: controls have accessible names, labels, and non-positive tab order', async () => {
    localStorage.clear();
    sessionStorage.clear();
    const api = new FakeChatApi();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatApi, useValue: api }],
    }).compileComponents();
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const view = fixture.nativeElement as HTMLElement;
    const buttons = Array.from(view.querySelectorAll('button')) as HTMLButtonElement[];
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      expect((button.getAttribute('aria-label') ?? button.textContent ?? '').trim().length).toBeGreaterThan(0);
      expect(button.tabIndex).toBeGreaterThanOrEqual(0);
    }

    const textareas = Array.from(view.querySelectorAll('textarea')) as HTMLTextAreaElement[];
    for (const textarea of textareas) {
      const label = textarea.getAttribute('aria-label')
        ?? view.querySelector(`label[for="${textarea.id}"]`)?.textContent;
      expect(label?.trim().length ?? 0).toBeGreaterThan(0);
      expect(textarea.tabIndex).toBeGreaterThanOrEqual(0);
    }

    const log = view.querySelector('[role="log"]');
    expect(log?.getAttribute('aria-live')).toBe('polite');
    fixture.destroy();
  });

  it('Q31: no machine-changing control appears in empty, loading, error, or Gemini clarification states', async () => {
    localStorage.clear();
    sessionStorage.clear();
    const api = new FakeChatApi();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatApi, useValue: api }],
    }).compileComponents();
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const assertNoMachineAction = (): void => {
      const view = fixture.nativeElement as HTMLElement;
      const labels = Array.from(view.querySelectorAll('button')).map((button) =>
        `${button.textContent ?? ''} ${button.getAttribute('aria-label') ?? ''}`,
      );
      expect(labels.join(' ')).not.toMatch(/execute|install|uninstall|remove|approve|อนุมัติ|ติดตั้ง|ถอนการติดตั้ง|ดำเนินการจริง/i);
    };

    assertNoMachineAction();
    const pending = new Subject<unknown>();
    api.responder = () => pending;
    const input = fixture.nativeElement.querySelector('#message-input') as HTMLTextAreaElement;
    input.value = 'pending';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement).click();
    fixture.detectChanges();
    assertNoMachineAction();
    pending.error({ status: 500 });
    fixture.detectChanges();
    assertNoMachineAction();

    const contract: GeminiChatResponse['gemini_response'] = {
      schema_version: '1.0',
      message: 'ต้องระบุเวอร์ชัน .NET ก่อนจัดทำแผน',
      intent: 'environment.prepare',
      status: 'needs_clarification',
      data: {
        packages: [{ name: '.NET SDK', version: 'LTS', purpose: 'Build .NET applications', suggested_source: 'Microsoft', suggested_method: 'WinGet after backend verification' }],
        environment: { name: '.NET development', purpose: 'Prepare tools', development_type: 'Unspecified', framework_version: 'LTS' },
        checks: [],
        notes: [],
      },
      needs_clarification: true,
      clarification: 'ต้องการ .NET Web API หรือ Desktop Application?',
    };
    api.responder = () => of({
      request_id: '123e4567-e89b-42d3-a456-426614174000',
      gemini_response: contract,
      gemini_raw_json: JSON.stringify(contract),
      provider: 'gemini',
      model: 'test-model',
      provider_connected: true,
    });
    input.value = 'เตรียมเครื่องพัฒนา .NET';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();
    assertNoMachineAction();
    expect(fixture.nativeElement.textContent).toContain('ต้องการ .NET Web API หรือ Desktop Application?');
    expect(fixture.nativeElement.querySelector('.gemini-json-details')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.clarification-form')).toBeNull();
    fixture.destroy();
  });


  it('Q31: restored conversation state still exposes no machine-changing control', async () => {
    localStorage.clear();
    sessionStorage.clear();
    const conversationId = '123e4567-e89b-42d3-a456-426614174000';
    sessionStorage.setItem('ai-agent-pc-automation.conversation-id', conversationId);
    const api = new FakeChatApi();
    api.history = { messages: [{ role: 'user', text: 'previous request' }, { role: 'assistant', text: 'previous reply' }] };
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatApi, useValue: api }],
    }).compileComponents();
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const view = fixture.nativeElement as HTMLElement;
    expect(view.textContent).toContain('previous request');
    const labels = Array.from(view.querySelectorAll('button')).map((button) =>
      `${button.textContent ?? ''} ${button.getAttribute('aria-label') ?? ''}`,
    );
    expect(labels.join(' ')).not.toMatch(/execute|install|uninstall|remove|approve|อนุมัติ|ติดตั้ง|ถอนการติดตั้ง|ดำเนินการจริง/i);
    fixture.destroy();
  });

});
