use std::collections::HashMap;
use js_sys::{Array, Float64Array, Object, Reflect};
use serde::{Deserialize, Serialize};
use wasm_bindgen::prelude::*;

use crate::csv_parser;
use crate::excel_parser;
use crate::formula;
use crate::map_parser;
use crate::session::{downsample_curve, nearest_sample, nearest_sample_2d, SessionStore};
use crate::tdms_parser;
use crate::types::{FilePreview, GlobalCalcDef, ParseSessionConfig, RawTable};

#[derive(Debug, Deserialize)]
struct SelectedLapInput {
    #[serde(rename = "sessionId")]
    session_id: String,
    #[serde(rename = "lapNumber")]
    lap_number: i32,
    color: String,
}

#[derive(Debug, Deserialize)]
struct PlotDataRequest {
    #[serde(rename = "xAxisSlug")]
    x_axis_slug: String,
    channels: Vec<String>,
    #[serde(rename = "selectedLaps")]
    selected_laps: Vec<SelectedLapInput>,
    #[serde(rename = "xMin")]
    x_min: Option<f64>,
    #[serde(rename = "xMax")]
    x_max: Option<f64>,
    #[serde(rename = "maxBuckets")]
    max_buckets: usize,
    #[serde(rename = "filterGaps")]
    filter_gaps: bool,
    #[serde(rename = "globalCalcs")]
    global_calcs: Vec<GlobalCalcDef>,
}

#[derive(Debug, Deserialize)]
struct HoveredLapInput {
    #[serde(rename = "sessionId")]
    session_id: String,
    #[serde(rename = "lapNumber")]
    lap_number: i32,
}

#[derive(Debug, Deserialize)]
struct HoveredPlotBounds {
    #[serde(rename = "channelSlug")]
    channel_slug: String,
    #[serde(rename = "hoveredLap")]
    hovered_lap: Option<HoveredLapInput>,
    #[serde(rename = "normalizeY")]
    normalize_y: Option<bool>,
    #[serde(rename = "channelExtents")]
    channel_extents: Option<HashMap<String, (f64, f64)>>,
    #[serde(rename = "targetY")]
    target_y: f64,
    #[serde(rename = "xMin")]
    x_min: f64,
    #[serde(rename = "xMax")]
    x_max: f64,
    #[serde(rename = "yMin")]
    y_min: f64,
    #[serde(rename = "yMax")]
    y_max: f64,
    #[serde(rename = "plotWidth")]
    plot_width: f64,
    #[serde(rename = "plotHeight")]
    plot_height: f64,
}

#[derive(Debug, Deserialize)]
struct CursorQueryRequest {
    #[serde(rename = "xAxisSlug")]
    x_axis_slug: String,
    channels: Vec<String>,
    #[serde(rename = "selectedLaps")]
    selected_laps: Vec<SelectedLapInput>,
    #[serde(rename = "targetX")]
    target_x: f64,
    hovered: Option<HoveredPlotBounds>,
    #[serde(rename = "globalCalcs")]
    global_calcs: Vec<GlobalCalcDef>,
}
#[derive(Debug, Serialize)]
struct InspectResult {
    #[serde(rename = "fileToken")]
    file_token: String,
    preview: FilePreview,
}

#[derive(Debug, Serialize)]
struct FormulaValidationResult {
    valid: bool,
    message: String,
    variables: Vec<String>,
}

#[derive(Debug, Serialize)]
struct TrackMapColumnsResult {
    #[serde(rename = "mapToken")]
    map_token: String,
    columns: Vec<String>,
}

#[derive(Debug, Serialize)]
struct CursorSampleItem {
    #[serde(rename = "lapKey")]
    lap_key: String,
    #[serde(rename = "sessionId")]
    session_id: String,
    #[serde(rename = "lapNumber")]
    lap_number: i32,
    color: String,
    #[serde(rename = "actualX")]
    actual_x: f64,
    #[serde(rename = "actualY")]
    actual_y: f64,
}

#[derive(Debug, Serialize)]
struct TrackMapDot {
    distance: f64,
    color: String,
}

#[derive(Debug, Serialize)]
struct CursorQueryResponse {
    #[serde(rename = "snappedX")]
    snapped_x: f64,
    #[serde(rename = "samplesByChannel")]
    samples_by_channel: HashMap<String, Vec<CursorSampleItem>>,
    #[serde(rename = "trackMapDots")]
    track_map_dots: Vec<TrackMapDot>,
}

fn file_ext_lower(file_name: &str) -> String {
    file_name
        .rsplit('.')
        .next()
        .map(|s| s.to_ascii_lowercase())
        .unwrap_or_default()
}

fn preview_by_ext(file_name: &str, bytes: &[u8]) -> Result<FilePreview, String> {
    match file_ext_lower(file_name).as_str() {
        "csv" => csv_parser::preview_csv(bytes, 5),
        "xlsx" | "xls" => excel_parser::preview_excel(bytes, 5),
        "tdms" => tdms_parser::preview_tdms(bytes, 5),
        other => Err(format!("Unsupported file format: .{other}")),
    }
}

fn parse_by_ext(file_name: &str, bytes: &[u8]) -> Result<RawTable, String> {
    match file_ext_lower(file_name).as_str() {
        "csv" => csv_parser::parse_csv(bytes),
        "xlsx" | "xls" => excel_parser::parse_excel(bytes),
        "tdms" => tdms_parser::parse_tdms(bytes),
        other => Err(format!("Unsupported file format: .{other}")),
    }
}

fn to_js_err(msg: impl ToString) -> JsValue {
    JsValue::from_str(&msg.to_string())
}

fn to_js_json<T: Serialize>(val: &T) -> Result<JsValue, JsValue> {
    val.serialize(&serde_wasm_bindgen::Serializer::json_compatible())
        .map_err(to_js_err)
}

#[wasm_bindgen]
pub struct TelemetryEngine {
    next_token: u64,
    pending_files: HashMap<String, (String, Vec<u8>)>,
    pending_maps: HashMap<String, (String, Vec<u8>)>,
    store: SessionStore,
}

impl Default for TelemetryEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[wasm_bindgen]
impl TelemetryEngine {
    #[wasm_bindgen(constructor)]
    pub fn new() -> Self {
        Self {
            next_token: 1,
            pending_files: HashMap::new(),
            pending_maps: HashMap::new(),
            store: SessionStore::new(),
        }
    }

    fn alloc_token(&mut self, prefix: &str) -> String {
        let id = self.next_token;
        self.next_token += 1;
        format!("{prefix}_{id}")
    }

    pub fn inspect_file(&mut self, file_name: &str, bytes: &[u8]) -> Result<JsValue, JsValue> {
        let preview = preview_by_ext(file_name, bytes).map_err(to_js_err)?;
        let token = self.alloc_token("file");
        self.pending_files
            .insert(token.clone(), (file_name.to_string(), bytes.to_vec()));
        let res = InspectResult {
            file_token: token,
            preview,
        };
        to_js_json(&res)
    }

    pub fn discard_pending_file(&mut self, file_token: &str) {
        self.pending_files.remove(file_token);
    }

    pub fn import_session(&mut self, file_token: &str, config_val: JsValue) -> Result<JsValue, JsValue> {
        let cfg: ParseSessionConfig =
            serde_wasm_bindgen::from_value(config_val).map_err(to_js_err)?;
        let (file_name, bytes) = self
            .pending_files
            .remove(file_token)
            .ok_or_else(|| to_js_err(format!("Pending file token '{file_token}' not found")))?;
        let raw = parse_by_ext(&file_name, &bytes).map_err(to_js_err)?;
        let summary = self.store.parse_from_raw(raw, cfg);
        to_js_json(&summary)
    }

    pub fn reparse_session(&mut self, session_id: &str, config_val: JsValue) -> Result<JsValue, JsValue> {
        let cfg: ParseSessionConfig =
            serde_wasm_bindgen::from_value(config_val).map_err(to_js_err)?;
        let summary = self.store.reparse_session(session_id, cfg).map_err(to_js_err)?;
        to_js_json(&summary)
    }

    pub fn remove_session(&mut self, session_id: &str) {
        self.store.sessions.remove(session_id);
    }

    pub fn clear_sessions(&mut self) {
        self.store.sessions.clear();
    }

    pub fn clear_calculated_cache(&mut self, calc_slugs_val: JsValue) -> Result<(), JsValue> {
        let slugs: Vec<String> = serde_wasm_bindgen::from_value(calc_slugs_val).map_err(to_js_err)?;
        self.store.clear_calculated_cache(&slugs);
        Ok(())
    }

    pub fn validate_formula(&self, expr: &str, expected_vars_val: JsValue) -> Result<JsValue, JsValue> {
        let expected_vars: Option<Vec<String>> = if expected_vars_val.is_undefined() || expected_vars_val.is_null() {
            None
        } else {
            Some(serde_wasm_bindgen::from_value(expected_vars_val).map_err(to_js_err)?)
        };

        let variables = formula::extract_variables(expr).unwrap_or_default();
        let res = match formula::validate_formula(expr, expected_vars.as_deref()) {
            Ok(()) => FormulaValidationResult {
                valid: true,
                message: "Formula is valid.".to_string(),
                variables,
            },
            Err(err) => FormulaValidationResult {
                valid: false,
                message: err,
                variables,
            },
        };
        to_js_json(&res)
    }

    pub fn parse_track_map_columns(&mut self, file_name: &str, bytes: &[u8]) -> Result<JsValue, JsValue> {
        let columns = map_parser::get_map_columns(bytes, file_name).map_err(to_js_err)?;
        let token = self.alloc_token("map");
        self.pending_maps
            .insert(token.clone(), (file_name.to_string(), bytes.to_vec()));
        let res = TrackMapColumnsResult {
            map_token: token,
            columns,
        };
        to_js_json(&res)
    }

    pub fn load_track_map_data(
        &mut self,
        map_token: &str,
        x_col: &str,
        y_col: &str,
        dist_col: Option<String>,
    ) -> Result<JsValue, JsValue> {
        let (file_name, bytes) = self
            .pending_maps
            .remove(map_token)
            .ok_or_else(|| to_js_err(format!("Pending map token '{map_token}' not found")))?;
        let data = map_parser::load_map_data(
            &bytes,
            &file_name,
            x_col,
            y_col,
            dist_col.as_deref(),
        )
        .map_err(to_js_err)?;
        to_js_json(&data)
    }

    pub fn discard_map_token(&mut self, map_token: &str) {
        self.pending_maps.remove(map_token);
    }

    pub fn get_plot_data(&mut self, req_val: JsValue) -> Result<JsValue, JsValue> {
        let req: PlotDataRequest = serde_wasm_bindgen::from_value(req_val).map_err(to_js_err)?;
        let global_map: HashMap<String, GlobalCalcDef> = req
            .global_calcs
            .into_iter()
            .map(|c| (c.slug.clone(), c))
            .collect();

        let curves_arr = Array::new();
        let mut x_global_min = f64::INFINITY;
        let mut x_global_max = f64::NEG_INFINITY;
        let mut y_extents: HashMap<String, (f64, f64)> = HashMap::new();

        for ch_slug in &req.channels {
            let mut ch_min = f64::INFINITY;
            let mut ch_max = f64::NEG_INFINITY;

            for lap_info in &req.selected_laps {
                let Some(raw_x) = self.store.get_lap_channel(
                    &lap_info.session_id,
                    lap_info.lap_number,
                    &req.x_axis_slug,
                    &global_map,
                ) else {
                    continue;
                };
                let Some(raw_y) = self.store.get_lap_channel(
                    &lap_info.session_id,
                    lap_info.lap_number,
                    ch_slug,
                    &global_map,
                ) else {
                    continue;
                };

                let n = raw_x.len().min(raw_y.len());
                if n == 0 {
                    continue;
                }

                // Update full extents across selected curves
                for i in 0..n {
                    let xv = raw_x[i];
                    let yv = raw_y[i];
                    if xv.is_finite() {
                        if xv < x_global_min {
                            x_global_min = xv;
                        }
                        if xv > x_global_max {
                            x_global_max = xv;
                        }
                    }
                    if yv.is_finite() {
                        if yv < ch_min {
                            ch_min = yv;
                        }
                        if yv > ch_max {
                            ch_max = yv;
                        }
                    }
                }

                let (gap_time, gap_dist, time_arr, dist_arr) = if req.filter_gaps {
                    let (gt, gd) = self
                        .store
                        .sessions
                        .get(&lap_info.session_id)
                        .map(|s| {
                            (
                                s.summary.gap_time_threshold.unwrap_or(1.0),
                                s.summary.gap_dist_threshold.unwrap_or(50.0),
                            )
                        })
                        .unwrap_or((1.0, 50.0));
                    let t_arr = self.store.get_lap_channel(
                        &lap_info.session_id,
                        lap_info.lap_number,
                        "lap_time",
                        &global_map,
                    );
                    let d_arr = self.store.get_lap_channel(
                        &lap_info.session_id,
                        lap_info.lap_number,
                        "lap_dist",
                        &global_map,
                    );
                    (Some(gt), Some(gd), t_arr, d_arr)
                } else {
                    (None, None, None, None)
                };

                let (dx, dy) = downsample_curve(
                    &raw_x[..n],
                    &raw_y[..n],
                    req.x_min,
                    req.x_max,
                    req.max_buckets.max(64),
                    time_arr.as_deref(),
                    dist_arr.as_deref(),
                    gap_time,
                    gap_dist,
                );

                let obj = Object::new();
                Reflect::set(&obj, &JsValue::from_str("channelSlug"), &JsValue::from_str(ch_slug))?;
                Reflect::set(&obj, &JsValue::from_str("sessionId"), &JsValue::from_str(&lap_info.session_id))?;
                Reflect::set(&obj, &JsValue::from_str("lapNumber"), &JsValue::from_f64(lap_info.lap_number as f64))?;
                Reflect::set(&obj, &JsValue::from_str("color"), &JsValue::from_str(&lap_info.color))?;
                let x_ta = Float64Array::from(dx.as_slice());
                let y_ta = Float64Array::from(dy.as_slice());
                Reflect::set(&obj, &JsValue::from_str("x"), &x_ta)?;
                Reflect::set(&obj, &JsValue::from_str("y"), &y_ta)?;
                curves_arr.push(&obj);
            }

            if ch_min.is_finite() && ch_max.is_finite() {
                if ch_min == ch_max {
                    ch_min -= 1.0;
                    ch_max += 1.0;
                }
                y_extents.insert(ch_slug.clone(), (ch_min, ch_max));
            }
        }

        let res_obj = Object::new();
        Reflect::set(&res_obj, &JsValue::from_str("curves"), &curves_arr)?;

        if x_global_min.is_finite() && x_global_max.is_finite() {
            if x_global_min == x_global_max {
                x_global_min -= 1.0;
                x_global_max += 1.0;
            }
            let x_ext = Array::new();
            x_ext.push(&JsValue::from_f64(x_global_min));
            x_ext.push(&JsValue::from_f64(x_global_max));
            Reflect::set(&res_obj, &JsValue::from_str("xExtent"), &x_ext)?;
        } else {
            Reflect::set(&res_obj, &JsValue::from_str("xExtent"), &JsValue::NULL)?;
        }

        let y_ext_obj = Object::new();
        for (ch, (ymin, ymax)) in y_extents {
            let pair = Array::new();
            pair.push(&JsValue::from_f64(ymin));
            pair.push(&JsValue::from_f64(ymax));
            Reflect::set(&y_ext_obj, &JsValue::from_str(&ch), &pair)?;
        }
        Reflect::set(&res_obj, &JsValue::from_str("yExtents"), &y_ext_obj)?;

        Ok(res_obj.into())
    }

    pub fn query_cursor(&mut self, req_val: JsValue) -> Result<JsValue, JsValue> {
        let req: CursorQueryRequest = serde_wasm_bindgen::from_value(req_val).map_err(to_js_err)?;
        let resp = resolve_cursor_query(&mut self.store, &req);
        to_js_json(&resp)
    }
}

fn resolve_cursor_query(store: &mut SessionStore, req: &CursorQueryRequest) -> CursorQueryResponse {
    let global_map: HashMap<String, GlobalCalcDef> = req
        .global_calcs
        .iter()
        .map(|c| (c.slug.clone(), c.clone()))
        .collect();

    let mut samples_by_channel: HashMap<String, Vec<CursorSampleItem>> = HashMap::new();
    let mut snapped_x = req.target_x;
    let mut snapped_by_lap_on_ch: HashMap<(String, i32), (f64, f64)> = HashMap::new();
    let mut snapped_ch_on_lap: Option<(String, i32, HashMap<String, (f64, f64)>)> = None;

    if let Some(hov) = &req.hovered {
        const MAX_SNAP_DIST_SQ: f64 = 25.0; // 5px radius
        let span_x = hov.x_max - hov.x_min;
        let span_y = hov.y_max - hov.y_min;
        if span_x > 0.0 && span_y > 0.0 && hov.plot_width > 0.0 && hov.plot_height > 0.0 {
            let px_per_x = hov.plot_width / span_x;

            if let Some(hlap) = &hov.hovered_lap {
                let mut snapped_by_ch: HashMap<String, (f64, f64)> = HashMap::new();
                let mut best_overall: Option<(f64, f64)> = None;
                let is_norm = hov.normalize_y.unwrap_or(false);

                if let Some(raw_x) = store.get_lap_channel(
                    &hlap.session_id,
                    hlap.lap_number,
                    &req.x_axis_slug,
                    &global_map,
                ) {
                    for ch_slug in &req.channels {
                        let Some(raw_y) = store.get_lap_channel(
                            &hlap.session_id,
                            hlap.lap_number,
                            ch_slug,
                            &global_map,
                        ) else {
                            continue;
                        };

                        let (ch_target_y, px_per_y) = if is_norm {
                            let Some(&(ch_min, ch_max)) =
                                hov.channel_extents.as_ref().and_then(|m| m.get(ch_slug))
                            else {
                                continue;
                            };
                            let ch_span = ch_max - ch_min;
                            if ch_span <= 0.0 || !ch_span.is_finite() {
                                continue;
                            }
                            (
                                ch_min + (hov.target_y / 100.0) * ch_span,
                                (hov.plot_height * 100.0) / (span_y * ch_span),
                            )
                        } else {
                            (hov.target_y, hov.plot_height / span_y)
                        };

                        if let Some((actual_x, actual_y, d2)) = nearest_sample_2d(
                            &raw_x,
                            &raw_y,
                            req.target_x,
                            ch_target_y,
                            hov.x_min,
                            hov.x_max,
                            px_per_x,
                            px_per_y,
                        ) {
                            if d2 <= MAX_SNAP_DIST_SQ {
                                snapped_by_ch.insert(ch_slug.clone(), (actual_x, actual_y));
                                if best_overall.map_or(true, |(bd2, _)| d2 < bd2) {
                                    best_overall = Some((d2, actual_x));
                                }
                            }
                        }
                    }
                }

                if let Some((_, best_x)) = best_overall {
                    snapped_x = best_x;
                }
                snapped_ch_on_lap = Some((hlap.session_id.clone(), hlap.lap_number, snapped_by_ch));
            } else {
                let px_per_y = hov.plot_height / span_y;
                let mut best_overall: Option<(f64, f64)> = None;

                for lap_info in &req.selected_laps {
                    let Some(raw_x) = store.get_lap_channel(
                        &lap_info.session_id,
                        lap_info.lap_number,
                        &req.x_axis_slug,
                        &global_map,
                    ) else {
                        continue;
                    };
                    let Some(raw_y) = store.get_lap_channel(
                        &lap_info.session_id,
                        lap_info.lap_number,
                        &hov.channel_slug,
                        &global_map,
                    ) else {
                        continue;
                    };

                    if let Some((actual_x, actual_y, d2)) = nearest_sample_2d(
                        &raw_x,
                        &raw_y,
                        req.target_x,
                        hov.target_y,
                        hov.x_min,
                        hov.x_max,
                        px_per_x,
                        px_per_y,
                    ) {
                        if d2 <= MAX_SNAP_DIST_SQ {
                            snapped_by_lap_on_ch.insert(
                                (lap_info.session_id.clone(), lap_info.lap_number),
                                (actual_x, actual_y),
                            );
                            if best_overall.map_or(true, |(bd2, _)| d2 < bd2) {
                                best_overall = Some((d2, actual_x));
                            }
                        }
                    }
                }

                if let Some((_, best_x)) = best_overall {
                    snapped_x = best_x;
                }
            }
        }
    }

    for ch_slug in &req.channels {
        let mut list = Vec::new();
        let is_hovered_channel = req
            .hovered
            .as_ref()
            .is_some_and(|h| h.hovered_lap.is_none() && h.channel_slug == *ch_slug);

        for lap_info in &req.selected_laps {
            let key = (lap_info.session_id.clone(), lap_info.lap_number);
            if is_hovered_channel {
                if let Some(&(actual_x, actual_y)) = snapped_by_lap_on_ch.get(&key) {
                    list.push(CursorSampleItem {
                        lap_key: format!("{}:{}", lap_info.session_id, lap_info.lap_number),
                        session_id: lap_info.session_id.clone(),
                        lap_number: lap_info.lap_number,
                        color: lap_info.color.clone(),
                        actual_x,
                        actual_y,
                    });
                    continue;
                }
            } else if let Some((h_sid, h_lap, map)) = &snapped_ch_on_lap {
                if *h_sid == lap_info.session_id && *h_lap == lap_info.lap_number {
                    if let Some(&(actual_x, actual_y)) = map.get(ch_slug) {
                        list.push(CursorSampleItem {
                            lap_key: format!("{}:{}", lap_info.session_id, lap_info.lap_number),
                            session_id: lap_info.session_id.clone(),
                            lap_number: lap_info.lap_number,
                            color: lap_info.color.clone(),
                            actual_x,
                            actual_y,
                        });
                        continue;
                    }
                }
            }

            let Some(raw_x) = store.get_lap_channel(
                &lap_info.session_id,
                lap_info.lap_number,
                &req.x_axis_slug,
                &global_map,
            ) else {
                continue;
            };
            let Some(raw_y) = store.get_lap_channel(
                &lap_info.session_id,
                lap_info.lap_number,
                ch_slug,
                &global_map,
            ) else {
                continue;
            };

            if let Some((actual_x, actual_y)) = nearest_sample(&raw_x, &raw_y, snapped_x) {
                list.push(CursorSampleItem {
                    lap_key: format!("{}:{}", lap_info.session_id, lap_info.lap_number),
                    session_id: lap_info.session_id.clone(),
                    lap_number: lap_info.lap_number,
                    color: lap_info.color.clone(),
                    actual_x,
                    actual_y,
                });
            }
        }
        samples_by_channel.insert(ch_slug.clone(), list);
    }

    let mut track_map_dots = Vec::new();
    for lap_info in &req.selected_laps {
        if req.x_axis_slug == "lap_dist" {
            if let Some(dist_arr) = store.get_lap_channel(
                &lap_info.session_id,
                lap_info.lap_number,
                "lap_dist",
                &global_map,
            ) {
                if !dist_arr.is_empty() {
                    let mut dmin = f64::INFINITY;
                    let mut dmax = f64::NEG_INFINITY;
                    for &v in &dist_arr {
                        if v.is_finite() {
                            if v < dmin { dmin = v; }
                            if v > dmax { dmax = v; }
                        }
                    }
                    if dmin.is_finite() && snapped_x >= dmin && snapped_x <= dmax {
                        track_map_dots.push(TrackMapDot {
                            distance: snapped_x,
                            color: lap_info.color.clone(),
                        });
                    }
                }
            }
        } else if let (Some(x_arr), Some(dist_arr)) = (
            store.get_lap_channel(
                &lap_info.session_id,
                lap_info.lap_number,
                &req.x_axis_slug,
                &global_map,
            ),
            store.get_lap_channel(
                &lap_info.session_id,
                lap_info.lap_number,
                "lap_dist",
                &global_map,
            ),
        ) {
            if let Some((_, dist_val)) = nearest_sample(&x_arr, &dist_arr, snapped_x) {
                track_map_dots.push(TrackMapDot {
                    distance: dist_val,
                    color: lap_info.color.clone(),
                });
            }
        }
    }

    CursorQueryResponse {
        snapped_x,
        samples_by_channel,
        track_map_dots,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::session::{StoredLap, StoredSession};
    use crate::types::{LapSummary, SessionSummary};

    #[test]
    fn test_resolve_cursor_query_hovered_lap_raw_and_normalized() {
        let mut store = SessionStore::default();
        let mut lap1_data = HashMap::new();
        lap1_data.insert("lap_dist".to_string(), vec![0.0, 5.0, 10.0]);
        lap1_data.insert("speed".to_string(), vec![10.0, 30.0, 10.0]); // peak 30 at x=5 (100% of [10,30])
        lap1_data.insert("power".to_string(), vec![0.0, 200.0, 800.0]); // 200 at x=5 (25% of [0,800])

        store.sessions.insert(
            "s1".to_string(),
            StoredSession {
                summary: SessionSummary {
                    id: "s1".to_string(),
                    name: "test.tdms".to_string(),
                    channels: vec!["lap_dist".to_string(), "speed".to_string(), "power".to_string()],
                    laps: vec![LapSummary {
                        lap_number: 1,
                        duration: 10.0,
                        distance: 10.0,
                        sample_count: 3,
                    }],
                    mapping: HashMap::new(),
                    local_calculated_channels: vec![],
                    preset_slug: None,
                    preset_name: None,
                    gap_time_threshold: None,
                    gap_dist_threshold: None,
                },
                raw_table: RawTable {
                    columns: vec![],
                    data: vec![],
                    row_count: 0,
                },
                laps: vec![StoredLap {
                    lap_number: 1,
                    duration: 10.0,
                    distance: 10.0,
                    sample_count: 3,
                    data: lap1_data,
                }],
            },
        );

        // 1. Raw By-Lap hover near (5.1, 202.0) snaps to power peak on Lap 1
        let req_raw = CursorQueryRequest {
            x_axis_slug: "lap_dist".to_string(),
            channels: vec!["speed".to_string(), "power".to_string()],
            selected_laps: vec![SelectedLapInput {
                session_id: "s1".to_string(),
                lap_number: 1,
                color: "#FF0000".to_string(),
            }],
            target_x: 5.02,
            hovered: Some(HoveredPlotBounds {
                channel_slug: String::new(),
                hovered_lap: Some(HoveredLapInput {
                    session_id: "s1".to_string(),
                    lap_number: 1,
                }),
                normalize_y: Some(false),
                channel_extents: None,
                target_y: 202.0,
                x_min: 0.0,
                x_max: 10.0,
                y_min: 0.0,
                y_max: 800.0,
                plot_width: 500.0,
                plot_height: 400.0,
            }),
            global_calcs: vec![],
        };
        let res_raw = resolve_cursor_query(&mut store, &req_raw);
        assert_eq!(res_raw.snapped_x, 5.0);
        assert_eq!(res_raw.samples_by_channel["speed"][0].actual_y, 30.0);
        assert_eq!(res_raw.samples_by_channel["power"][0].actual_y, 200.0);

        // 2. Normalized By-Lap hover at 99% near x=5.02 snaps to speed peak (100% -> actual 30.0)
        let mut extents = HashMap::new();
        extents.insert("speed".to_string(), (10.0, 30.0));
        extents.insert("power".to_string(), (0.0, 800.0));
        let req_norm = CursorQueryRequest {
            x_axis_slug: "lap_dist".to_string(),
            channels: vec!["speed".to_string(), "power".to_string()],
            selected_laps: vec![SelectedLapInput {
                session_id: "s1".to_string(),
                lap_number: 1,
                color: "#FF0000".to_string(),
            }],
            target_x: 5.02,
            hovered: Some(HoveredPlotBounds {
                channel_slug: String::new(),
                hovered_lap: Some(HoveredLapInput {
                    session_id: "s1".to_string(),
                    lap_number: 1,
                }),
                normalize_y: Some(true),
                channel_extents: Some(extents),
                target_y: 99.0,
                x_min: 0.0,
                x_max: 10.0,
                y_min: 0.0,
                y_max: 100.0,
                plot_width: 500.0,
                plot_height: 200.0,
            }),
            global_calcs: vec![],
        };
        let res_norm = resolve_cursor_query(&mut store, &req_norm);
        assert_eq!(res_norm.snapped_x, 5.0);
        assert_eq!(res_norm.samples_by_channel["speed"][0].actual_y, 30.0);
        assert_eq!(res_norm.samples_by_channel["power"][0].actual_y, 200.0);
    }
}
