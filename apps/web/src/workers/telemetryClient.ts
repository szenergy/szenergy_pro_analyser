import {
  ChannelGroupDef,
  FilePreview,
  MapData,
  ParseSessionConfig,
  SelectedLapInfo,
  SessionSummary,
} from '@/types/telemetry';
import {
  CursorQueryResponse,
  HoveredPlotBounds,
  PlotDataResponse,
  WorkerRequest,
  WorkerResponse,
} from '@/workers/protocol';

type PendingCall = {
  resolve: (value: unknown) => void;
  reject: (err: Error) => void;
};

export class TelemetryWorkerClient {
  private worker: Worker;
  private nextId = 1;
  private pending = new Map<number, PendingCall>();
  private readyPromise: Promise<void> | null = null;

  constructor() {
    this.worker = new Worker(new URL('./telemetry.worker.ts', import.meta.url), {
      type: 'module',
    });
    this.worker.onmessage = (ev: MessageEvent<WorkerResponse>) => {
      const msg = ev.data;
      const call = this.pending.get(msg.id);
      if (!call) return;
      this.pending.delete(msg.id);
      if (msg.ok) {
        call.resolve(msg.result);
      } else {
        call.reject(new Error(msg.error));
      }
    };
    this.worker.onerror = (ev) => {
      const err = new Error(ev.message || 'Telemetry worker error');
      for (const call of this.pending.values()) {
        call.reject(err);
      }
      this.pending.clear();
    };
  }

  public async init(): Promise<void> {
    if (!this.readyPromise) {
      this.readyPromise = this.request<void>({ type: 'init' });
    }
    return this.readyPromise;
  }

  private request<T>(
    payload: WorkerRequest extends infer R ? (R extends WorkerRequest ? Omit<R, 'id'> : never) : never,
    transfer: Transferable[] = [],
  ): Promise<T> {
    const id = this.nextId++;
    const msg = { ...payload, id } as WorkerRequest;
    const { promise, resolve, reject } = Promise.withResolvers<T>();
    this.pending.set(id, {
      resolve: resolve as (v: unknown) => void,
      reject,
    });
    this.worker.postMessage(msg, transfer);
    return promise;
  }

  public async inspectFile(file: File): Promise<{ fileToken: string; preview: FilePreview }> {
    await this.init();
    const buffer = await file.arrayBuffer();
    return this.request(
      { type: 'inspectFile', fileName: file.name, buffer },
      [buffer],
    );
  }

  public async inspectExcelSheet(
    fileToken: string,
    sheetName: string,
  ): Promise<{ fileToken: string; preview: FilePreview }> {
    await this.init();
    return this.request({ type: 'inspectExcelSheet', fileToken, sheetName });
  }

  public async getSessionSheetPreview(
    sessionId: string,
    sheetName?: string,
  ): Promise<FilePreview> {
    await this.init();
    return this.request({ type: 'getSessionSheetPreview', sessionId, sheetName });
  }

  public async discardPendingFile(fileToken: string): Promise<void> {
    await this.init();
    return this.request({ type: 'discardPendingFile', fileToken });
  }

  public async importSession(fileToken: string, config: ParseSessionConfig): Promise<SessionSummary> {
    await this.init();
    return this.request({ type: 'importSession', fileToken, config });
  }

  public async reparseSession(sessionId: string, config: ParseSessionConfig): Promise<SessionSummary> {
    await this.init();
    return this.request({ type: 'reparseSession', sessionId, config });
  }

  public async removeSession(sessionId: string): Promise<void> {
    await this.init();
    return this.request({ type: 'removeSession', sessionId });
  }

  public async clearSessions(): Promise<void> {
    await this.init();
    return this.request({ type: 'clearSessions' });
  }

  public async parseTrackMapColumns(file: File): Promise<{ mapToken: string; columns: string[] }> {
    await this.init();
    const buffer = await file.arrayBuffer();
    return this.request(
      { type: 'parseTrackMapColumns', fileName: file.name, buffer },
      [buffer],
    );
  }

  public async loadTrackMapData(
    mapToken: string,
    fileName: string,
    xCol: string,
    yCol: string,
    distCol: string | null,
  ): Promise<MapData> {
    await this.init();
    return this.request({
      type: 'loadTrackMapData',
      mapToken,
      fileName,
      xCol,
      yCol,
      distCol,
    });
  }

  public async discardMapToken(mapToken: string): Promise<void> {
    await this.init();
    return this.request({ type: 'discardMapToken', mapToken });
  }

  public async getPlotData(params: {
    xAxisSlug: string;
    channels: string[];
    selectedLaps: SelectedLapInfo[];
    xMin: number | null;
    xMax: number | null;
    maxBuckets: number;
    filterGaps: boolean;
    channelGroups: ChannelGroupDef[];
  }): Promise<PlotDataResponse> {
    await this.init();
    return this.request({ type: 'getPlotData', ...params });
  }

  public async queryCursor(params: {
    xAxisSlug: string;
    channels: string[];
    selectedLaps: SelectedLapInfo[];
    targetX: number;
    hovered?: HoveredPlotBounds | null;
    channelGroups: ChannelGroupDef[];
  }): Promise<CursorQueryResponse> {
    await this.init();
    return this.request({ type: 'queryCursor', ...params });
  }

  public dispose() {
    this.worker.terminate();
  }
}

export const telemetryClient = new TelemetryWorkerClient();
