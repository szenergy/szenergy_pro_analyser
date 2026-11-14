use std::collections::{BTreeMap, HashMap};

use crate::types::{
    ChannelGroupDef, ChannelTransform, LapSummary, ParseSessionConfig, RawTable, SessionSummary,
};
#[derive(Debug, Clone)]
pub struct StoredLap {
    pub lap_number: i32,
    pub duration: f64,
    pub distance: f64,
    pub sample_count: usize,
    pub sys_time: Option<Vec<f64>>,
    pub sys_dist: Option<Vec<f64>>,
    pub data: HashMap<String, Vec<f64>>,
}

#[derive(Debug, Clone)]
pub struct StoredSession {
    pub summary: SessionSummary,
    pub raw_table: RawTable,
    pub source_bytes: Option<Vec<u8>>,
    pub is_tabular: bool,
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

fn apply_transform(values: &[f64], factor: f64, offset: f64) -> Vec<f64> {
    if (factor - 1.0).abs() <= f64::EPSILON && offset == 0.0 {
        return values.to_vec();
    }
    values.iter().map(|&v| (v * factor) + offset).collect()
}

fn resolve_transform<'a>(
    transforms: &'a HashMap<String, ChannelTransform>,
    alias: &str,
    resolved_key: &str,
) -> (f64, f64) {
    if let Some(t) = transforms.get(resolved_key) {
        return (t.factor, t.offset);
    }
    if let Some(t) = transforms.get(alias) {
        return (t.factor, t.offset);
    }
    if let Some(k) = resolve_key_case_insensitive(transforms, resolved_key) {
        if let Some(t) = transforms.get(k) {
            return (t.factor, t.offset);
        }
    }
    (1.0, 0.0)
}


impl SessionStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn parse_from_raw(
        &mut self,
        raw: RawTable,
        cfg: ParseSessionConfig,
        is_tabular: bool,
        source_bytes: Option<Vec<u8>>,
    ) -> Result<SessionSummary, String> {
        let lap_col = cfg.lap_col.trim().to_string();
        if lap_col.is_empty() {
            return Err("Lap Number column is required.".to_string());
        }
        let lap_idx = raw
            .column_index(&lap_col)
            .ok_or_else(|| format!("Lap Number column '{}' was not found.", lap_col))?;

        let time_col = cfg
            .time_col
            .as_deref()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string);
        let dist_col = cfg
            .dist_col
            .as_deref()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string);

        if time_col.is_none() && dist_col.is_none() {
            return Err("Select at least Lap Time or Lap Distance.".to_string());
        }

        let time_idx = match &time_col {
            Some(col) => Some(
                raw.column_index(col)
                    .ok_or_else(|| format!("Lap Time column '{}' was not found.", col))?,
            ),
            None => None,
        };
        let dist_idx = match &dist_col {
            Some(col) => Some(
                raw.column_index(col)
                    .ok_or_else(|| format!("Lap Distance column '{}' was not found.", col))?,
            ),
            None => None,
        };

        let lap_vec = &raw.data[lap_idx];
        let mut lap_groups: BTreeMap<i32, Vec<usize>> = BTreeMap::new();
        for (idx, &val) in lap_vec.iter().enumerate() {
            if val.is_finite() {
                let lap_num = val as i32;
                lap_groups.entry(lap_num).or_default().push(idx);
            }
        }
        if lap_groups.is_empty() {
            return Err(format!(
                "Column '{}' contains no valid numeric lap numbers.",
                lap_col
            ));
        }

        let ref_finite_count = lap_vec.iter().filter(|v| v.is_finite()).count();

        let mut kept_indices: Vec<usize> = Vec::new();
        let mut channels: Vec<String> = Vec::new();
        let mut skipped_channels: Vec<String> = Vec::new();

        for (col_idx, col_name) in raw.columns.iter().enumerate() {
            if col_idx == lap_idx {
                continue;
            }
            let col_vec = &raw.data[col_idx];
            let finite_count = col_vec.iter().filter(|v| v.is_finite()).count();

            let enough_points = if is_tabular {
                finite_count >= 2 && (ref_finite_count < 4 || finite_count * 2 >= ref_finite_count)
            } else {
                finite_count >= 2
            };

            if enough_points {
                kept_indices.push(col_idx);
                channels.push(col_name.clone());
            } else {
                skipped_channels.push(col_name.clone());
            }
        }

        let mut stored_laps: Vec<StoredLap> = Vec::with_capacity(lap_groups.len());
        for (lap_num, indices) in lap_groups {
            let mut lap_data: HashMap<String, Vec<f64>> = HashMap::with_capacity(kept_indices.len());
            for &col_idx in &kept_indices {
                let col_name = &raw.columns[col_idx];
                let col_vec = &raw.data[col_idx];
                let mut slice = Vec::with_capacity(indices.len());
                for &row_idx in &indices {
                    slice.push(col_vec[row_idx]);
                }
                lap_data.insert(col_name.clone(), slice);
            }

            let sys_time = time_idx.map(|t_idx| {
                let col_vec = &raw.data[t_idx];
                indices.iter().map(|&r| col_vec[r]).collect::<Vec<f64>>()
            });
            let sys_dist = dist_idx.map(|d_idx| {
                let col_vec = &raw.data[d_idx];
                indices.iter().map(|&r| col_vec[r]).collect::<Vec<f64>>()
            });

            let duration = sys_time.as_deref().map(compute_valid_span).unwrap_or(0.0);
            let distance = sys_dist.as_deref().map(compute_valid_span).unwrap_or(0.0);

            stored_laps.push(StoredLap {
                lap_number: lap_num,
                duration,
                distance,
                sample_count: indices.len(),
                sys_time,
                sys_dist,
                data: lap_data,
            });
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
            sheet_name: cfg.sheet_name.clone(),
            channels,
            skipped_channels,
            available_columns: raw.columns.clone(),
            lap_col,
            time_col: time_col.clone(),
            dist_col: dist_col.clone(),
            has_time: time_idx.is_some(),
            has_dist: dist_idx.is_some(),
            laps: lap_summaries,
            gap_time_threshold: cfg.gap_time_threshold,
            gap_dist_threshold: cfg.gap_dist_threshold,
            group_overrides: cfg.group_overrides,
        };

        let stored = StoredSession {
            summary: summary.clone(),
            raw_table: raw,
            source_bytes,
            is_tabular,
            laps: stored_laps,
        };
        self.sessions.insert(cfg.session_id, stored);
        Ok(summary)
    }

    pub fn get_lap_channel(
        &self,
        session_id: &str,
        lap_num: i32,
        key_or_group: &str,
        groups: &HashMap<String, ChannelGroupDef>,
    ) -> Option<Vec<f64>> {
        if key_or_group.is_empty() {
            return None;
        }
        let session = self.sessions.get(session_id)?;
        let lap = session.laps.iter().find(|l| l.lap_number == lap_num)?;

        if key_or_group == "lap_time" {
            return lap.sys_time.clone();
        }
        if key_or_group == "lap_dist" {
            return lap.sys_dist.clone();
        }

        if let Some(ov) = session.summary.group_overrides.get(key_or_group) {
            if !ov.channel.is_empty() {
                if let Some(resolved) = resolve_key_case_insensitive(&lap.data, &ov.channel) {
                    if let Some(vec) = lap.data.get(resolved) {
                        return Some(apply_transform(vec, ov.factor, ov.offset));
                    }
                }
            }
        }

        if let Some(group) = groups.get(key_or_group) {
            for alias in &group.channels {
                if let Some(resolved) = resolve_key_case_insensitive(&lap.data, alias) {
                    if let Some(vec) = lap.data.get(resolved) {
                        let (factor, offset) =
                            resolve_transform(&group.transforms, alias, resolved);
                        return Some(apply_transform(vec, factor, offset));
                    }
                }
            }
            return None;
        }

        if let Some(key) = resolve_key_case_insensitive(&lap.data, key_or_group) {
            return lap.data.get(key).cloned();
        }
        None
    }
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
    fn test_parse_from_raw_zero_mapping_and_tabular_filtering() {
        let raw = make_raw(&[
            ("Lap_Raw", &[2.0, 2.0, 1.0, 1.0, 1.0, 1.0]),
            ("Time_Raw", &[10.0, 12.5, 0.0, 1.0, 2.0, 3.0]),
            ("Dist_Raw", &[200.0, 250.0, 0.0, 20.0, 40.0, 60.0]),
            ("Speed", &[30.0, 40.0, 10.0, 20.0, 30.0, 40.0]),
            // Constant / 1-value column should be skipped
            ("Constant", &[42.0, f64::NAN, f64::NAN, f64::NAN, f64::NAN, f64::NAN]),
            // Small 2-row summary table in a 6-row CSV/Excel sheet (2 * 2 < 6) should be skipped
            ("Summary_Mini", &[100.0, 200.0, f64::NAN, f64::NAN, f64::NAN, f64::NAN]),
            // All NaN string column should be skipped
            ("Notes", &[f64::NAN, f64::NAN, f64::NAN, f64::NAN, f64::NAN, f64::NAN]),
        ]);

        let cfg = ParseSessionConfig {
            session_id: "s1".to_string(),
            file_name: "run1.csv".to_string(),
            sheet_name: None,
            lap_col: "Lap_Raw".to_string(),
            time_col: Some("Time_Raw".to_string()),
            dist_col: Some("Dist_Raw".to_string()),
            gap_time_threshold: None,
            gap_dist_threshold: None,
            group_overrides: HashMap::new(),
        };

        let mut store = SessionStore::new();
        let summary = store.parse_from_raw(raw, cfg, true, None).unwrap();

        assert_eq!(summary.laps.len(), 2);
        assert_eq!(summary.laps[0].lap_number, 1);
        assert_eq!(summary.laps[0].sample_count, 4);
        assert_abs_diff_eq!(summary.laps[0].duration, 3.0);
        assert_abs_diff_eq!(summary.laps[0].distance, 60.0);

        assert_eq!(summary.laps[1].lap_number, 2);
        assert_eq!(summary.laps[1].sample_count, 2);
        assert_abs_diff_eq!(summary.laps[1].duration, 2.5);
        assert_abs_diff_eq!(summary.laps[1].distance, 50.0);

        assert!(summary.channels.contains(&"Speed".to_string()));
        assert!(!summary.channels.contains(&"Lap_Raw".to_string()));
        assert!(!summary.channels.contains(&"Constant".to_string()));
        assert!(!summary.channels.contains(&"Summary_Mini".to_string()));
        assert!(!summary.channels.contains(&"Notes".to_string()));
        assert!(summary.skipped_channels.contains(&"Constant".to_string()));
        assert!(summary.skipped_channels.contains(&"Summary_Mini".to_string()));

        let lap1_speed = store.get_lap_channel("s1", 1, "Speed", &HashMap::new()).unwrap();
        assert_abs_diff_eq!(lap1_speed.as_slice(), [10.0, 20.0, 30.0, 40.0].as_slice());
        let lap1_time = store.get_lap_channel("s1", 1, "lap_time", &HashMap::new()).unwrap();
        assert_abs_diff_eq!(lap1_time.as_slice(), [0.0, 1.0, 2.0, 3.0].as_slice());
    }

    #[test]
    fn test_channel_group_priority_resolution() {
        let raw = make_raw(&[
            ("Lap", &[1.0, 1.0, 1.0]),
            ("Time", &[0.0, 1.0, 2.0]),
            ("Speed_A", &[10.0, 20.0, 30.0]),
            ("Speed_B", &[99.0, 88.0, 77.0]),
        ]);
        let cfg = ParseSessionConfig {
            session_id: "s1".to_string(),
            file_name: "run.tdms".to_string(),
            sheet_name: None,
            lap_col: "Lap".to_string(),
            time_col: Some("Time".to_string()),
            dist_col: None,
            gap_time_threshold: None,
            gap_dist_threshold: None,
            group_overrides: HashMap::new(),
        };
        let mut store = SessionStore::new();
        let summary = store.parse_from_raw(raw, cfg, false, None).unwrap();
        assert!(summary.has_time);
        assert!(!summary.has_dist);

        let mut transforms = HashMap::new();
        transforms.insert(
            "Speed_B".to_string(),
            ChannelTransform {
                factor: 2.0,
                offset: 5.0,
            },
        );
        let mut groups = HashMap::new();
        groups.insert(
            "grp_speed".to_string(),
            ChannelGroupDef {
                id: "grp_speed".to_string(),
                name: "Speed".to_string(),
                unit: "km/h".to_string(),
                channels: vec![
                    "Missing_Speed".to_string(),
                    "Speed_B".to_string(),
                    "Speed_A".to_string(),
                ],
                transforms,
            },
        );

        // Speed_B has higher priority than Speed_A, and applies (raw * 2.0) + 5.0
        let resolved = store.get_lap_channel("s1", 1, "grp_speed", &groups).unwrap();
        assert_abs_diff_eq!(resolved.as_slice(), [203.0, 181.0, 159.0].as_slice());

        // Local override selects Speed_A with (raw * 0.5) - 1.0
        let mut overrides = HashMap::new();
        overrides.insert(
            "grp_speed".to_string(),
            crate::types::GroupChannelOverride {
                channel: "Speed_A".to_string(),
                factor: 0.5,
                offset: -1.0,
            },
        );
        store
            .sessions
            .get_mut("s1")
            .unwrap()
            .summary
            .group_overrides = overrides;
        let overridden = store.get_lap_channel("s1", 1, "grp_speed", &groups).unwrap();
        assert_abs_diff_eq!(overridden.as_slice(), [4.0, 9.0, 14.0].as_slice());
    }

    #[test]
    fn test_requires_lap_and_time_or_dist() {
        let raw = make_raw(&[("Lap", &[1.0, 1.0]), ("Speed", &[10.0, 20.0])]);
        let cfg = ParseSessionConfig {
            session_id: "s_err".to_string(),
            file_name: "err.csv".to_string(),
            sheet_name: None,
            lap_col: "Lap".to_string(),
            time_col: None,
            dist_col: None,
            gap_time_threshold: None,
            gap_dist_threshold: None,
            group_overrides: HashMap::new(),
        };
        let mut store = SessionStore::new();
        assert!(store.parse_from_raw(raw, cfg, true, None).is_err());
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
