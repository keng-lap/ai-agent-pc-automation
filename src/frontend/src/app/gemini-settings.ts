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
          <p class="model">เลือก Model ที่ต้องการใช้งาน</p>
        </div>
        <span class="state" [class.ready]="configured()">{{ configured() ? 'บันทึกแล้ว' : 'ยังไม่ตั้งค่า' }}</span>
      </div>
      <label for="gemini-model">Gemini Model</label>
      <select id="gemini-model" [value]="selectedModel()" (change)="selectModel($any($event.target).value)" [disabled]="busy()">
        @for (model of models(); track model) {
          <option [value]="model">{{ model }}</option>
        }
      </select>
      <label for="gemini-key">Gemini API Key (กรอกเฉพาะเมื่อต้องการเปลี่ยน Key)</label>
      <input
        id="gemini-key"
        type="password"
        [disabled]="busy()"
        autocomplete="off"
        spellcheck="false"
        [value]="apiKey()"
        (input)="onApiKeyChanged($any($event.target).value)"
        placeholder="วาง API Key ที่นี่"
      />
      <div class="actions">
        <button type="button" [disabled]="busy() || !testPassed()" (click)="save()">บันทึก Model และ Key</button>
        <button type="button" class="secondary" [disabled]="busy() || (!configured() && !apiKey().trim())" (click)="test()">ทดสอบ Model ที่เลือก</button>
      </div>
      @if (message()) {
        <p class="message" role="status">{{ message() }}</p>
      }
      <p class="note">ต้องทดสอบ Model ที่เลือกให้ผ่านก่อนจึงจะบันทึกได้ หากเปลี่ยน Model หรือ Key ต้องทดสอบใหม่ ค่าเดิมจะยังใช้งานอยู่จนกว่าจะบันทึกสำเร็จ</p>
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
    select { box-sizing:border-box; width:100%; margin-bottom:12px; padding:10px 12px; border:1px solid var(--line-strong,#e0e0eb); border-radius:10px; background:var(--surface,#fff); color:var(--ink,#22253a); font:inherit; font-size:12px; }
    input { box-sizing:border-box; width:100%; padding:11px 12px; border:1px solid var(--line-strong,#e0e0eb); border-radius:10px; background:var(--surface,#fff); color:var(--ink,#22253a); font:inherit; font-size:12px; }
    input:focus { outline:2px solid #8175df55; border-color:#8175df; }
    .actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
    button { padding:9px 12px; border:0; border-radius:9px; color:#fff; background:#7165dc; font:inherit; font-size:11px; font-weight:700; cursor:pointer; }
    button.secondary { color:var(--ink,#22253a); background:var(--active,#f4f3fa); border:1px solid var(--line,#e9e9f1); }
    button:disabled { opacity:.45; cursor:not-allowed; }
    .message { margin:10px 0 0; font-size:12px; color:var(--ink,#22253a); }
  ` + "\n    :host { margin-bottom:0; }\n    .settings { padding:18px; border-radius:13px; background:var(--surface,#fff); box-shadow:0 8px 28px #173b3010; }\n    h2 { color:var(--ink,#1d302d); font-size:15px; letter-spacing:-.02em; }\n    .state { border:1px solid #e5d9bd; border-radius:5px; color:#876a35; background:#fbf6e9; }\n    .state.ready { border-color:#c8dfd0; color:#28634b; background:#eaf4ed; }\n    input { border-radius:8px; }\n    button { border-radius:7px; background:#285d50; }\n    button:hover:not(:disabled) { background:#1d493e; }\n    button.secondary { color:var(--ink,#1d302d); background:var(--active,#e8f1ec); border:1px solid var(--line,#dfe8e3); }\n    .note { line-height:1.6; }\n    @media (prefers-color-scheme:dark) {\n      .state { border-color:#665638; color:#e4c78f; background:#3a3325; }\n      .state.ready { border-color:#496a58; color:#bfe0cb; background:#2a4437; }\n    }\n",
  ],
})
export class GeminiSettingsComponent {
  private readonly api = inject(ChatApi);
  protected readonly apiKey = signal('');
  protected readonly configured = signal(false);
  protected readonly busy = signal(false);
  protected readonly message = signal('');
  protected readonly models = signal<string[]>(['gemini-3.1-flash-lite', 'gemini-2.5-flash', 'gemini-2.5-pro']);
  protected readonly selectedModel = signal('gemini-3.1-flash-lite');
  protected readonly testedModel = signal<string | null>(null);
  protected readonly testPassed = signal(false);

  constructor() {
    this.api.getGeminiStatus().subscribe({
      next: (result) => {
        this.configured.set(result.configured);
        this.models.set(result.models?.length ? result.models : [result.model]);
        this.selectedModel.set(result.model);
      },
      error: () => this.message.set('อ่านสถานะการตั้งค่าไม่ได้'),
    });
  }

  protected selectModel(model: string): void {
    this.selectedModel.set(model);
    this.testedModel.set(null);
    this.testPassed.set(false);
    this.message.set('Model เปลี่ยนแล้ว กรุณาทดสอบใหม่ก่อนบันทึก');
  }

  protected onApiKeyChanged(value: string): void {
    this.apiKey.set(value);
    this.testedModel.set(null);
    this.testPassed.set(false);
    this.message.set('Key เปลี่ยนแล้ว กรุณาทดสอบใหม่ก่อนบันทึก');
  }

  protected save(): void {
    if (this.busy() || !this.testPassed() || this.testedModel() !== this.selectedModel()) return;
    this.busy.set(true);
    this.message.set('กำลังบันทึกการตั้งค่า Gemini...');
    this.api.saveGeminiKey(this.apiKey(), this.selectedModel()).subscribe({
      next: (result) => {
        this.configured.set(result.configured);
        this.selectedModel.set(result.model);
        this.apiKey.set('');
        this.testedModel.set(null);
        this.testPassed.set(false);
        this.message.set('บันทึก Model สำเร็จ การสนทนาครั้งถัดไปจะใช้ Model นี้');
        this.busy.set(false);
      },
      error: () => {
        this.message.set('บันทึกไม่สำเร็จ ค่า Model เดิมยังคงใช้งานอยู่');
        this.busy.set(false);
      },
    });
  }

  protected test(): void {
    if (this.busy() || (!this.configured() && !this.apiKey().trim())) return;
    const model = this.selectedModel();
    this.busy.set(true);
    this.testPassed.set(false);
    this.testedModel.set(null);
    this.message.set(`กำลังทดสอบ ${model}...`);
    this.api.testGeminiConnection(model, this.apiKey()).subscribe({
      next: (result) => {
        if (result.model !== model) {
          this.message.set('ผลทดสอบไม่ตรงกับ Model ที่เลือก กรุณาทดสอบใหม่');
          this.busy.set(false);
          return;
        }
        this.testedModel.set(model);
        this.testPassed.set(true);
        this.message.set(`ทดสอบ ${model} ผ่านแล้ว กดบันทึกเพื่อใช้งาน Model นี้`);
        this.busy.set(false);
      },
      error: (error: unknown) => {
        this.testPassed.set(false);
        this.testedModel.set(null);
        this.message.set(this.testErrorMessage(error));
        this.busy.set(false);
      },
    });
  }

  private testErrorMessage(error: unknown): string {
    if (typeof error !== 'object' || error === null || !('error' in error)) {
      return 'ทดสอบไม่สำเร็จ ตรวจสอบการเชื่อมต่อ Backend';
    }
    const body = (error as { error: unknown }).error;
    if (typeof body !== 'object' || body === null || !('detail' in body)) {
      return 'ทดสอบไม่สำเร็จ ตรวจสอบการเชื่อมต่อ Backend';
    }
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail !== 'object' || detail === null || !('code' in detail)) {
      return 'ทดสอบไม่สำเร็จ ตรวจสอบการเชื่อมต่อ Backend';
    }
    const messages: Record<string, string> = {
      key_or_access: 'Gemini ปฏิเสธ API Key หรือไม่มีสิทธิ์ใช้ API นี้ ตรวจสอบ Key และโปรเจกต์',
      quota_exceeded: 'โควตา Gemini เต็มหรือเกินขีดจำกัด ตรวจสอบ Quota และ Billing',
      model_unavailable: 'ไม่พบโมเดล Gemini ที่กำหนด ตรวจสอบชื่อโมเดลหรือสิทธิ์ใช้งาน',
      provider_unavailable: 'บริการ Gemini ขัดข้องชั่วคราว โปรดลองใหม่ภายหลัง',
      request_rejected: 'Gemini ปฏิเสธคำขอ ตรวจสอบการตั้งค่า API',
      network_error: 'ติดต่อ Gemini ไม่ได้ ตรวจสอบอินเทอร์เน็ตหรือ Firewall',
      request_timeout: 'คำขอไปยัง Gemini หมดเวลา โปรดลองใหม่',
      invalid_response: 'Gemini ส่งคำตอบที่อ่านไม่ได้กลับมา',
      empty_response: 'Gemini ไม่ได้ส่งข้อความตอบกลับ อาจถูกกรองหรือไม่มีข้อความ',
      google_cloud_auth_missing: 'Gemini SDK พยายามใช้ Google Cloud credentials แต่ไม่พบ token ตรวจสอบว่าปิด GOOGLE_GENAI_USE_VERTEXAI',
      sdk_runtime_error: 'Gemini SDK เกิดข้อผิดพลาดภายใน',
      unknown: 'Gemini ตอบกลับด้วยข้อผิดพลาดที่ยังระบุสาเหตุไม่ได้',
    };
    const code = (detail as { code: unknown }).code;
    const message = typeof code === 'string'
      ? messages[code] ?? 'ทดสอบไม่สำเร็จ ตรวจสอบการเชื่อมต่อ Gemini'
      : 'ทดสอบไม่สำเร็จ ตรวจสอบการเชื่อมต่อ Gemini';
    const errorType = (detail as { error_type?: unknown }).error_type;
    if ((code === 'unknown' || code === 'sdk_runtime_error')
      && typeof errorType === 'string'
      && /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(errorType)) {
      const stage = (detail as { stage?: unknown }).stage;
      const trace = (detail as { trace?: unknown }).trace;
      const diagnostics = [errorType];
      if (typeof stage === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(stage)) {
        diagnostics.push(stage);
      }
      if (typeof trace === 'string' && /^[A-Za-z0-9_.,-]{1,256}$/.test(trace)) {
        diagnostics.push(trace);
      }
      return `${message} (${diagnostics.join(' · ')})`;
    }
    return message;
  }
}
