import { DOCUMENT } from '@angular/common';
import { AfterViewChecked, Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { defer, finalize, take, timeout, TimeoutError } from 'rxjs';
import { ChatApi, UiLanguage } from './chat/chat-api';

type EntryKind = 'user' | 'agent' | 'error';
type ErrorCode = 'MSG-03' | 'MSG-04' | 'MSG-05' | 'MSG-06' | 'MSG-07' | 'MSG-08' | 'MSG-09' | 'MSG-10';

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
  response?: StructuredAgentResponse;
}

const LANGUAGE_STORAGE_KEY = 'ai-agent-pc-automation.language';
const MAX_MESSAGE_LENGTH = 2000;
const REQUEST_TIMEOUT_MS = 10_000;

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

@Component({
  selector: 'app-root',
  imports: [],
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

  constructor() {
    this.document.documentElement.lang = this.language();
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
    if (!message || message.length > MAX_MESSAGE_LENGTH || this.pending()) return;

    const languageAtSend = this.language();
    this.entries.update((entries) => [
      ...entries,
      { id: ++this.nextEntryId, kind: 'user', text: message },
    ]);
    this.draft.set('');
    this.pending.set(true);

    defer(() => this.chatApi.sendMessage(message, languageAtSend))
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
        error: (error: unknown) => this.appendError(this.classifyError(error), this.getStatus(error)),
      });
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
      ? 'Agent จะช่วยวิเคราะห์คำขอและแสดงแผนงานในโหมดจำลอง โดยยังไม่มีการเปลี่ยนแปลงเครื่องคอมพิวเตอร์.'
      : 'The Agent analyzes requests and presents a dry-run plan. No changes are made to your computer.';
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
    return !this.pending() && this.draft().trim().length > 0 && this.draft().length <= MAX_MESSAGE_LENGTH;
  }

  protected errorText(entry: ChatEntry): string {
    if (!entry.errorCode) return entry.text;
    const template = MESSAGES[this.language()][entry.errorCode];
    return template.replace('{status}', entry.text || 'unknown');
  }

  private appendError(code: ErrorCode, status?: number): void {
    this.entries.update((entries) => [
      ...entries,
      {
        id: ++this.nextEntryId,
        kind: 'error',
        text: status === undefined ? '' : String(status),
        errorCode: code,
      },
    ]);
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
    if (status === 0 || status === 502 || status === 503 || status === 504) return 'MSG-03';
    if (status === 400 || status === 403 || status === 415) return 'MSG-05';
    if (status === 413) return 'MSG-09';
    if (status === 422) return 'MSG-04';
    if (status === 200) return 'MSG-08';
    if (status >= 500 && status <= 599) {
      return this.hasBackendDetail(error) ? 'MSG-06' : 'MSG-03';
    }
    return 'MSG-10';
  }
}
