use std::io::Cursor;

use calamine::{open_workbook_auto_from_rs, Data, Reader};
use csv::ReaderBuilder;
use encoding_rs::WINDOWS_1252;

use crate::types::MapData;

fn sniff_delimiter(text: &str) -> u8 {
    let first_line = text
        .lines()
        .find(|l| !l.trim().is_empty())
        .unwrap_or("");

    let candidates = [b',', b';', b'\t', b'|'];
    let mut best_delim = b',';
    let mut best_count = 0usize;

    for &delim in &candidates {
        let mut count = 0usize;
        let mut in_quotes = false;
        for &b in first_line.as_bytes() {
            if b == b'"' {
                in_quotes = !in_quotes;
            } else if !in_quotes && b == delim {
                count += 1;
            }
        }
        if count > best_count {
            best_count = count;
            best_delim = delim;
        }
    }

    best_delim
}

fn decode_text(bytes: &[u8]) -> String {
    let stripped = bytes.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(bytes);
    match std::str::from_utf8(stripped) {
        Ok(s) => s.to_string(),
        Err(_) => {
            let (cow, _, _) = WINDOWS_1252.decode(stripped);
            cow.into_owned()
        }
    }
}

fn parse_csv_rows(bytes: &[u8]) -> Result<Vec<Vec<String>>, String> {
    let text = decode_text(bytes);
    let delim = sniff_delimiter(&text);

    let mut rdr = ReaderBuilder::new()
        .has_headers(false)
        .delimiter(delim)
        .flexible(true)
        .from_reader(text.as_bytes());

    let mut rows = Vec::new();
    for result in rdr.records() {
        let record = result.map_err(|e| format!("CSV parse error: {e}"))?;
        let row: Vec<String> = record.iter().map(|s| s.trim().to_string()).collect();
        if row.iter().all(|c| c.is_empty()) {
            continue;
        }
        rows.push(row);
    }
    Ok(rows)
}

fn cell_to_string(cell: &Data) -> String {
    match cell {
        Data::Empty => String::new(),
        Data::String(s) => s.trim().to_string(),
        Data::Float(f) => f.to_string(),
        Data::Int(i) => i.to_string(),
        Data::Bool(b) => b.to_string(),
        Data::DateTime(dt) => dt.to_string(),
        Data::DateTimeIso(s) | Data::DurationIso(s) => s.trim().to_string(),
        Data::Error(_) => String::new(),
    }
}

fn parse_excel_rows(bytes: &[u8]) -> Result<Vec<Vec<String>>, String> {
    let cursor = Cursor::new(bytes);
    let mut workbook = open_workbook_auto_from_rs(cursor)
        .map_err(|e| format!("Failed to open Excel workbook: {e}"))?;

    let sheet_names = workbook.sheet_names();
    let first_sheet = sheet_names
        .first()
        .ok_or_else(|| "Excel workbook contains no sheets".to_string())?
        .clone();

    let range = workbook
        .worksheet_range(&first_sheet)
        .map_err(|e| format!("Failed to read sheet '{first_sheet}': {e}"))?;

    let mut rows = Vec::new();
    for row in range.rows() {
        let r: Vec<String> = row.iter().map(cell_to_string).collect();
        if r.iter().all(|c| c.is_empty()) {
            continue;
        }
        rows.push(r);
    }
    Ok(rows)
}

fn parse_rows(bytes: &[u8], file_name: &str) -> Result<Vec<Vec<String>>, String> {
    let ext = file_name
        .rsplit('.')
        .next()
        .map(|s| s.to_ascii_lowercase())
        .unwrap_or_default();

    match ext.as_str() {
        "csv" => parse_csv_rows(bytes),
        "xlsx" | "xls" => parse_excel_rows(bytes),
        _ => Err(format!(
            "Unsupported track map file format: '.{ext}'. Supported: .csv, .xlsx, .xls"
        )),
    }
}

fn is_numeric_str(s: &str) -> bool {
    let trimmed = s.trim();
    if trimmed.is_empty() {
        return false;
    }
    trimmed.parse::<f64>().map(|v| v.is_finite()).unwrap_or(false)
}

fn has_header_row(first_row: &[String]) -> bool {
    let non_empty: Vec<&String> = first_row.iter().filter(|s| !s.trim().is_empty()).collect();
    if non_empty.is_empty() {
        return true;
    }
    let all_numeric = non_empty.iter().all(|s| is_numeric_str(s));
    !all_numeric
}

fn extract_columns_and_data_start(rows: &[Vec<String>]) -> Result<(Vec<String>, usize), String> {
    let first_row = rows
        .first()
        .ok_or_else(|| "Map file is empty".to_string())?;

    if has_header_row(first_row) {
        let cols = first_row
            .iter()
            .enumerate()
            .map(|(i, s)| {
                let t = s.trim();
                if t.is_empty() {
                    format!("Column {i}")
                } else {
                    t.to_string()
                }
            })
            .collect();
        Ok((cols, 1))
    } else {
        let cols = (0..first_row.len())
            .map(|i| format!("Column {i}"))
            .collect();
        Ok((cols, 0))
    }
}

pub fn get_map_columns(bytes: &[u8], file_name: &str) -> Result<Vec<String>, String> {
    let rows = parse_rows(bytes, file_name)?;
    let (cols, _) = extract_columns_and_data_start(&rows)?;
    Ok(cols)
}

pub fn load_map_data(
    bytes: &[u8],
    file_name: &str,
    x_col: &str,
    y_col: &str,
    dist_col: Option<&str>,
) -> Result<MapData, String> {
    let rows = parse_rows(bytes, file_name)?;
    let (cols, data_start) = extract_columns_and_data_start(&rows)?;

    let x_idx = cols
        .iter()
        .position(|c| c == x_col)
        .ok_or_else(|| format!("X column '{x_col}' not found in map file"))?;
    let y_idx = cols
        .iter()
        .position(|c| c == y_col)
        .ok_or_else(|| format!("Y column '{y_col}' not found in map file"))?;

    let dist_idx = match dist_col {
        Some(dc) if !dc.is_empty() => Some(
            cols.iter()
                .position(|c| c == dc)
                .ok_or_else(|| format!("Distance column '{dc}' not found in map file"))?,
        ),
        _ => None,
    };

    let mut x_vec = Vec::with_capacity(rows.len().saturating_sub(data_start));
    let mut y_vec = Vec::with_capacity(rows.len().saturating_sub(data_start));
    let mut dist_vec = dist_idx.map(|_| Vec::with_capacity(rows.len().saturating_sub(data_start)));

    for row in &rows[data_start..] {
        let x_val = row
            .get(x_idx)
            .and_then(|s| s.trim().parse::<f64>().ok())
            .filter(|v| v.is_finite());
        let y_val = row
            .get(y_idx)
            .and_then(|s| s.trim().parse::<f64>().ok())
            .filter(|v| v.is_finite());

        let (Some(xv), Some(yv)) = (x_val, y_val) else {
            continue;
        };

        x_vec.push(xv);
        y_vec.push(yv);

        if let (Some(d_idx), Some(d_out)) = (dist_idx, &mut dist_vec) {
            let d_val = row
                .get(d_idx)
                .and_then(|s| s.trim().parse::<f64>().ok())
                .unwrap_or(f64::NAN);
            d_out.push(d_val);
        }
    }

    Ok(MapData {
        x: x_vec,
        y: y_vec,
        distance: dist_vec,
    })
}

pub fn compute_start_line_coords(x: &[f64], y: &[f64], angle_deg: f64) -> ([f64; 2], [f64; 2]) {
    let n = x.len().min(y.len());
    if n < 2 {
        return ([0.0, 0.0], [0.0, 0.0]);
    }

    let x0 = x[0];
    let y0 = y[0];

    let mut dx = 1.0_f64;
    let mut dy = 0.0_f64;
    for i in 1..n {
        let d_x = x[i] - x0;
        let d_y = y[i] - y0;
        if d_x * d_x + d_y * d_y > 1e-8 {
            dx = d_x;
            dy = d_y;
            break;
        }
    }

    let length = (dx * dx + dy * dy).sqrt();
    let (tx, ty) = if length > 0.0 {
        (dx / length, dy / length)
    } else {
        (1.0, 0.0)
    };

    let nx = -ty;
    let ny = tx;

    let mut min_x = f64::INFINITY;
    let mut max_x = f64::NEG_INFINITY;
    let mut sum_x = 0.0_f64;
    for &vx in &x[..n] {
        if vx < min_x {
            min_x = vx;
        }
        if vx > max_x {
            max_x = vx;
        }
        sum_x += vx;
    }

    let mut min_y = f64::INFINITY;
    let mut max_y = f64::NEG_INFINITY;
    let mut sum_y = 0.0_f64;
    for &vy in &y[..n] {
        if vy < min_y {
            min_y = vy;
        }
        if vy > max_y {
            max_y = vy;
        }
        sum_y += vy;
    }

    let span_x = max_x - min_x;
    let span_y = max_y - min_y;
    let track_span = span_x.max(span_y);
    let half_width = (0.03 * track_span).max(1.0);

    let p1x = x0 - half_width * nx;
    let p1y = y0 - half_width * ny;
    let p2x = x0 + half_width * nx;
    let p2y = y0 + half_width * ny;

    let cx = sum_x / (n as f64);
    let cy = sum_y / (n as f64);
    let rad = angle_deg.to_radians();
    let cos_theta = rad.cos();
    let sin_theta = rad.sin();

    let rot = |px: f64, py: f64| -> (f64, f64) {
        let ox = px - cx;
        let oy = py - cy;
        let rx = ox * cos_theta - oy * sin_theta + cx;
        let ry = ox * sin_theta + oy * cos_theta + cy;
        (rx, ry)
    };

    let (r1x, r1y) = rot(p1x, p1y);
    let (r2x, r2y) = rot(p2x, p2y);

    ([r1x, r2x], [r1y, r2y])
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn test_headered_csv_map() {
        let csv = b"X,Y,Dist\n0.0,0.0,0.0\n10.0,0.0,10.0\n10.0,10.0,20.0\n";
        let cols = get_map_columns(csv, "track.csv").unwrap();
        assert_eq!(cols, vec!["X", "Y", "Dist"]);

        let data = load_map_data(csv, "track.csv", "X", "Y", Some("Dist")).unwrap();
        assert_eq!(data.x, vec![0.0, 10.0, 10.0]);
        assert_eq!(data.y, vec![0.0, 0.0, 10.0]);
        assert_eq!(data.distance.unwrap(), vec![0.0, 10.0, 20.0]);
    }

    #[test]
    fn test_headerless_csv_map_and_nan_filtering() {
        let csv = b"1.0;2.0\n3.0;4.0\nbad;5.0\n6.0;7.0\n";
        let cols = get_map_columns(csv, "track.csv").unwrap();
        assert_eq!(cols, vec!["Column 0", "Column 1"]);

        let data = load_map_data(csv, "track.csv", "Column 0", "Column 1", None).unwrap();
        assert_eq!(data.x, vec![1.0, 3.0, 6.0]);
        assert_eq!(data.y, vec![2.0, 4.0, 7.0]);
        assert!(data.distance.is_none());
    }

    #[test]
    fn test_missing_column_returns_err() {
        let csv = b"X,Y\n0.0,1.0\n";
        let res = load_map_data(csv, "track.csv", "Z", "Y", None);
        assert!(res.is_err());
    }

    #[test]
    fn test_compute_start_line_coords_zero_and_90_deg() {
        // Square track: (0,0) -> (100,0) -> (100,100) -> (0,100)
        // Forward tangent at (0,0) is (1,0), normal is (0,1).
        // span = 100, half_width = max(3.0, 1.0) = 3.0.
        // At 0 deg: p1 = (0, -3), p2 = (0, 3).
        let x = [0.0, 100.0, 100.0, 0.0];
        let y = [0.0, 0.0, 100.0, 100.0];

        let (xs, ys) = compute_start_line_coords(&x, &y, 0.0);
        assert_relative_eq!(xs[0], 0.0, epsilon = 1e-9);
        assert_relative_eq!(xs[1], 0.0, epsilon = 1e-9);
        assert_relative_eq!(ys[0], -3.0, epsilon = 1e-9);
        assert_relative_eq!(ys[1], 3.0, epsilon = 1e-9);

        // Rotate 90 deg CCW around centroid (50, 50):
        // (0, -3) -> offset (-50, -53) -> rotated (53, -50) -> + (50, 50) = (103, 0)
        // (0, 3)  -> offset (-50, -47) -> rotated (47, -50) -> + (50, 50) = (97, 0)
        let (xs90, ys90) = compute_start_line_coords(&x, &y, 90.0);
        assert_relative_eq!(xs90[0], 103.0, epsilon = 1e-9);
        assert_relative_eq!(ys90[0], 0.0, epsilon = 1e-9);
        assert_relative_eq!(xs90[1], 97.0, epsilon = 1e-9);
        assert_relative_eq!(ys90[1], 0.0, epsilon = 1e-9);
    }
}
