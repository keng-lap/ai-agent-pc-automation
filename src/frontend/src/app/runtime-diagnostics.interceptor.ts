import { HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { EMPTY, catchError, throwError } from 'rxjs';
import { RuntimeDiagnosticsState } from './runtime-diagnostics.state';

const BROWSER_EVENT_PATH = '/api/diagnostics/browser-events';

export const runtimeDiagnosticsInterceptor: HttpInterceptorFn = (request, next) => {
  const http = inject(HttpClient);
  const diagnosticsState = inject(RuntimeDiagnosticsState);
  const correlationId = request.headers.get('X-Correlation-ID') ?? globalThis.crypto.randomUUID();
  const correlatedRequest = request.clone({
    setHeaders: {
      'X-Correlation-ID': correlationId,
      'X-Workflow-ID': diagnosticsState.workflowId,
    },
  });

  return next(correlatedRequest).pipe(
    catchError((error: unknown) => {
      if (diagnosticsState.enabled && request.url.startsWith('/api/') && !request.url.includes(BROWSER_EVENT_PATH)) {
        const statusCode = error instanceof HttpErrorResponse && error.status > 0
          ? error.status
          : null;
        http.post(
          BROWSER_EVENT_PATH,
          {
            event_code: 'BROWSER_API_FAILURE',
            component: 'api',
            status_code: statusCode,
          },
          { headers: { 'X-Correlation-ID': correlationId } },
        ).pipe(catchError(() => EMPTY)).subscribe();
      }
      return throwError(() => error);
    }),
  );
};
