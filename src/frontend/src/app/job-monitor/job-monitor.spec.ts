import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { JobMonitorComponent } from './job-monitor';

describe('JobMonitorComponent', () => {
  let fixture: ComponentFixture<JobMonitorComponent>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [JobMonitorComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(JobMonitorComponent);
    fixture.detectChanges();
  });

  afterEach(() => {
    fixture.destroy();
    http.verify();
  });

  it('renders backend job state and bounded event data without mock records', async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
    const request = http.expectOne((req) => req.url === '/api/jobs' && req.params.get('limit') === '25');
    expect(request.request.method).toBe('GET');
    request.flush({
      checked_at: '2026-11-13T09:45:00Z',
      jobs: [{
        job_id: 'job-123',
        tool_id: 'software.install',
        state: 'RUNNING',
        created_at: '2026-11-13T09:40:00Z',
        started_at: '2026-11-13T09:40:02Z',
        finished_at: null,
        progress_message: 'กำลังติดตั้งแพ็กเกจที่ได้รับอนุมัติ',
        result_code: null,
        reboot_required: false,
        recent_events: [{
          sequence: 3,
          occurred_at: '2026-11-13T09:42:00Z',
          state: 'RUNNING',
          level: 'INFO',
          message: 'Process started inside containment',
        }],
      }],
    });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('job-123');
    expect(fixture.nativeElement.textContent).toContain('กำลังทำงาน');
    expect(fixture.nativeElement.textContent).toContain('Process started inside containment');
    expect(fixture.nativeElement.textContent).not.toContain('RUN-2026-0118');
    expect(fixture.nativeElement.textContent).not.toContain('ข้อมูลจำลอง');
  });

  it('shows an unavailable state instead of fabricated jobs when the API fails', async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
    const request = http.expectOne('/api/jobs?limit=25');
    request.flush({}, { status: 503, statusText: 'Service Unavailable' });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('ยังเชื่อมต่อ Job Status API ไม่ได้');
    expect(fixture.nativeElement.textContent).not.toContain('RUN-2026-0118');
  });
});
