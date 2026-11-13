import initWasm, { TelemetryEngine } from '@/wasm/telemetry_core';
import { WorkerRequest, WorkerResponse } from '@/workers/protocol';

let engine: TelemetryEngine | null = null;
let initPromise: Promise<void> | null = null;

async function ensureEngine(): Promise<TelemetryEngine> {
  if (!initPromise) {
    initPromise = (async () => {
      await initWasm();
      engine = new TelemetryEngine();
    })();
  }
  await initPromise;
  if (!engine) {
    throw new Error('Failed to initialize TelemetryEngine WASM module');
  }
  return engine;
}

function respondOk(id: number, result: unknown, transfer: Transferable[] = []) {
  const msg: WorkerResponse = { id, ok: true, result };
  self.postMessage(msg, { transfer });
}

function respondErr(id: number, err: unknown) {
  const message =
    err instanceof Error ? err.message : typeof err === 'string' ? err : String(err);
  const msg: WorkerResponse = { id, ok: false, error: message };
  self.postMessage(msg);
}

self.onmessage = async (ev: MessageEvent<WorkerRequest>) => {
  const req = ev.data;
  try {
    const eng = await ensureEngine();
    switch (req.type) {
      case 'init': {
        respondOk(req.id, null);
        return;
      }
      case 'inspectFile': {
        const bytes = new Uint8Array(req.buffer);
        const res = eng.inspect_file(req.fileName, bytes);
        respondOk(req.id, res);
        return;
      }
      case 'discardPendingFile': {
        eng.discard_pending_file(req.fileToken);
        respondOk(req.id, null);
        return;
      }
      case 'importSession': {
        const res = eng.import_session(req.fileToken, req.config);
        respondOk(req.id, res);
        return;
      }
      case 'reparseSession': {
        const res = eng.reparse_session(req.sessionId, req.config);
        respondOk(req.id, res);
        return;
      }
      case 'removeSession': {
        eng.remove_session(req.sessionId);
        respondOk(req.id, null);
        return;
      }
      case 'clearSessions': {
        eng.clear_sessions();
        respondOk(req.id, null);
        return;
      }
      case 'clearCalculatedCache': {
        eng.clear_calculated_cache(req.calcSlugs);
        respondOk(req.id, null);
        return;
      }
      case 'validateFormula': {
        const res = eng.validate_formula(req.formula, req.expectedVars ?? null);
        respondOk(req.id, res);
        return;
      }
      case 'parseTrackMapColumns': {
        const bytes = new Uint8Array(req.buffer);
        const res = eng.parse_track_map_columns(req.fileName, bytes);
        respondOk(req.id, res);
        return;
      }
      case 'loadTrackMapData': {
        const res = eng.load_track_map_data(
          req.mapToken,
          req.xCol,
          req.yCol,
          req.distCol,
        );
        respondOk(req.id, res);
        return;
      }
      case 'discardMapToken': {
        eng.discard_map_token(req.mapToken);
        respondOk(req.id, null);
        return;
      }
      case 'getPlotData': {
        const res = eng.get_plot_data({
          xAxisSlug: req.xAxisSlug,
          channels: req.channels,
          selectedLaps: req.selectedLaps,
          xMin: req.xMin,
          xMax: req.xMax,
          maxBuckets: req.maxBuckets,
          filterGaps: req.filterGaps,
          globalCalcs: req.globalCalcs,
        }) as {
          curves?: Array<{ x: Float64Array; y: Float64Array }>;
        };
        const transfer: Transferable[] = [];
        if (res?.curves) {
          for (const c of res.curves) {
            if (c.x?.buffer) transfer.push(c.x.buffer);
            if (c.y?.buffer) transfer.push(c.y.buffer);
          }
        }
        respondOk(req.id, res, transfer);
        return;
      }
      case 'queryCursor': {
        const res = eng.query_cursor({
          xAxisSlug: req.xAxisSlug,
          channels: req.channels,
          selectedLaps: req.selectedLaps,
          targetX: req.targetX,
          hovered: req.hovered ?? null,
          globalCalcs: req.globalCalcs,
        });
        respondOk(req.id, res);
        return;
      }
    }
  } catch (err) {
    respondErr(req.id, err);
  }
};
