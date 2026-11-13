import { Component, DestroyRef, Input, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, catchError, switchMap, tap, timer } from 'rxjs';
import { ChatApi, JobState, JobSummary, UiLanguage } from '../chat/chat-api';

const ACTIVE_STATES = new Set<JobState>([
  'QUEUED',
  'STARTING',
  'RUNNING',
  'VERIFYING',
  'REBOOT_REQUIRED',
  'CANCEL_REQUESTED',
]);

@Component({
  selector: 'app-job-monitor',
  standalone: true,
  templateUrl: './job-monitor.html',
})
export class JobMonitorComponent implements OnInit {
  @Input() language: UiLanguage = 'th';

  private readonly api = inject(ChatApi);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly tab = signal<'active' | 'history'>('active');
  protected readonly query = signal('');
  protected readonly selectedId = signal<string | null>(null);
  protected readonly jobs = signal<JobSummary[]>([]);
  protected readonly apiStatus = signal<'loading' | 'connected' | 'unavailable'>('loading');
  protected readonly lastCheckedAt = signal<string | null>(null);

  protected readonly activeJobs = computed(() =>
    this.jobs().filter((job) => ACTIVE_STATES.has(job.state)),
  );
  protected readonly historyJobs = computed(() =>
    this.jobs().filter((job) => !ACTIVE_STATES.has(job.state)),
  );
  protected readonly visibleJobs = computed(() => {
    const rows = this.tab() === 'active' ? this.activeJobs() : this.historyJobs();
    const query = this.query().trim().toLowerCase();
    return rows.filter((job) =>
      !query || [job.job_id, job.tool_id].some((value) => value.toLowerCase().includes(query)),
    );
  });
  protected readonly selected = computed(() => {
    const rows = this.visibleJobs();
    return rows.find((job) => job.job_id === this.selectedId()) ?? rows[0] ?? null;
  });
  protected readonly runningCount = computed(() =>
    this.jobs().filter((job) => job.state === 'RUNNING' || job.state === 'STARTING').length,
  );
  protected readonly queuedCount = computed(() =>
    this.jobs().filter((job) => job.state === 'QUEUED').length,
  );
  protected readonly verifyingCount = computed(() =>
    this.jobs().filter((job) => job.state === 'VERIFYING' || job.state === 'REBOOT_REQUIRED').length,
  );
  protected readonly failedCount = computed(() =>
    this.jobs().filter((job) => job.state === 'FAILED' || job.state === 'UNKNOWN').length,
  );

  ngOnInit(): void {
    timer(0, 5000)
      .pipe(
        switchMap(() =>
          this.api.getJobs(25).pipe(
            tap((response) => {
              this.jobs.set(response.jobs);
              this.lastCheckedAt.set(response.checked_at);
              this.apiStatus.set('connected');
              if (!this.selectedId() && response.jobs.length > 0) {
                this.selectedId.set(response.jobs[0].job_id);
              }
            }),
            catchError(() => {
              this.apiStatus.set('unavailable');
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }

  protected isThai(): boolean {
    return this.language === 'th';
  }

  protected stateLabel(state: JobState): string {
    const th: Record<JobState, string> = {
      QUEUED: 'รอคิว',
      STARTING: 'กำลังเริ่มงาน',
      RUNNING: 'กำลังทำงาน',
      VERIFYING: 'กำลังตรวจสอบผล',
      REBOOT_REQUIRED: 'รอรีสตาร์ต',
      CANCEL_REQUESTED: 'กำลังยกเลิก',
      SUCCEEDED: 'สำเร็จ',
      FAILED: 'ล้มเหลว',
      CANCELLED: 'ยกเลิกแล้ว',
      UNKNOWN: 'ไม่ทราบผล',
    };
    const en: Record<JobState, string> = {
      QUEUED: 'Queued',
      STARTING: 'Starting',
      RUNNING: 'Running',
      VERIFYING: 'Verifying',
      REBOOT_REQUIRED: 'Reboot required',
      CANCEL_REQUESTED: 'Cancelling',
      SUCCEEDED: 'Succeeded',
      FAILED: 'Failed',
      CANCELLED: 'Cancelled',
      UNKNOWN: 'Unknown',
    };
    return (this.isThai() ? th : en)[state];
  }

  protected stateClass(state: JobState): string {
    return state.toLowerCase();
  }

  protected jobTitle(toolId: string): string {
    const known: Record<string, string> = {
      'software.install': this.isThai() ? 'ติดตั้งซอฟต์แวร์' : 'Install software',
      'software.remove': this.isThai() ? 'ถอนการติดตั้งซอฟต์แวร์' : 'Remove software',
    };
    return known[toolId] ?? toolId;
  }

  protected formatTime(value: string | null): string {
    if (!value) return this.isThai() ? '—' : '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString(this.isThai() ? 'th-TH' : 'en-US');
  }

  protected setTab(tab: 'active' | 'history'): void {
    this.tab.set(tab);
    this.selectedId.set(null);
  }

  protected selectJob(jobId: string): void {
    this.selectedId.set(jobId);
  }

  protected refresh(): void {
    this.api.getJobs(25).subscribe({
      next: (response) => {
        this.jobs.set(response.jobs);
        this.lastCheckedAt.set(response.checked_at);
        this.apiStatus.set('connected');
      },
      error: () => this.apiStatus.set('unavailable'),
    });
  }
}
