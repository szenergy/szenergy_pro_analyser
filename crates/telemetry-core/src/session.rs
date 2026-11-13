use std::collections::{BTreeMap, HashMap, HashSet};

use crate::formula::evaluate_formula;
use crate::types::{
    GlobalCalcDef, LapSummary, ParseSessionConfig, RawTable, SessionSummary,
};

#[derive(Debug, Clone)]
pub struct StoredLap {
    pub lap_number: i32,
    pub duration: f64,
    pub distance: f64,
    pub sample_count: usize,
    pub data: HashMap<String, Vec<f64>>,
}

#[derive(Debug, Clone)]
pub struct StoredSession {
    pub summary: SessionSummary,
    pub raw_table: RawTable,
    pub laps: Vec<StoredLap>,
}

#[derive(Debug, Default)]
pub struct SessionStore {
    pub sessions: HashMap<String, StoredSession>,
}

fn resolve_key_case_insensitive<'a, V>(map: &'a HashMap<String, V>, target: &str) -> Option<&'a str> {
    if target.is_empty() {
        return None;
    }
    if let Some((k, _)) = map.get_key_value(target) {
        return Some(k.as_str());
    }
    let norm_target = target.trim().to_lowercase();
    let norm_target_us = norm_target.replace(' ', "_");
    for k in map.keys() {
        let kl = k.trim().to_lowercase();
        let kl_us = k.trim().replace(' ', "_").to_lowercase();
        if kl == norm_target || kl_us == norm_target || kl_us == norm_target_us {
            return Some(k.as_str());
        }
    }
    None
}

fn compute_valid_span(values: &[f64]) -> f64 {
    let mut first: Option<f64> = None;
    let mut last: Option<f64> = None;
    let mut count = 0usize;
    for &v in values {
        if v.is_finite() {
            if first.is_none() {
                first = Some(v);
            }
            last = Some(v);
            count += 1;
        }
    }
    if count >= 2 {
        if let (Some(f), Some(l)) = (first, last) {
            return (l - f).max(0.0);
        }
    }
    0.0
}

fn normalize_len(mut vec: Vec<f64>, target_len: usize) -> Vec<f64> {
    if vec.len() == target_len {
        return vec;
    }
    if target_len == 0 {
        vec.clear();
        return vec;
    }
    if vec.len() == 1 {
        return vec![vec[0]; target_len];
    }
    if vec.len() > target_len {
        vec.truncate(target_len);
    } else {
        let pad_val = vec.last().copied().unwrap_or(f64::NAN);
        vec.resize(target_len, pad_val);
    }
    vec
}

impl SessionStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn parse_from_raw(&mut self, raw: RawTable, cfg: ParseSessionConfig) -> SessionSummary {
        let mut calc_col_names: HashSet<String> = HashSet::new();
        for calc in &cfg.local_calculated_channels {
            if !calc.target_slug.is_empty() {
                calc_col_names.insert(calc.target_slug.clone());
            }
            if !calc.name.is_empty() {
                calc_col_names.insert(calc.name.clone());
            }
            if !calc.target_label.is_empty() {
                calc_col_names.insert(calc.target_label.clone());
            }
        }

        // Clean raw_table so local calculated channels never pollute raw_table or mapping
        let mut clean_columns = Vec::with_capacity(raw.columns.len());
        let mut clean_data = Vec::with_capacity(raw.data.len());
        for (col_name, col_vec) in raw.columns.into_iter().zip(raw.data.into_iter()) {
            if !calc_col_names.contains(&col_name) {
                clean_columns.push(col_name);
                clean_data.push(col_vec);
            }
        }
        let clean_raw = RawTable {
            columns: clean_columns,
            data: clean_data,
            row_count: raw.row_count,
        };

        let target_len = clean_raw.row_count;

        // Build working map for sequential local calculated channel evaluation
        let mut working_cols: HashMap<String, Vec<f64>> =
            HashMap::with_capacity(clean_raw.columns.len() + cfg.local_calculated_channels.len() * 2);
        for (col_name, col_vec) in clean_raw.columns.iter().zip(clean_raw.data.iter()) {
            working_cols.insert(col_name.clone(), col_vec.clone());
        }

        for calc in &cfg.local_calculated_channels {
            let target_slug = calc.target_slug.trim();
            let formula = calc.formula.trim();
            if target_slug.is_empty() || formula.is_empty() {
                continue;
            }

            let mut missing_input = false;
            let mut input_refs: HashMap<String, &[f64]> = HashMap::with_capacity(calc.inputs.len());
            for (var_name, raw_col) in &calc.inputs {
                if let Some(arr) = working_cols.get(raw_col) {
                    input_refs.insert(var_name.clone(), arr.as_slice());
                } else {
                    missing_input = true;
                    break;
                }
            }
            if missing_input {
                continue;
            }

            if let Ok(result) = evaluate_formula(formula, &input_refs, target_len) {
                let normalized = normalize_len(result, target_len);
                if !calc.name.is_empty() && calc.name != target_slug {
                    working_cols.insert(calc.name.clone(), normalized.clone());
                }
                working_cols.insert(target_slug.to_string(), normalized);
            }
        }

        // Filter mapping to existing clean raw columns
        let mut valid_mapping: HashMap<String, String> = HashMap::new();
        for (raw_col, slug) in &cfg.mapping {
            if !slug.is_empty()
                && !calc_col_names.contains(raw_col)
                && clean_raw.column_index(raw_col).is_some()
            {
                valid_mapping.insert(raw_col.clone(), slug.clone());
            }
        }

        // Map columns to slugs in deterministic order (raw column order, then local calcs)
        let mut mapped_cols: HashMap<String, Vec<f64>> = HashMap::new();
        let mut ordered_slugs: Vec<String> = Vec::new();
        let mut seen_slugs: HashSet<String> = HashSet::new();

        for raw_col in &clean_raw.columns {
            if let Some(slug) = valid_mapping.get(raw_col) {
                if let Some(col_vec) = working_cols.get(raw_col) {
                    mapped_cols.insert(slug.clone(), col_vec.clone());
                    if seen_slugs.insert(slug.clone()) {
                        ordered_slugs.push(slug.clone());
                    }
                }
            }
        }

        for calc in &cfg.local_calculated_channels {
            let target_slug = calc.target_slug.trim();
            if !target_slug.is_empty() {
                if let Some(col_vec) = working_cols.get(target_slug) {
                    mapped_cols.insert(target_slug.to_string(), col_vec.clone());
                    if seen_slugs.insert(target_slug.to_string()) {
                        ordered_slugs.push(target_slug.to_string());
                    }
                }
            }
        }

        let resolved_lap = resolve_key_case_insensitive(&mapped_cols, &cfg.lap_slug).map(str::to_string);
        let resolved_time = resolve_key_case_insensitive(&mapped_cols, &cfg.time_slug).map(str::to_string);
        let resolved_dist = resolve_key_case_insensitive(&mapped_cols, &cfg.dist_slug).map(str::to_string);

        let channels: Vec<String> = ordered_slugs
            .into_iter()
            .filter(|slug| resolved_lap.as_deref() != Some(slug.as_str()))
            .collect();

        let mut stored_laps: Vec<StoredLap> = Vec::new();

        if target_len > 0 {
            match &resolved_lap {
                None => {
                    let duration = resolved_time
                        .as_ref()
                        .and_then(|k| mapped_cols.get(k))
                        .map(|v| compute_valid_span(v))
                        .unwrap_or(0.0);
                    let distance = resolved_dist
                        .as_ref()
                        .and_then(|k| mapped_cols.get(k))
                        .map(|v| compute_valid_span(v))
                        .unwrap_or(0.0);

                    stored_laps.push(StoredLap {
                        lap_number: 1,
                        duration,
                        distance,
                        sample_count: target_len,
                        data: mapped_cols,
                    });
                }
                Some(lap_key) => {
                    let lap_vec = &mapped_cols[lap_key];
                    let mut lap_groups: BTreeMap<i32, Vec<usize>> = BTreeMap::new();
                    for (idx, &val) in lap_vec.iter().enumerate() {
                        if val.is_finite() {
                            let lap_num = val as i32;
                            lap_groups.entry(lap_num).or_default().push(idx);
                        }
                    }

                    if lap_groups.is_empty() {
                        let mut data = mapped_cols;
                        data.remove(lap_key);
                        stored_laps.push(StoredLap {
                            lap_number: 1,
                            duration: 0.0,
                            distance: 0.0,
                            sample_count: target_len,
                            data,
                        });
                    } else {
                        for (lap_num, indices) in lap_groups {
                            let mut lap_data: HashMap<String, Vec<f64>> =
                                HashMap::with_capacity(mapped_cols.len());
                            for (slug, col_vec) in &mapped_cols {
                                if slug == lap_key {
                                    continue;
                                }
                                let mut slice = Vec::with_capacity(indices.len());
                                for &row_idx in &indices {
                                    slice.push(col_vec[row_idx]);
                                }
                                lap_data.insert(slug.clone(), slice);
                            }

                            let duration = resolved_time
                                .as_ref()
                                .and_then(|k| lap_data.get(k))
                                .map(|v| compute_valid_span(v))
                                .unwrap_or(0.0);
                            let distance = resolved_dist
                                .as_ref()
                                .and_then(|k| lap_data.get(k))
                                .map(|v| compute_valid_span(v))
                                .unwrap_or(0.0);

                            stored_laps.push(StoredLap {
                                lap_number: lap_num,
                                duration,
                                distance,
                                sample_count: indices.len(),
                                data: lap_data,
                            });
                        }
                    }
                }
            }
        }

        let lap_summaries: Vec<LapSummary> = stored_laps
            .iter()
            .map(|l| LapSummary {
                lap_number: l.lap_number,
                duration: l.duration,
                distance: l.distance,
                sample_count: l.sample_count,
            })
            .collect();

        let summary = SessionSummary {
            id: cfg.session_id.clone(),
            name: cfg.file_name.clone(),
            channels,
            laps: lap_summaries,
            mapping: valid_mapping,
            local_calculated_channels: cfg.local_calculated_channels,
            preset_slug: cfg.preset_slug,
            preset_name: cfg.preset_name,
            gap_time_threshold: cfg.gap_time_threshold,
            gap_dist_threshold: cfg.gap_dist_threshold,
        };

        let stored = StoredSession {
            summary: summary.clone(),
            raw_table: clean_raw,
            laps: stored_laps,
        };
        self.sessions.insert(cfg.session_id, stored);
        summary
    }

    pub fn reparse_session(
        &mut self,
        session_id: &str,
        mut cfg: ParseSessionConfig,
    ) -> Result<SessionSummary, String> {
        let raw_table = self
            .sessions
            .get(session_id)
            .map(|s| s.raw_table.clone())
            .ok_or_else(|| format!("Session '{}' not found", session_id))?;
        cfg.session_id = session_id.to_string();
        Ok(self.parse_from_raw(raw_table, cfg))
    }

    pub fn get_lap_channel<'a>(
        &mut self,
        session_id: &str,
        lap_num: i32,
        slug: &str,
        global_calcs: &HashMap<String, GlobalCalcDef>,
    ) -> Option<Vec<f64>> {
        if slug.is_empty() {
            return None;
        }
        let session = self.sessions.get_mut(session_id)?;
        let lap = session.laps.iter_mut().find(|l| l.lap_number == lap_num)?;

        if let Some(key) = resolve_key_case_insensitive(&lap.data, slug) {
            return lap.data.get(key).cloned();
        }

        let mut visited = HashSet::new();
        compute_global_calc(lap, slug, global_calcs, &mut visited)
    }

    pub fn clear_calculated_cache(&mut self, calc_slugs: &[String]) {
        if calc_slugs.is_empty() {
            return;
        }
        for session in self.sessions.values_mut() {
            for lap in &mut session.laps {
                for slug in calc_slugs {
                    lap.data.remove(slug);
                }
            }
        }
    }
}

fn compute_global_calc(
    lap: &mut StoredLap,
    slug: &str,
    global_calcs: &HashMap<String, GlobalCalcDef>,
    visited: &mut HashSet<String>,
) -> Option<Vec<f64>> {
    if visited.contains(slug) {
        return None;
    }

    let calc_def = global_calcs.get(slug)?;
    if calc_def.kind != "calculated" {
        return None;
    }

    let formula = calc_def.formula.trim();
    if formula.is_empty() || calc_def.inputs.is_empty() {
        return None;
    }

    visited.insert(slug.to_string());

    let mut resolved_inputs: Vec<(String, Vec<f64>)> = Vec::with_capacity(calc_def.inputs.len());
    let mut target_len: Option<usize> = None;

    for (var_name, input_slug) in &calc_def.inputs {
        if input_slug.is_empty() {
            visited.remove(slug);
            return None;
        }

        let arr_opt = if let Some(key) = resolve_key_case_insensitive(&lap.data, input_slug) {
            lap.data.get(key).cloned()
        } else {
            compute_global_calc(lap, input_slug, global_calcs, visited)
        };

        let mut arr = match arr_opt {
            Some(a) if !a.is_empty() => a,
            _ => {
                visited.remove(slug);
                return None;
            }
        };

        match target_len {
            None => target_len = Some(arr.len()),
            Some(len) if arr.len() != len => {
                arr = normalize_len(arr, len);
            }
            _ => {}
        }

        resolved_inputs.push((var_name.clone(), arr));
    }

    visited.remove(slug);

    let len = target_len?;
    let input_refs: HashMap<String, &[f64]> = resolved_inputs
        .iter()
        .map(|(k, v)| (k.clone(), v.as_slice()))
        .collect();

    let result = evaluate_formula(formula, &input_refs, len).ok()?;
    lap.data.insert(slug.to_string(), result.clone());
    Some(result)
}

pub fn downsample_curve(
    x: &[f64],
    y: &[f64],
    x_min: Option<f64>,
    x_max: Option<f64>,
    max_buckets: usize,
    time_arr: Option<&[f64]>,
    dist_arr: Option<&[f64]>,
    gap_time: Option<f64>,
    gap_dist: Option<f64>,
) -> (Vec<f64>, Vec<f64>) {
    let n = x.len().min(y.len());
    if n == 0 {
        return (Vec::new(), Vec::new());
    }

    let filter_range = x_min.is_some() || x_max.is_some();
    let lo = x_min.unwrap_or(f64::NEG_INFINITY);
    let hi = x_max.unwrap_or(f64::INFINITY);

    let in_bounds = |v: f64| v.is_finite() && v >= lo && v <= hi;
    let seg_overlaps = |a: f64, b: f64| a.is_finite() && b.is_finite() && a.min(b) <= hi && a.max(b) >= lo;

    let gap_enabled = gap_time.is_some() || gap_dist.is_some();

    let mut fx = Vec::new();
    let mut fy = Vec::new();

    if !filter_range && !gap_enabled {
        fx.extend_from_slice(&x[..n]);
        fy.extend_from_slice(&y[..n]);
    } else {
        let mut prev_kept: Option<usize> = None;

        for i in 0..n {
            let keep = if !filter_range {
                true
            } else {
                in_bounds(x[i])
                    || (i + 1 < n && seg_overlaps(x[i], x[i + 1]))
                    || (i > 0 && seg_overlaps(x[i - 1], x[i]))
                    || (!x[i].is_finite()
                        && i > 0
                        && i + 1 < n
                        && in_bounds(x[i - 1])
                        && in_bounds(x[i + 1]))
            };

            if !keep {
                continue;
            }

            if gap_enabled {
                let curr_finite = x[i].is_finite() && y[i].is_finite();
                if let Some(prev) = prev_kept {
                    let prev_finite = x[prev].is_finite() && y[prev].is_finite();
                    let mut connected = prev_finite && curr_finite && i == prev + 1;
                    if connected {
                        let dx = x[i] - x[prev];
                        if !dx.is_finite() || dx < 0.0 {
                            connected = false;
                        }
                    }
                    if connected {
                        if let (Some(gt), Some(t)) = (gap_time, time_arr) {
                            if i < t.len() && prev < t.len() {
                                let dt = t[i] - t[prev];
                                if !dt.is_finite() || dt < 0.0 || dt > gt {
                                    connected = false;
                                }
                            }
                        }
                    }
                    if connected {
                        if let (Some(gd), Some(d)) = (gap_dist, dist_arr) {
                            if i < d.len() && prev < d.len() {
                                let dd = d[i] - d[prev];
                                if !dd.is_finite() || dd < 0.0 || dd > gd {
                                    connected = false;
                                }
                            }
                        }
                    }
                    if !connected {
                        let last_is_finite = fx
                            .last()
                            .zip(fy.last())
                            .map_or(false, |(lx, ly)| lx.is_finite() && ly.is_finite());
                        if last_is_finite {
                            fx.push(f64::NAN);
                            fy.push(f64::NAN);
                        }
                    }
                }
                if curr_finite {
                    fx.push(x[i]);
                    fy.push(y[i]);
                } else {
                    let last_is_finite = fx
                        .last()
                        .zip(fy.last())
                        .map_or(true, |(lx, ly)| lx.is_finite() && ly.is_finite());
                    if last_is_finite {
                        fx.push(f64::NAN);
                        fy.push(f64::NAN);
                    }
                }
            } else {
                fx.push(x[i]);
                fy.push(y[i]);
            }

            prev_kept = Some(i);
        }
    }

    let m = fx.len();
    if max_buckets == 0 || m <= max_buckets.saturating_mul(2) {
        return (fx, fy);
    }

    let mut out_x = Vec::with_capacity(max_buckets.saturating_mul(2) + 8);
    let mut out_y = Vec::with_capacity(max_buckets.saturating_mul(2) + 8);
    let mut last_pushed_idx: Option<usize> = None;

    let push_break = |ox: &mut Vec<f64>, oy: &mut Vec<f64>| {
        let last_finite = ox
            .last()
            .zip(oy.last())
            .map_or(false, |(lx, ly)| lx.is_finite() && ly.is_finite());
        if last_finite {
            ox.push(f64::NAN);
            oy.push(f64::NAN);
        }
    };

    if fx[0].is_finite() && fy[0].is_finite() {
        out_x.push(fx[0]);
        out_y.push(fy[0]);
        last_pushed_idx = Some(0);
    }

    for b in 0..max_buckets {
        let b_start = ((b as u128 * m as u128) / max_buckets as u128) as usize;
        let b_end = (((b + 1) as u128 * m as u128) / max_buckets as u128) as usize;
        if b_start >= b_end {
            continue;
        }

        let mut idx = b_start;
        while idx < b_end {
            if !fx[idx].is_finite() || !fy[idx].is_finite() {
                push_break(&mut out_x, &mut out_y);
                while idx < b_end && (!fx[idx].is_finite() || !fy[idx].is_finite()) {
                    idx += 1;
                }
                continue;
            }

            // Contiguous finite run within bucket [b_start, b_end)
            let mut min_idx = idx;
            let mut max_idx = idx;
            let mut min_y = fy[idx];
            let mut max_y = fy[idx];
            idx += 1;

            while idx < b_end && fx[idx].is_finite() && fy[idx].is_finite() {
                let yv = fy[idx];
                if yv < min_y {
                    min_y = yv;
                    min_idx = idx;
                }
                if yv > max_y {
                    max_y = yv;
                    max_idx = idx;
                }
                idx += 1;
            }

            let mut emit_idx = |i: usize| {
                if last_pushed_idx != Some(i) {
                    out_x.push(fx[i]);
                    out_y.push(fy[i]);
                    last_pushed_idx = Some(i);
                }
            };

            if min_idx == max_idx {
                emit_idx(min_idx);
            } else if min_idx < max_idx {
                emit_idx(min_idx);
                emit_idx(max_idx);
            } else {
                emit_idx(max_idx);
                emit_idx(min_idx);
            }
        }
    }

    if m > 0 && fx[m - 1].is_finite() && fy[m - 1].is_finite() && last_pushed_idx != Some(m - 1) {
        out_x.push(fx[m - 1]);
        out_y.push(fy[m - 1]);
    }

    (out_x, out_y)
}

pub fn nearest_sample(x: &[f64], y: &[f64], target_x: f64) -> Option<(f64, f64)> {
    let n = x.len().min(y.len());
    if n == 0 || !target_x.is_finite() {
        return None;
    }

    let x_first = x[0];
    let x_last = x[n - 1];

    // Fast O(log N) binary search for monotonically non-decreasing finite X series
    if x_first.is_finite() && x_last.is_finite() && x_last >= x_first {
        if target_x < x_first || target_x > x_last {
            return None;
        }

        let xs = &x[..n];
        let idx = xs.partition_point(|&v| v < target_x);

        let fast_candidate = if idx == 0 {
            if xs[0].is_finite() {
                Some(0)
            } else {
                None
            }
        } else if idx >= n {
            if xs[n - 1].is_finite() {
                Some(n - 1)
            } else {
                None
            }
        } else if xs[idx].is_finite() && xs[idx - 1].is_finite() {
            if (xs[idx] - target_x).abs() < (xs[idx - 1] - target_x).abs() {
                Some(idx)
            } else {
                Some(idx - 1)
            }
        } else {
            None
        };

        if let Some(best_idx) = fast_candidate {
            let vx = x[best_idx];
            let vy = y[best_idx];
            if vx.is_finite() && vy.is_finite() {
                return Some((vx, vy));
            }
        }
    }

    // Linear fallback for non-monotonic series or arrays with NaNs/Infs
    let mut min_x = f64::INFINITY;
    let mut max_x = f64::NEG_INFINITY;
    let mut best: Option<(f64, f64, f64)> = None;

    for i in 0..n {
        let vx = x[i];
        let vy = y[i];
        if vx.is_finite() && vy.is_finite() {
            if vx < min_x {
                min_x = vx;
            }
            if vx > max_x {
                max_x = vx;
            }
            let dist = (vx - target_x).abs();
            if best.map_or(true, |(bd, _, _)| dist < bd) {
                best = Some((dist, vx, vy));
            }
        }
    }

    if best.is_none() || target_x < min_x || target_x > max_x {
        return None;
    }

    best.map(|(_, bx, by)| (bx, by))
}

/// Finds the sample (x, y) within [x_min, x_max] that is closest in 2D screen-pixel space
/// to (target_x, target_y), returning (actual_x, actual_y, dist_sq_px).
pub fn nearest_sample_2d(
    x: &[f64],
    y: &[f64],
    target_x: f64,
    target_y: f64,
    x_min: f64,
    x_max: f64,
    px_per_x: f64,
    px_per_y: f64,
) -> Option<(f64, f64, f64)> {
    let n = x.len().min(y.len());
    if n == 0
        || !target_x.is_finite()
        || !target_y.is_finite()
        || !px_per_x.is_finite()
        || !px_per_y.is_finite()
        || px_per_x <= 0.0
        || px_per_y <= 0.0
    {
        return None;
    }

    let x_first = x[0];
    let x_last = x[n - 1];
    let is_monotonic = x_first.is_finite() && x_last.is_finite() && x_last >= x_first;

    let (start, end) = if is_monotonic {
        if target_x < x_first || target_x > x_last {
            return None;
        }
        let xs = &x[..n];
        let s = xs.partition_point(|&v| v < x_min).saturating_sub(1);
        let e = (xs.partition_point(|&v| v <= x_max) + 1).min(n);
        (s, e)
    } else {
        (0, n)
    };

    let mut min_x = f64::INFINITY;
    let mut max_x = f64::NEG_INFINITY;
    let mut best: Option<(f64, f64, f64)> = None;

    for i in start..end {
        let vx = x[i];
        let vy = y[i];
        if vx.is_finite() && vy.is_finite() {
            if !is_monotonic {
                if vx < min_x {
                    min_x = vx;
                }
                if vx > max_x {
                    max_x = vx;
                }
            }
            let dx_px = (vx - target_x) * px_per_x;
            let dy_px = (vy - target_y) * px_per_y;
            let d2 = dx_px * dx_px + dy_px * dy_px;
            if best.map_or(true, |(_, _, bd2)| d2 < bd2) {
                best = Some((vx, vy, d2));
            }
        }
    }

    if !is_monotonic && (best.is_none() || target_x < min_x || target_x > max_x) {
        return None;
    }

    best
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::LocalCalcDef;
    use approx::assert_abs_diff_eq;

    fn make_raw(cols: &[(&str, &[f64])]) -> RawTable {
        let row_count = cols.first().map_or(0, |(_, s)| s.len());
        RawTable {
            columns: cols.iter().map(|(c, _)| c.to_string()).collect(),
            data: cols.iter().map(|(_, s)| s.to_vec()).collect(),
            row_count,
        }
    }

    #[test]
    fn test_parse_from_raw_lap_splitting_and_local_calcs() {
        let raw = make_raw(&[
            ("Lap_Raw", &[2.0, 2.0, 1.0, 1.0, 1.0]),
            ("Time_Raw", &[10.0, 12.5, 0.0, 1.0, 2.5]),
            ("Dist_Raw", &[200.0, 250.0, 0.0, 20.0, 55.0]),
            ("Wheel_FL", &[30.0, 40.0, 10.0, 20.0, 30.0]),
            ("Wheel_FR", &[32.0, 42.0, 12.0, 22.0, 32.0]),
        ]);

        let mut mapping = HashMap::new();
        mapping.insert("Lap_Raw".to_string(), "lap_num".to_string());
        mapping.insert("Time_Raw".to_string(), "lap_time".to_string());
        mapping.insert("Dist_Raw".to_string(), "lap_dist".to_string());

        let local_calcs = vec![
            LocalCalcDef {
                name: "AvgSpeed".to_string(),
                target_slug: "speed".to_string(),
                target_label: "Speed".to_string(),
                formula: "(A + B) / 2.0".to_string(),
                inputs: HashMap::from([
                    ("A".to_string(), "Wheel_FL".to_string()),
                    ("B".to_string(), "Wheel_FR".to_string()),
                ]),
            },
            LocalCalcDef {
                name: "SpeedMS".to_string(),
                target_slug: "speed_ms".to_string(),
                target_label: "Speed m/s".to_string(),
                formula: "A / 3.6".to_string(),
                inputs: HashMap::from([("A".to_string(), "speed".to_string())]),
            },
        ];

        let cfg = ParseSessionConfig {
            session_id: "s1".to_string(),
            file_name: "run1.csv".to_string(),
            mapping,
            local_calculated_channels: local_calcs,
            lap_slug: "lap_num".to_string(),
            time_slug: "lap_time".to_string(),
            dist_slug: "lap_dist".to_string(),
            preset_slug: None,
            preset_name: None,
            gap_time_threshold: None,
            gap_dist_threshold: None,
        };

        let mut store = SessionStore::new();
        let summary = store.parse_from_raw(raw, cfg);

        assert_eq!(summary.laps.len(), 2);
        // Sorted numerically: Lap 1 then Lap 2
        assert_eq!(summary.laps[0].lap_number, 1);
        assert_eq!(summary.laps[0].sample_count, 3);
        assert_abs_diff_eq!(summary.laps[0].duration, 2.5);
        assert_abs_diff_eq!(summary.laps[0].distance, 55.0);

        assert_eq!(summary.laps[1].lap_number, 2);
        assert_eq!(summary.laps[1].sample_count, 2);
        assert_abs_diff_eq!(summary.laps[1].duration, 2.5);
        assert_abs_diff_eq!(summary.laps[1].distance, 50.0);

        assert!(summary.channels.contains(&"speed".to_string()));
        assert!(summary.channels.contains(&"speed_ms".to_string()));
        assert!(!summary.channels.contains(&"lap_num".to_string()));

        // Raw table must not be polluted by local calc targets
        let stored = store.sessions.get("s1").unwrap();
        assert!(stored.raw_table.column("speed").is_none());
        assert!(stored.raw_table.column("AvgSpeed").is_none());

        let lap1_speed = store.get_lap_channel("s1", 1, "speed", &HashMap::new()).unwrap();
        assert_abs_diff_eq!(lap1_speed.as_slice(), [11.0, 21.0, 31.0].as_slice());

        let lap2_speed = store.get_lap_channel("s1", 2, "speed", &HashMap::new()).unwrap();
        assert_abs_diff_eq!(lap2_speed.as_slice(), [31.0, 41.0].as_slice());
    }

    #[test]
    fn test_parse_single_lap_when_no_lap_column_and_reparse() {
        let raw = make_raw(&[
            ("Time", &[f64::NAN, 1.0, 3.5, f64::NAN]),
            ("Dist", &[100.0, 80.0, 90.0, 95.0]), // negative delta -> clamped >= 0
            ("Speed", &[10.0, 20.0, 30.0, 40.0]),
        ]);

        let cfg = ParseSessionConfig {
            session_id: "s_nolap".to_string(),
            file_name: "nolap.csv".to_string(),
            mapping: HashMap::from([
                ("Time".to_string(), "lap_time".to_string()),
                ("Dist".to_string(), "lap_dist".to_string()),
                ("Speed".to_string(), "speed".to_string()),
            ]),
            local_calculated_channels: Vec::new(),
            lap_slug: "lap_num".to_string(),
            time_slug: "lap_time".to_string(),
            dist_slug: "lap_dist".to_string(),
            preset_slug: None,
            preset_name: None,
            gap_time_threshold: None,
            gap_dist_threshold: None,
        };

        let mut store = SessionStore::new();
        let summary = store.parse_from_raw(raw, cfg);
        assert_eq!(summary.laps.len(), 1);
        assert_eq!(summary.laps[0].lap_number, 1);
        assert_abs_diff_eq!(summary.laps[0].duration, 2.5);
        assert_abs_diff_eq!(summary.laps[0].distance, 0.0);

        // Reparse with Speed mapped to vehicle_speed
        let cfg2 = ParseSessionConfig {
            session_id: "s_nolap".to_string(),
            file_name: "nolap.csv".to_string(),
            mapping: HashMap::from([
                ("Time".to_string(), "lap_time".to_string()),
                ("Speed".to_string(), "vehicle_speed".to_string()),
            ]),
            local_calculated_channels: Vec::new(),
            lap_slug: "lap_num".to_string(),
            time_slug: "lap_time".to_string(),
            dist_slug: "lap_dist".to_string(),
            preset_slug: Some("p1".to_string()),
            preset_name: Some("P1".to_string()),
            gap_time_threshold: Some(2.0),
            gap_dist_threshold: Some(50.0),
        };

        let summary2 = store.reparse_session("s_nolap", cfg2).unwrap();
        assert!(summary2.channels.contains(&"vehicle_speed".to_string()));
        assert!(!summary2.channels.contains(&"speed".to_string()));
        assert_eq!(summary2.gap_time_threshold, Some(2.0));
    }

    #[test]
    fn test_cascading_global_calcs_cycle_detection_and_cache_clear() {
        let raw = make_raw(&[
            ("Time", &[0.0, 1.0]),
            ("V_x", &[3.0, 6.0]),
            ("V_y", &[4.0, 8.0]),
        ]);

        let cfg = ParseSessionConfig {
            session_id: "s_calc".to_string(),
            file_name: "calc.csv".to_string(),
            mapping: HashMap::from([
                ("Time".to_string(), "lap_time".to_string()),
                ("V_x".to_string(), "v_x".to_string()),
                ("V_y".to_string(), "v_y".to_string()),
            ]),
            local_calculated_channels: Vec::new(),
            lap_slug: "lap_num".to_string(),
            time_slug: "lap_time".to_string(),
            dist_slug: "lap_dist".to_string(),
            preset_slug: None,
            preset_name: None,
            gap_time_threshold: None,
            gap_dist_threshold: None,
        };

        let mut store = SessionStore::new();
        store.parse_from_raw(raw, cfg);

        let mut global_calcs = HashMap::new();
        global_calcs.insert(
            "speed_ms".to_string(),
            GlobalCalcDef {
                slug: "speed_ms".to_string(),
                label: "Speed m/s".to_string(),
                kind: "calculated".to_string(),
                unit: "m/s".to_string(),
                formula: "sqrt(A**2 + B**2)".to_string(),
                inputs: HashMap::from([
                    ("A".to_string(), "v_x".to_string()),
                    ("B".to_string(), "v_y".to_string()),
                ]),
            },
        );
        global_calcs.insert(
            "speed_kmh".to_string(),
            GlobalCalcDef {
                slug: "speed_kmh".to_string(),
                label: "Speed km/h".to_string(),
                kind: "calculated".to_string(),
                unit: "km/h".to_string(),
                formula: "A * 3.6".to_string(),
                inputs: HashMap::from([("A".to_string(), "speed_ms".to_string())]),
            },
        );
        // Circular dependency pair
        global_calcs.insert(
            "cyc_a".to_string(),
            GlobalCalcDef {
                slug: "cyc_a".to_string(),
                label: "Cyc A".to_string(),
                kind: "calculated".to_string(),
                unit: "".to_string(),
                formula: "A + 1".to_string(),
                inputs: HashMap::from([("A".to_string(), "cyc_b".to_string())]),
            },
        );
        global_calcs.insert(
            "cyc_b".to_string(),
            GlobalCalcDef {
                slug: "cyc_b".to_string(),
                label: "Cyc B".to_string(),
                kind: "calculated".to_string(),
                unit: "".to_string(),
                formula: "A * 2".to_string(),
                inputs: HashMap::from([("A".to_string(), "cyc_a".to_string())]),
            },
        );

        // Case-insensitive / space-to-underscore fallback on direct channel
        let vx = store.get_lap_channel("s_calc", 1, "V X", &global_calcs).unwrap();
        assert_abs_diff_eq!(vx.as_slice(), [3.0, 6.0].as_slice());

        // Cascading calculated channel
        let kmh = store.get_lap_channel("s_calc", 1, "speed_kmh", &global_calcs).unwrap();
        assert_abs_diff_eq!(kmh.as_slice(), [18.0, 36.0].as_slice());

        // Cached in lap.data
        assert!(store.sessions["s_calc"].laps[0].data.contains_key("speed_ms"));
        assert!(store.sessions["s_calc"].laps[0].data.contains_key("speed_kmh"));

        // Circular dependency returns None without stack overflow
        assert!(store.get_lap_channel("s_calc", 1, "cyc_a", &global_calcs).is_none());

        // Clear calculated cache
        store.clear_calculated_cache(&["speed_kmh".to_string(), "speed_ms".to_string()]);
        assert!(!store.sessions["s_calc"].laps[0].data.contains_key("speed_kmh"));
        assert!(!store.sessions["s_calc"].laps[0].data.contains_key("speed_ms"));
    }

    #[test]
    fn test_downsample_curve_gap_breaks_and_peak_buckets() {
        // 1. Gap filtering inserts NaN break on dt > gap_time and dx < 0
        let x = [0.0, 1.0, 5.0, 6.0, 4.0, 5.0];
        let y = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0];
        let t = [0.0, 1.0, 5.0, 6.0, 7.0, 8.0];
        let (dx, dy) = downsample_curve(
            &x,
            &y,
            None,
            None,
            100,
            Some(&t),
            None,
            Some(2.0),
            None,
        );
        // Breaks between index 1->2 (dt=4 > 2) and index 3->4 (dx=-2 < 0)
        assert_eq!(dx.len(), 8);
        assert!(dx[2].is_nan() && dy[2].is_nan());
        assert!(dx[5].is_nan() && dy[5].is_nan());

        // 2. Peak downsampling inside [x_min, x_max] with 1-sample margin and NaN preservation
        let mut bx = Vec::new();
        let mut by = Vec::new();
        let mut bt = Vec::new();
        for i in 0..1000 {
            let xv = i as f64;
            bx.push(xv);
            // Spike up and down
            let yv = if i == 250 {
                500.0
            } else if i == 251 {
                -500.0
            } else {
                (xv * 0.1).sin()
            };
            by.push(yv);
            bt.push(if i >= 500 { xv + 10.0 } else { xv });
        }

        let (px, py) = downsample_curve(
            &bx,
            &by,
            Some(100.0),
            Some(600.0),
            50,
            Some(&bt),
            None,
            Some(2.0),
            None,
        );

        // Includes 1 sample margin outside [100, 600]
        assert_eq!(px[0], 99.0);
        assert_eq!(*px.last().unwrap(), 601.0);
        // Preserves peaks
        assert!(py.iter().any(|&v| v == 500.0));
        assert!(py.iter().any(|&v| v == -500.0));
        // Preserves NaN gap break at i=500 (dt=11 > 2)
        assert!(px.iter().any(|v| v.is_nan()));
        assert!(px.len() <= 110);
    }

    #[test]
    fn test_nearest_sample_monotonic_nans_and_non_monotonic() {
        // 1. Monotonic fast path
        let x: Vec<f64> = (0..10_000).map(|i| i as f64 * 0.1).collect();
        let y: Vec<f64> = x.iter().map(|&v| v * 2.0).collect();
        let s = nearest_sample(&x, &y, 50.03).unwrap();
        assert_abs_diff_eq!(s.0, 50.0, epsilon = 1e-9);
        assert_abs_diff_eq!(s.1, 100.0, epsilon = 1e-9);
        assert!(nearest_sample(&x, &y, -1.0).is_none());
        assert!(nearest_sample(&x, &y, 1000.0).is_none());

        // 2. Leading/interior NaNs
        let nx = [f64::NAN, 0.0, f64::NAN, 2.0, 4.0];
        let ny = [f64::NAN, 10.0, 20.0, f64::NAN, 50.0];
        assert_eq!(nearest_sample(&nx, &ny, 1.5), Some((0.0, 10.0)));
        assert_eq!(nearest_sample(&nx, &ny, 3.0), Some((4.0, 50.0)));

        // 3. Duplicate X
        let dx = [0.0, 0.0, 1.0, 2.0];
        let dy = [0.0, 5.0, 10.0, 20.0];
        assert_eq!(nearest_sample(&dx, &dy, 0.9), Some((1.0, 10.0)));

        // 4. Non-monotonic fallback
        let mx = [10.0, 5.0, 2.0, 8.0];
        let my = [100.0, 50.0, 20.0, 80.0];
        assert_eq!(nearest_sample(&mx, &my, 2.2), Some((2.0, 20.0)));
        assert!(nearest_sample(&mx, &my, 1.0).is_none());
    }

    #[test]
    fn test_nearest_sample_2d_snaps_to_peak() {
        let x = [0.0, 2.0, 4.0, 5.0, 6.0, 8.0, 10.0];
        let y = [0.0, 10.0, 20.0, 100.0, 20.0, 10.0, 0.0];
        let res = nearest_sample_2d(&x, &y, 5.3, 102.0, 0.0, 10.0, 100.0, 5.0).unwrap();
        assert_eq!(res.0, 5.0);
        assert_eq!(res.1, 100.0);
    }
}
