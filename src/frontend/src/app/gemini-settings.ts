import { Component, inject, signal } from '@angular/core';
import { ChatApi } from './chat/chat-api';

@Component({
  selector: 'app-gemini-settings',
  standalone: true,
  template: `
    <section class="settings" aria-labelledby="gemini-settings-title">
      <div class="heading">
        <div>
          <p class="eyebrow">AI PROVIDER</p>
          <h2 id="gemini-settings-title">ตั้งค่า Google Gemini</h2>
          <p class="model">Model: gemini-3.1-flash-lite</p>
        </div>
        <span class="state" [class.ready]="configured()">{{ configured() ? 'บันทึกแล้ว' : 'ยังไม่ตั้งค่า' }}</span>
      </div>
      <label for="gemini-key">Gemini API Key</label>
      <input
        id="gemini-key"
        type="password"
        autocomplete="off"
        spellcheck="false"
        [value]="apiKey()"
        (input)="apiKey.set($any($event.target).value)"
        placeholder="วาง API Key ที่นี่"
      />
      <div class="actions">
        <button type="button" [disabled]="busy() || !apiKey().trim()" (click)="save()">บันทึก Key</button>
        <button type="button" class="secondary" [disabled]="busy() || !configured()" (click)="test()">ทดสอบการเชื่อมต่อ</button>
      </div>
      @if (message()) {
        <p class="message" role="status">{{ message() }}</p>
      }
      <p class="note">Key เก็บในหน่วยความจำของ Backend เท่านั้น และจะถูกล้างเมื่อปิดหรือเริ่ม Backend ใหม่</p>
    </section>
  `,
  styles: [`
    :host { display:block; margin-bottom:18px; }
    .settings { padding:18px 20px; border:1px solid var(--line,#e9e9f1); border-radius:18px; background:var(--surface,#fff); }
    .heading { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:14px; }
    .eyebrow { margin:0 0 4px; color:var(--muted,#8b8da2); font-size:10px; font-weight:750; letter-spacing:.14em; }
    h2 { margin:0; font-size:16px; }
    .model,.note { margin:5px 0 0; color:var(--muted,#8b8da2); font-size:11px; }
    .state { padding:5px 9px; border-radius:99px; background:#f3f1e9; color:#827044; font-size:10px; white-space:nowrap; }
    .state.ready { background:#eaf6ef; color:#26784b; }
    label { display:block; margin-bottom:7px; font-size:12px; font-weight:700; }
    input { box-sizing:border-box; width:100%; padding:11px 12px; border:1px solid var(--line-strong,#e0e0eb); border-radius:10px; background:var(--surface,#fff); color:var(--ink,#22253a); font:inherit; font-size:12px; }
    input:focus { outline:2px solid #8175df55; border-color:#8175df; }
    .actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
    button { padding:9px 12px; border:0; border-radius:9px; color:#fff; background:#7165dc; font:inherit; font-size:11px; font-weight:700; cursor:pointer; }
    button.secondary { color:var(--ink,#22253a); background:var(--active,#f4f3fa); border:1px solid var(--line,#e9e9f1); }
    button:disabled { opacity:.45; cursor:not-allowed; }
    .message { margin:10px 0 0; font-size:12px; color:var(--ink,#22253a); }
  `],
})
export class GeminiSettingsComponent {
  private readonly api = inject(ChatApi);
  protected readonly apiKey = signal('');
  protected readonly configured = signal(false);
  protected readonly busy = signal(false);
  protected readonly message = signal('');

  constructor() {
    this.api.getGeminiStatus().subscribe({
      next: (result) => this.configured.set(result.configured),
      error: () => this.message.set('อ่านสถานะการตั้งค่าไม่ได้'),
    });
  }

  protected save(): void {
    const key = this.apiKey().trim();
    if (!key || this.busy()) return;
    this.busy.set(true);
    this.message.set('');
    this.api.saveGeminiKey(key).subscribe({
      next: () => {
        this.configured.set(true);
        this.apiKey.set('');
        this.message.set('บันทึก Key ใน Backend แล้ว');
        this.busy.set(false);
      },
      error: () => {
        this.message.set('บันทึก Key ไม่สำเร็จ');
        this.busy.set(false);
      },
    });
  }

  protected test(): void {
    if (this.busy() || !this.configured()) return;
    this.busy.set(true);
    this.message.set('กำลังทดสอบ Gemini API...');
    this.api.testGeminiConnection().subscribe({
      next: () => {
        this.message.set('เชื่อมต่อ Gemini สำเร็จ พร้อมใช้งาน Chat');
        this.busy.set(false);
      },
      error: () => {
        this.message.set('ทดสอบไม่สำเร็จ ตรวจสอบ API Key, quota และการเชื่อมต่อ');
        this.busy.set(false);
      },
    });
  }
}
