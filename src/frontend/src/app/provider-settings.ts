import { Component, inject, signal } from '@angular/core';
import { ChatApi, ProviderStatus } from './chat/chat-api';

@Component({
  selector: 'app-provider-settings',
  standalone: true,
  template: `
    <section class="settings" aria-labelledby="provider-settings-title">
      <div class="heading">
        <div>
          <p class="eyebrow">AI PROVIDER ROUTING</p>
          <h2 id="provider-settings-title">เลือก AI Provider</h2>
          <p class="note">เลือกผู้ให้บริการที่จะใช้ตอบแชต ระบบจะตรวจ JSON Schema ฝั่ง Backend เหมือนกันทุก Provider</p>
        </div>
        <span class="state" [class.ready]="status()?.active === 'grok' || status()?.active === 'gemini'">
          {{ status() ? 'พร้อมตั้งค่า' : 'กำลังโหลด' }}
        </span>
      </div>

      <label for="active-provider">Provider ที่ใช้สนทนา</label>
      <select id="active-provider" [value]="status()?.active ?? 'gemini'" (change)="changeProvider($any($event.target).value)" [disabled]="busy() || !status()">
        <option value="gemini" [disabled]="!status()?.gemini_configured">Google Gemini {{ status()?.gemini_configured ? '' : '(ยังไม่ตั้งค่า)' }}</option>
        <option value="grok" [disabled]="!status()?.grok_configured">xAI Grok {{ status()?.grok_configured ? '' : '(ยังไม่ตั้งค่า)' }}</option>
      </select>
      @if (message()) { <p class="message" role="status">{{ message() }}</p> }

      <div class="provider-divider"></div>
      <h3>ตั้งค่า xAI Grok</h3>
      <p class="note">API Key จะอยู่ในหน่วยความจำของ Backend เท่านั้น และต้องทดสอบผ่านก่อนบันทึก</p>
      <label for="grok-model">Grok Model</label>
      <select id="grok-model" [value]="model()" (change)="onModelChanged($any($event.target).value)" [disabled]="busy()">
        @for (item of models(); track item) { <option [value]="item">{{ item }}</option> }
      </select>
      <label for="grok-key">xAI API Key</label>
      <input id="grok-key" type="password" autocomplete="off" spellcheck="false"
        [value]="apiKey()" (input)="onKeyChanged($any($event.target).value)"
        [disabled]="busy()" placeholder="วาง xAI API Key ที่นี่" />
      <div class="actions">
        <button type="button" class="secondary" [disabled]="busy() || (!status()?.grok_configured && !apiKey().trim())" (click)="test()">ทดสอบ Grok</button>
        <button type="button" [disabled]="busy() || !testPassed()" (click)="save()">บันทึก Grok</button>
      </div>
      @if (grokMessage()) { <p class="message" role="status">{{ grokMessage() }}</p> }
      <p class="note">เริ่มต้นรองรับ Grok 4.7 แบบ Structured Outputs และจะไม่ส่งคำสั่งติดตั้งตรงไปยัง Grok</p>
    </section>
  `,
  styles: [`
    :host { display:block; margin-bottom:18px; }
    .settings { padding:18px; border:1px solid var(--line,#e9e9f1); border-radius:13px; background:var(--surface,#fff); box-shadow:0 8px 28px #173b3010; }
    .heading { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:14px; }
    .eyebrow { margin:0 0 4px; color:var(--muted,#8b8da2); font-size:10px; font-weight:750; letter-spacing:.14em; }
    h2 { margin:0; color:var(--ink,#1d302d); font-size:15px; }
    h3 { margin:0 0 8px; color:var(--ink,#1d302d); font-size:13px; }
    .note { margin:5px 0 10px; color:var(--muted,#8b8da2); font-size:11px; line-height:1.6; }
    .state { padding:5px 9px; border:1px solid var(--line,#e9e9f1); border-radius:5px; color:var(--muted,#8b8da2); font-size:10px; white-space:nowrap; }
    .state.ready { color:#28634b; background:#eaf4ed; border-color:#c8dfd0; }
    label { display:block; margin:12px 0 7px; font-size:12px; font-weight:700; }
    select,input { box-sizing:border-box; width:100%; padding:10px 12px; border:1px solid var(--line-strong,#e0e0eb); border-radius:8px; background:var(--surface,#fff); color:var(--ink,#22253a); font:inherit; font-size:12px; }
    .provider-divider { height:1px; margin:17px 0; background:var(--line,#e9e9f1); }
    .actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
    button { padding:9px 12px; border:0; border-radius:7px; color:#fff; background:#285d50; font:inherit; font-size:11px; font-weight:700; cursor:pointer; }
    button.secondary { color:var(--ink,#22253a); background:var(--active,#f4f3fa); border:1px solid var(--line,#e9e9f1); }
    button:disabled,select:disabled,input:disabled { opacity:.5; cursor:not-allowed; }
    .message { margin:10px 0 0; color:var(--ink,#22253a); font-size:12px; }
  `],
})
export class ProviderSettingsComponent {
  private readonly api = inject(ChatApi);
  protected readonly status = signal<ProviderStatus | null>(null);
  protected readonly apiKey = signal('');
  protected readonly model = signal('grok-4.7');
  protected readonly models = signal<string[]>(['grok-4.7']);
  protected readonly busy = signal(false);
  protected readonly testPassed = signal(false);
  protected readonly testedModel = signal<string | null>(null);
  protected readonly message = signal('');
  protected readonly grokMessage = signal('');

  constructor() {
    this.refresh();
    this.api.getGrokStatus().subscribe({
      next: (result) => {
        this.models.set(result.models.length ? result.models : [result.model]);
        this.model.set(result.model);
      },
      error: () => this.grokMessage.set('อ่านสถานะ Grok ไม่สำเร็จ'),
    });
  }

  private refresh(): void {
    this.api.getProviderStatus().subscribe({
      next: (result) => this.status.set(result),
      error: () => this.message.set('อ่านสถานะ Provider ไม่สำเร็จ'),
    });
  }

  protected changeProvider(provider: 'gemini' | 'grok'): void {
    if (this.busy()) return;
    this.grokMessage.set('');
    this.busy.set(true);
    this.api.setActiveProvider(provider).subscribe({
      next: (result) => {
        this.status.set(result);
        this.message.set(`เปลี่ยน Provider เป็น ${provider} แล้ว`);
        this.busy.set(false);
      },
      error: () => {
        this.message.set('เปลี่ยน Provider ไม่สำเร็จ ตรวจสอบว่าตั้งค่าและทดสอบ Provider แล้ว');
        this.refresh();
        this.busy.set(false);
      },
    });
  }

  protected onKeyChanged(value: string): void {
    this.apiKey.set(value);
    this.invalidateTest('API Key เปลี่ยนแล้ว กรุณาทดสอบใหม่');
  }

  protected onModelChanged(value: string): void {
    this.model.set(value);
    this.invalidateTest('Model เปลี่ยนแล้ว กรุณาทดสอบใหม่');
  }

  private invalidateTest(message: string): void {
    this.testPassed.set(false);
    this.testedModel.set(null);
    this.grokMessage.set(message);
  }

  protected test(): void {
    if (this.busy() || (!this.status()?.grok_configured && !this.apiKey().trim())) return;
    const selected = this.model();
    this.busy.set(true);
    this.testPassed.set(false);
    this.testedModel.set(null);
    this.grokMessage.set(`กำลังทดสอบ ${selected} ด้วย Structured Outputs...`);
    this.api.testGrokConnection(selected, this.apiKey()).subscribe({
      next: (result) => {
        if (!result.connected || result.model !== selected) {
          this.grokMessage.set('ผลทดสอบไม่ตรงกับ Model ที่เลือก');
        } else {
          this.testPassed.set(true);
          this.testedModel.set(selected);
          this.grokMessage.set(`ทดสอบ ${selected} ผ่านแล้ว กดบันทึกเพื่อใช้งาน`);
        }
        this.busy.set(false);
      },
      error: (error: unknown) => {
        this.testPassed.set(false);
        this.testedModel.set(null);
        this.grokMessage.set(this.errorMessage(error));
        this.busy.set(false);
      },
    });
  }

  protected save(): void {
    if (this.busy() || !this.testPassed() || this.testedModel() !== this.model()) return;
    this.busy.set(true);
    this.api.saveGrokKey(this.apiKey(), this.model()).subscribe({
      next: (result) => {
        this.apiKey.set('');
        this.testPassed.set(false);
        this.testedModel.set(null);
        this.grokMessage.set(`บันทึก ${result.model} สำเร็จ`);
        this.refresh();
        this.busy.set(false);
      },
      error: () => {
        this.grokMessage.set('บันทึกไม่สำเร็จ ค่าเดิมยังคงใช้งานอยู่');
        this.busy.set(false);
      },
    });
  }

  private errorMessage(error: unknown): string {
    const detail = (error as { error?: { detail?: { code?: string } } })?.error?.detail;
    const messages: Record<string, string> = {
      key_or_access: 'xAI ปฏิเสธ API Key หรือไม่มีสิทธิ์ใช้งาน',
      quota_exceeded: 'Grok ใช้เกิน Rate Limit หรือ Quota',
      model_unavailable: 'ไม่พบ Grok Model นี้หรือไม่มีสิทธิ์ใช้งาน',
      provider_unavailable: 'บริการ xAI ขัดข้องชั่วคราว',
      request_rejected: 'xAI ปฏิเสธคำขอ ตรวจสอบ API และ Schema',
      network_error: 'ติดต่อ xAI ไม่ได้ ตรวจสอบอินเทอร์เน็ตหรือ Firewall',
      request_timeout: 'คำขอไปยัง xAI หมดเวลา',
      invalid_response: 'Grok ส่ง JSON ที่ไม่ตรงกับ Contract',
      empty_response: 'Grok ไม่ได้ส่งเนื้อหากลับมา',
    };
    return (detail?.code && messages[detail.code]) || 'ทดสอบ Grok ไม่สำเร็จ ตรวจสอบ Diagnostics';
  }
}
