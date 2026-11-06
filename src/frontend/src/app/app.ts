import { DOCUMENT } from '@angular/common';
import { AfterViewChecked, Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { defer, finalize, take, timeout, TimeoutError } from 'rxjs';
import { ChatApi, ConversationHistory, UiLanguage } from './chat/chat-api';
import { GeminiSettingsComponent } from './gemini-settings';

type EntryKind = 'user' | 'agent' | 'error';
type ErrorCode = 'MSG-03' | 'MSG-04' | 'MSG-05' | 'MSG-06' | 'MSG-07' | 'MSG-08' | 'MSG-09' | 'MSG-10' | 'MSG-11' | 'MSG-12' | 'MSG-13' | 'MSG-14' | 'MSG-15' | 'MSG-16' | 'MSG-17' | 'MSG-18' | 'MSG-19' | 'MSG-20' | 'MSG-21' | 'MSG-22' | 'MSG-23';

interface StructuredAgentResponse {
  task_status: 'planned' | 'dry_run_completed';
  provider_connected: false;
  plan: {
    intent: { category: string; goal: string; target: string | null };
    prerequisites: Array<{ id: string; order: number; title: string; reason: string; status: string }>;
    steps: Array<{ order: number; title: string; detail: string }>;
    execution_mode: 'dry_run';
    approval_required: true;
  };
  tool_result: { tool_id: string; target: string; status: 'dry_run'; approval_required: true; summary: string } | null;
}

interface ChatEntry {
  id: number;
  kind: EntryKind;
  text: string;
  errorCode?: ErrorCode;
  diagnosticType?: string;
  diagnosticStage?: string;
  diagnosticTrace?: string;
  response?: StructuredAgentResponse;
}

const LANGUAGE_STORAGE_KEY = 'ai-agent-pc-automation.language';
const CONVERSATION_STORAGE_KEY = 'ai-agent-pc-automation.conversation-id';
const MAX_MESSAGE_LENGTH = 2000;
const REQUEST_TIMEOUT_MS = 60_000;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const MESSAGES: Record<UiLanguage, Record<ErrorCode, string>> = {
  th: {
    'MSG-03': 'เชื่อมต่อ Backend ไม่ได้ โปรดตรวจสอบว่า Backend ทำงานอยู่ (scripts\\dev.ps1).',
    'MSG-04': 'ไม่รับข้อความนี้ ข้อความต้องมีความยาว 1 ถึง 2000 อักขระ',
    'MSG-05': 'Backend ปฏิเสธคำขอ (ไม่ผ่านการตรวจสอบความปลอดภัย)',
    'MSG-06': 'Backend พบข้อผิดพลาดภายใน โปรดลองอีกครั้ง',
    'MSG-07': 'Agent ไม่ตอบกลับภายในเวลาที่กำหนด โปรดลองอีกครั้ง',
    'MSG-08': 'Backend ส่งคำตอบในรูปแบบที่ไม่คาดคิด',
    'MSG-09': 'ข้อความมีขนาดใหญ่เกินไป',
    'MSG-10': 'เกิดข้อผิดพลาดที่ไม่คาดคิด (HTTP {status})',
    'MSG-11': 'กรุณาตั้งค่า Gemini API Key ก่อนเริ่มสนทนา',
    'MSG-12': 'Gemini ปฏิเสธ API Key หรือไม่มีสิทธิ์ใช้ API นี้ ตรวจสอบ Key และการตั้งค่าโปรเจกต์',
    'MSG-13': 'โควตา Gemini เต็มหรือเกินขีดจำกัด โปรดตรวจสอบ Quota และ Billing',
    'MSG-14': 'ไม่พบโมเดล Gemini ที่กำหนด โปรดตรวจสอบชื่อโมเดลหรือสิทธิ์ใช้งาน',
    'MSG-15': 'บริการ Gemini ขัดข้องชั่วคราว โปรดลองใหม่ภายหลัง',
    'MSG-16': 'Gemini ปฏิเสธคำขอ โปรดตรวจสอบการตั้งค่า API และลองใหม่',
    'MSG-17': 'Gemini ตอบกลับด้วยข้อผิดพลาดที่ยังระบุสาเหตุไม่ได้ โปรดลองใหม่',
    'MSG-18': 'Gemini ติดต่อไม่ได้ โปรดตรวจสอบอินเทอร์เน็ตหรือ Firewall',
    'MSG-19': 'คำขอไปยัง Gemini หมดเวลา โปรดลองใหม่',
    'MSG-20': 'Gemini ส่งคำตอบที่อ่านไม่ได้กลับมา',
    'MSG-21': 'Gemini ไม่ได้ส่งข้อความตอบกลับ อาจถูกกรองหรือไม่มีข้อความ',
    'MSG-22': 'Gemini SDK พยายามใช้ Google Cloud credentials แต่ไม่พบ token โปรดปิดการตั้งค่า Vertex AI ใน Environment',
    'MSG-23': 'Gemini SDK เกิดข้อผิดพลาดภายใน โปรดส่งชนิดข้อผิดพลาดให้ผู้ดูแล',
  },
  en: {
    'MSG-03': 'Cannot reach the backend. Check that it is running (scripts\\dev.ps1).',
    'MSG-04': 'The message was not accepted. Messages must be 1 to 2000 characters.',
    'MSG-05': 'The backend rejected the request (security check).',
    'MSG-06': 'The backend reported an internal error. Please try again.',
    'MSG-07': 'The Agent did not respond in time. Please try again.',
    'MSG-08': 'The backend sent an unexpected response.',
    'MSG-09': 'The message is too large.',
    'MSG-10': 'Unexpected error (HTTP {status}).',
    'MSG-11': 'Please configure your Gemini API key before chatting.',
    'MSG-12': 'Gemini rejected the API key or access. Check the key and project settings.',
    'MSG-13': 'Gemini quota is exhausted or exceeded. Check your quota and billing.',
    'MSG-14': 'The configured Gemini model is unavailable. Check the model name or access.',
    'MSG-15': 'Gemini is temporarily unavailable. Please try again later.',
    'MSG-16': 'Gemini rejected the request. Check the API configuration and try again.',
    'MSG-17': 'Gemini returned an unclassified error. Please try again.',
    'MSG-18': 'Could not reach Gemini. Check your internet connection or firewall.',
    'MSG-19': 'The request to Gemini timed out. Please try again.',
    'MSG-20': 'Gemini returned a response that could not be read.',
    'MSG-21': 'Gemini returned no text. The response may have been filtered or empty.',
    'MSG-22': 'The Gemini SDK tried to use Google Cloud credentials but found no token. Disable the Vertex AI environment setting.',
    'MSG-23': 'The Gemini SDK encountered an internal error. Share the error type with the maintainer.',
  },
};

function readStoredLanguage(): UiLanguage {
  try {
    if (typeof window === 'undefined') return 'th';
    const saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return saved === 'en' || saved === 'th' ? saved : 'th';
  } catch {
    return 'th';
  }
}

function readStoredConversationId(): string | null {
  try {
    if (typeof window === 'undefined') return null;
    const saved = window.sessionStorage.getItem(CONVERSATION_STORAGE_KEY);
    if (!saved) return null;
    if (UUID_PATTERN.test(saved)) return saved;
    window.sessionStorage.removeItem(CONVERSATION_STORAGE_KEY);
  } catch {
    return null;
  }
  return null;
}

function writeStoredConversationId(conversationId: string): void {
  try {
    if (typeof window !== 'undefined') {
      window.sessionStorage.setItem(CONVERSATION_STORAGE_KEY, conversationId);
    }
  } catch {
    // Keep the conversation usable when browser storage is blocked or unavailable.
  }
}

@Component({
  selector: 'app-root',
  imports: [GeminiSettingsComponent],
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App implements AfterViewChecked {
  private readonly document = inject(DOCUMENT);
  private readonly chatApi = inject(ChatApi);
  private nextEntryId = 0;

  @ViewChild('messageLog') private messageLog?: ElementRef<HTMLElement>;

  protected readonly title = 'AI Agent PC Automation';
  protected readonly language = signal<UiLanguage>(readStoredLanguage());
  protected readonly draft = signal('');
  protected readonly entries = signal<ChatEntry[]>([]);
  protected readonly pending = signal(false);
  protected readonly restoring = signal(false);
  protected readonly clearing = signal(false);
  protected readonly conversationNotice = signal('');
  private readonly conversationId = signal('');

  constructor() {
    this.document.documentElement.lang = this.language();
    const storedConversationId = readStoredConversationId();
    const conversationId = storedConversationId ?? globalThis.crypto.randomUUID();
    this.conversationId.set(conversationId);
    if (storedConversationId) {
      this.restoreConversation(conversationId);
    } else {
      writeStoredConversationId(conversationId);
    }
  }

  ngAfterViewChecked(): void {
    const log = this.messageLog?.nativeElement;
    if (log) log.scrollTop = log.scrollHeight;
  }

  protected setLanguage(language: UiLanguage): void {
    this.language.set(language);
    this.document.documentElement.lang = language;
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
      }
    } catch {
      // Keep the UI usable when browser storage is blocked or unavailable.
    }
  }

  protected onInput(event: Event): void {
    const value = (event.target as HTMLTextAreaElement).value;
    this.draft.set(value.slice(0, MAX_MESSAGE_LENGTH));
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    this.send();
  }

  protected onSubmit(event: Event): void {
    event.preventDefault();
    this.send();
  }

  protected send(): void {
    const message = this.draft().trim();
    if (!message || message.length > MAX_MESSAGE_LENGTH || !this.canSend) return;

    const languageAtSend = this.language();
    const conversationId = this.conversationId();
    this.entries.update((entries) => [
      ...entries,
      { id: ++this.nextEntryId, kind: 'user', text: message },
    ]);
    this.draft.set('');
    this.pending.set(true);

    defer(() => this.chatApi.sendMessage(message, languageAtSend, conversationId))
      .pipe(
        timeout({ first: REQUEST_TIMEOUT_MS }),
        take(1),
        finalize(() => this.pending.set(false)),
      )
      .subscribe({
        next: (response: unknown) => {
          if (this.isReply(response)) {
            this.entries.update((entries) => [
              ...entries,
              { id: ++this.nextEntryId, kind: 'agent', text: response.reply, response: this.isStructuredAgentResponse(response) ? response : undefined },
            ]);
          } else {
            this.appendError('MSG-08');
          }
        },
        error: (error: unknown) => this.appendError(
          this.classifyError(error),
          this.getStatus(error),
          this.getProviderErrorType(error),
          this.getProviderDiagnostic(error, 'stage'),
          this.getProviderDiagnostic(error, 'trace'),
        ),
      });
  }

  protected startNewChat(): void {
    if (this.pending() || this.restoring() || this.clearing()) return;
    const conversationId = this.conversationId();
    this.clearing.set(true);
    this.conversationNotice.set('');
    defer(() => this.chatApi.clearConversation(conversationId))
      .pipe(
        timeout({ first: REQUEST_TIMEOUT_MS }),
        take(1),
        finalize(() => this.clearing.set(false)),
      )
      .subscribe({
        next: () => {
          this.entries.set([]);
          const nextConversationId = globalThis.crypto.randomUUID();
          this.conversationId.set(nextConversationId);
          writeStoredConversationId(nextConversationId);
        },
        error: () => {
          this.conversationNotice.set(this.language() === 'th'
            ? 'ล้างบทสนทนาไม่ได้ โปรดลองอีกครั้ง'
            : 'Could not clear the conversation. Please try again.');
        },
      });
  }

  protected taskStatusLabel(status: StructuredAgentResponse['task_status']): string {
    if (this.language() === 'th') {
      return status === 'dry_run_completed' ? 'จำลองเสร็จแล้ว' : 'วางแผนแล้ว';
    }
    return status === 'dry_run_completed' ? 'Dry run completed' : 'Planned';
  }

  protected prerequisiteLabel(status: string): string {
    const labels: Record<UiLanguage, Record<string, string>> = {
      th: {
        known: 'ทราบแล้ว',
        user_confirmation_needed: 'รอการยืนยันจากผู้ใช้',
        discovery_not_available: 'ยังตรวจสอบไม่ได้ในระยะนี้',
      },
      en: {
        known: 'Known',
        user_confirmation_needed: 'User confirmation needed',
        discovery_not_available: 'Discovery unavailable in this phase',
      },
    };
    return labels[this.language()][status] ?? status;
  }

  protected labelFor(kind: EntryKind): string {
    const labels: Record<UiLanguage, Record<EntryKind, string>> = {
      th: { user: 'คุณ', agent: 'Agent', error: 'ข้อผิดพลาด' },
      en: { user: 'You', agent: 'Agent', error: 'Error' },
    };
    return labels[this.language()][kind];
  }

  protected get hint(): string {
    return this.language() === 'th'
      ? 'เชื่อมต่อ Gemini เพื่อสนทนาได้โดยตรง โดยไม่มีการสั่งงานคอมพิวเตอร์ในขั้นตอนนี้.'
      : 'Chat with Gemini directly. Computer actions are not enabled in this MVP.';
  }

  protected get placeholder(): string {
    return this.language() === 'th' ? 'พิมพ์ข้อความของคุณ...' : 'Type your message...';
  }

  protected get sendLabel(): string {
    return this.language() === 'th' ? 'ส่งข้อความ' : 'Send';
  }

  protected get pendingLabel(): string {
    return this.language() === 'th' ? 'กำลังรอคำตอบจาก Agent…' : 'Waiting for the Agent…';
  }

  protected get canSend(): boolean {
    return !this.pending() && !this.restoring() && !this.clearing()
      && this.draft().trim().length > 0 && this.draft().length <= MAX_MESSAGE_LENGTH;
  }

  protected get newChatLabel(): string {
    return this.language() === 'th' ? 'เริ่มแชตใหม่' : 'New chat';
  }

  protected get newChatDisabled(): boolean {
    return this.pending() || this.restoring() || this.clearing();
  }

  protected get storageNotice(): string {
    return this.language() === 'th'
      ? 'ระบบเก็บบริบท 10 คู่ล่าสุดไว้ในหน่วยความจำ Backend ชั่วคราว และส่งบริบทนี้ให้ Gemini; รีสตาร์ต Backend หรือไม่มีการใช้งาน 1 ชั่วโมงจะล้างข้อมูล'
      : 'The backend temporarily keeps the 10 most recent exchanges in memory and sends this context to Gemini. Restarting the backend or 1 hour of inactivity clears it.';
  }

  protected errorText(entry: ChatEntry): string {
    if (!entry.errorCode) return entry.text;
    const template = MESSAGES[this.language()][entry.errorCode];
    const message = template.replace('{status}', entry.text || 'unknown');
    if (entry.errorCode === 'MSG-17' || entry.errorCode === 'MSG-23') {
      const diagnostics = [entry.diagnosticType, entry.diagnosticStage, entry.diagnosticTrace]
        .filter((value): value is string => !!value);
      return diagnostics.length ? `${message} (${diagnostics.join(' · ')})` : message;
    }
    return message;
  }

  private appendError(
    code: ErrorCode,
    status?: number,
    diagnosticType?: string,
    diagnosticStage?: string,
    diagnosticTrace?: string,
  ): void {
    this.entries.update((entries) => [
      ...entries,
      {
        id: ++this.nextEntryId,
        kind: 'error',
        text: status === undefined ? '' : String(status),
        errorCode: code,
        diagnosticType,
        diagnosticStage,
        diagnosticTrace,
      },
    ]);
  }

  private restoreConversation(conversationId: string): void {
    this.restoring.set(true);
    defer(() => this.chatApi.getConversation(conversationId))
      .pipe(
        timeout({ first: REQUEST_TIMEOUT_MS }),
        take(1),
        finalize(() => this.restoring.set(false)),
      )
      .subscribe({
        next: (history: ConversationHistory) => {
          if (!this.isConversationHistory(history)) {
            this.conversationNotice.set(this.language() === 'th'
              ? 'Backend ส่งประวัติสนทนาในรูปแบบที่ไม่คาดคิด'
              : 'The backend returned an unexpected conversation history.');
            return;
          }
          this.entries.set(history.messages.map((message) => ({
            id: ++this.nextEntryId,
            kind: message.role === 'user' ? 'user' : 'agent',
            text: message.text,
          })));
        },
        error: (error: unknown) => {
          if (this.getStatus(error) === 404) {
            this.conversationId.set(globalThis.crypto.randomUUID());
            writeStoredConversationId(this.conversationId());
            this.conversationNotice.set(this.language() === 'th'
              ? 'บริบทเดิมหมดอายุหรือ Backend ถูกเริ่มใหม่แล้ว เริ่มบทสนทนาใหม่'
              : 'The previous context expired or the backend restarted. A new conversation has started.');
            return;
          }
          this.conversationNotice.set(this.language() === 'th'
            ? 'โหลดประวัติสนทนาไม่ได้ โปรดลองรีโหลดหรือตรวจสอบ Backend'
            : 'Could not load conversation history. Check the backend and try again.');
        },
      });
  }

  private isConversationHistory(value: unknown): value is ConversationHistory {
    if (typeof value !== 'object' || value === null || !('messages' in value)) return false;
    const messages = (value as { messages: unknown }).messages;
    return Array.isArray(messages) && messages.every((message) =>
      typeof message === 'object' && message !== null
      && 'role' in message && (message.role === 'user' || message.role === 'assistant')
      && 'text' in message && typeof message.text === 'string',
    );
  }

  private isStructuredAgentResponse(value: unknown): value is { reply: string } & StructuredAgentResponse {
    if (typeof value !== 'object' || value === null) return false;
    const item = value as Record<string, unknown>;
    return typeof item['task_status'] === 'string'
      && typeof item['plan'] === 'object' && item['plan'] !== null
      && Array.isArray((item['plan'] as Record<string, unknown>)['steps'])
      && Array.isArray((item['plan'] as Record<string, unknown>)['prerequisites']);
  }

  private isReply(value: unknown): value is { reply: string } {
    return typeof value === 'object' && value !== null && 'reply' in value
      && typeof (value as { reply: unknown }).reply === 'string';
  }

  private getStatus(error: unknown): number | undefined {
    if (typeof error !== 'object' || error === null || !('status' in error)) return undefined;
    const status = Number((error as { status: unknown }).status);
    return Number.isFinite(status) ? status : undefined;
  }

  private hasBackendDetail(value: unknown): boolean {
    if (typeof value !== 'object' || value === null) return false;
    const error = value as Record<string, unknown>;
    const body = 'error' in error ? error['error'] : error;
    return typeof body === 'object' && body !== null
      && 'detail' in body && typeof (body as { detail: unknown }).detail === 'string';
  }

  private classifyError(error: unknown): ErrorCode {
    if (error instanceof TimeoutError) return 'MSG-07';
    if (typeof error !== 'object' || error === null || !('status' in error)) return 'MSG-03';

    const status = Number((error as { status: unknown }).status);
    if (status === 409) return 'MSG-11';
    if (status === 0 || status === 503 || status === 504) return 'MSG-03';
    if (status === 400 || status === 403 || status === 415) return 'MSG-05';
    if (status === 413) return 'MSG-09';
    if (status === 422) return 'MSG-04';
    if (status === 200) return 'MSG-08';
    if (status === 502) return this.providerErrorCode(error) ?? 'MSG-06';
    if (status >= 500 && status <= 599) {
      return this.hasBackendDetail(error) ? 'MSG-06' : 'MSG-03';
    }
    return 'MSG-10';
  }

  private providerErrorCode(error: unknown): ErrorCode | undefined {
    if (typeof error !== 'object' || error === null || !('error' in error)) return undefined;
    const body = (error as { error: unknown }).error;
    if (typeof body !== 'object' || body === null || !('detail' in body)) return undefined;
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail !== 'object' || detail === null || !('code' in detail)) return undefined;
    const codes: Record<string, ErrorCode> = {
      key_or_access: 'MSG-12',
      quota_exceeded: 'MSG-13',
      model_unavailable: 'MSG-14',
      provider_unavailable: 'MSG-15',
      request_rejected: 'MSG-16',
      unknown: 'MSG-17',
      network_error: 'MSG-18',
      request_timeout: 'MSG-19',
      invalid_response: 'MSG-20',
      empty_response: 'MSG-21',
      google_cloud_auth_missing: 'MSG-22',
      sdk_runtime_error: 'MSG-23',
    };
    const code = (detail as { code: unknown }).code;
    return typeof code === 'string' ? codes[code] : undefined;
  }

  private getProviderErrorType(error: unknown): string | undefined {
    return this.getProviderDiagnostic(error, 'error_type');
  }

  private getProviderDiagnostic(error: unknown, key: 'error_type' | 'stage' | 'trace'): string | undefined {
    if (typeof error !== 'object' || error === null || !('error' in error)) return undefined;
    const body = (error as { error: unknown }).error;
    if (typeof body !== 'object' || body === null || !('detail' in body)) return undefined;
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail !== 'object' || detail === null || !(key in detail)) return undefined;
    const value = (detail as Record<string, unknown>)[key];
    const pattern = key === 'trace'
      ? /^[A-Za-z0-9_.,-]{1,256}$/
      : /^[A-Za-z][A-Za-z0-9_]{0,63}$/;
    return typeof value === 'string' && pattern.test(value) ? value : undefined;
  }
}
