import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Observable, Subject, of, throwError } from 'rxjs';
import { TimeoutError } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './app';
import { ChatApi, UiLanguage } from './chat/chat-api';

class FakeChatApi {
  calls: Array<{ message: string; language: UiLanguage }> = [];
  responder: (message: string, language: UiLanguage) => Observable<unknown> = () => of({ reply: 'Mock reply' });

  sendMessage(message: string, language: UiLanguage): Observable<unknown> {
    this.calls.push({ message, language });
    return this.responder(message, language);
  }
}

describe('App chat UI (T-202)', () => {
  let fixture: ComponentFixture<App>;
  let api: FakeChatApi;

  async function render(): Promise<void> {
    fixture = TestBed.createComponent(App);
    fixture.detectChanges();
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

  function send(value = 'hello'): void {
    inputText(value);
    sendButton().click();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    localStorage.clear();
    api = new FakeChatApi();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatApi, useValue: api }],
    }).compileComponents();
  });

  afterEach(() => {
    fixture?.destroy();
    vi.restoreAllMocks();
  });

  it('F-01: starts in Thai with the empty hint and disabled Send', async () => {
    await render();
    expect(fixture.nativeElement.textContent).toContain('เริ่มพิมพ์ข้อความได้เลย Agent ยังไม่พร้อมใช้งาน');
    expect(sendButton().disabled).toBe(true);
    expect(document.documentElement.lang).toBe('th');
    expect(fixture.nativeElement.querySelector('textarea')?.getAttribute('placeholder')).toContain('พิมพ์');
  });

  it('F-02: whitespace-only input keeps Send disabled', async () => {
    await render();
    inputText('   \n  ');
    expect(sendButton().disabled).toBe(true);
  });

  it('F-03/F-04: sends trimmed text, shows user and Agent entries, and clears the composer', async () => {
    await render();
    send('  hello Agent  ');
    expect(api.calls).toEqual([{ message: 'hello Agent', language: 'th' }]);
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

  it('F-08: maps validation, rejection, server, malformed reply, too-large and other errors', async () => {
    const cases: Array<{ error: unknown; expected: string }> = [
      { error: { status: 0 }, expected: 'Cannot reach the backend' },
      { error: { status: 400 }, expected: 'security check' },
      { error: { status: 403 }, expected: 'security check' },
      { error: { status: 415 }, expected: 'security check' },
      { error: { status: 413 }, expected: 'message is too large' },
      { error: { status: 422 }, expected: '1 to 2000 characters' },
      { error: { status: 500, detail: 'internal' }, expected: 'internal error' },
      { error: { status: 502 }, expected: 'Cannot reach the backend' },
      { error: { status: 503 }, expected: 'Cannot reach the backend' },
      { error: { status: 504 }, expected: 'Cannot reach the backend' },
      { error: { status: 500 }, expected: 'Cannot reach the backend' },
      { error: { status: 404 }, expected: 'Unexpected error (HTTP 404)' },
    ];
    await render();
    for (const item of cases) {
      api.responder = () => throwError(() => item.error);
      send('test');
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain('Error');
      expect(fixture.nativeElement.textContent).toContain(item.expected);
      expect(sendButton().disabled).toBe(true);
      inputText('next');
    }
  });

  it('F-09: timeout shows MSG-07 and allows a new send', async () => {
    await render();
    api.responder = () => throwError(() => new TimeoutError());
    send('slow');
    expect(fixture.nativeElement.textContent).toContain('Agent did not respond in time');
    send('again');
    expect(api.calls).toHaveLength(2);
  });

  it('F-10: renders user and reply HTML as literal text', async () => {
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

  it('F-13: does not store messages or chat history in browser storage', async () => {
    await render();
    send('private test message');
    expect(localStorage.length).toBe(0);
    expect(localStorage.getItem('private test message')).toBeNull();
  });

  it('F-14: the default ChatApi is disconnected and shows MSG-03', async () => {
    await TestBed.resetTestingModule();
    localStorage.clear();
    await TestBed.configureTestingModule({ imports: [App] }).compileComponents();
    await render();
    send('hello');
    expect(fixture.nativeElement.textContent).toContain('เชื่อมต่อ Backend ไม่ได้');
  });

  it('F-17/F-18: language switch updates the UI and document language', async () => {
    await render();
    const english = Array.from(fixture.nativeElement.querySelectorAll('button')).find((button: Element) => button.textContent?.trim() === 'EN') as HTMLButtonElement;
    english.click();
    fixture.detectChanges();
    expect(document.documentElement.lang).toBe('en');
    expect(fixture.nativeElement.textContent).toContain('Start a conversation');
    expect(fixture.nativeElement.querySelector('textarea')?.getAttribute('placeholder')).toBe('Type your message...');
    expect(sendButton().textContent).toContain('Send');
    const thai = Array.from(fixture.nativeElement.querySelectorAll('button')).find((button: Element) => button.textContent?.trim() === 'ไทย') as HTMLButtonElement;
    thai.click();
    fixture.detectChanges();
    expect(document.documentElement.lang).toBe('th');
    expect(fixture.nativeElement.textContent).toContain('เริ่มต้นบทสนทนา');
  });

  it('F-19: saves and restores only the selected language', async () => {
    await render();
    fixture.nativeElement.querySelectorAll('button')[1].click();
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
    const english = Array.from(fixture.nativeElement.querySelectorAll('button')).find((button: Element) => button.textContent?.trim() === 'EN') as HTMLButtonElement;
    english.click();
    fixture.detectChanges();
    expect(document.documentElement.lang).toBe('en');
  });

  it('F-21: every MSG-03 to MSG-10 error has Thai and English text', async () => {
    const cases: Array<{ error: unknown; thai: string; english: string }> = [
      { error: { status: 0 }, thai: 'เชื่อมต่อ Backend ไม่ได้', english: 'Cannot reach the backend' },
      { error: { status: 422 }, thai: 'ไม่รับข้อความนี้', english: '1 to 2000 characters' },
      { error: { status: 403 }, thai: 'Backend ปฏิเสธคำขอ', english: 'security check' },
      { error: { status: 500, detail: 'x' }, thai: 'Backend พบข้อผิดพลาดภายใน', english: 'internal error' },
      { error: new TimeoutError(), thai: 'Agent ไม่ตอบกลับ', english: 'Agent did not respond in time' },
      { error: { status: 200, malformed: true }, thai: 'รูปแบบที่ไม่คาดคิด', english: 'unexpected response' },
      { error: { status: 413 }, thai: 'ข้อความมีขนาดใหญ่เกินไป', english: 'message is too large' },
      { error: { status: 404 }, thai: 'HTTP 404', english: 'HTTP 404' },
    ];
    await render();
    for (const item of cases) {
      api.responder = () => item.error instanceof TimeoutError ? throwError(() => item.error) : item.error && typeof item.error === 'object' && 'malformed' in item.error ? of(item.error) : throwError(() => item.error);
      send('error case');
      expect(fixture.nativeElement.textContent).toContain(item.thai);
      const english = Array.from(fixture.nativeElement.querySelectorAll('button')).find((button: Element) => button.textContent?.trim() === 'EN') as HTMLButtonElement;
      english.click();
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain(item.english);
      const thai = Array.from(fixture.nativeElement.querySelectorAll('button')).find((button: Element) => button.textContent?.trim() === 'ไทย') as HTMLButtonElement;
      thai.click();
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
    const english = Array.from(fixture.nativeElement.querySelectorAll('button')).find((button: Element) => button.textContent?.trim() === 'EN') as HTMLButtonElement;
    english.click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Error');
    expect(fixture.nativeElement.textContent).toContain('ข้อความของฉัน');
    expect(fixture.nativeElement.textContent).toContain('ตอบกลับภาษาไทย');
    expect(fixture.nativeElement.textContent).toContain('security check');
  });
});
