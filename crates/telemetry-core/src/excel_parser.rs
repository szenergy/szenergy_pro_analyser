use crate::types::{FilePreview, RawTable};
use calamine::{open_workbook_auto_from_rs, Data, Reader};
use std::io::Cursor;

fn cell_to_string(cell: &Data) -> String {
    match cell {
        Data::Empty => String::new(),
        Data::String(s) => s.clone(),
        Data::Float(v) => {
            if v.fract() == 0.0 && v.abs() < 1e15 {
                format!("{}", *v as i64)
            } else {
                v.to_string()
            }
        }
        Data::Int(v) => v.to_string(),
        Data::Bool(b) => b.to_string(),
        Data::DateTime(dt) => dt.to_string(),
        Data::DateTimeIso(s) => s.clone(),
        Data::DurationIso(s) => s.clone(),
        Data::Error(e) => format!("{e:?}"),
    }
}

fn cell_to_f64(cell: &Data) -> f64 {
    match cell {
        Data::Float(v) => *v,
        Data::Int(v) => *v as f64,
        Data::String(s) => s.trim().parse::<f64>().unwrap_or(f64::NAN),
        Data::Bool(b) => {
            if *b {
                1.0
            } else {
                0.0
            }
        }
        _ => f64::NAN,
    }
}

fn extract_headers(header_row: &[Data]) -> Vec<String> {
    header_row
        .iter()
        .enumerate()
        .map(|(col_idx, cell)| {
            let s = cell_to_string(cell);
            let trimmed = s.trim();
            if trimmed.is_empty() {
                format!("Unnamed: {col_idx}")
            } else {
                trimmed.to_string()
            }
        })
        .collect()
}

pub fn preview_excel(
    bytes: &[u8],
    sheet_name: Option<&str>,
    max_rows: usize,
) -> Result<FilePreview, String> {
    let cursor = Cursor::new(bytes);
    let mut workbook = open_workbook_auto_from_rs(cursor)
        .map_err(|e| format!("Failed to open Excel workbook: {e}"))?;

    let sheets = workbook.sheet_names();
    if sheets.is_empty() {
        return Err("Workbook has no worksheets".to_string());
    }

    let selected = match sheet_name {
        Some(name) if !name.trim().is_empty() => {
            if sheets.iter().any(|s| s == name) {
                name.to_string()
            } else {
                return Err(format!("Worksheet '{name}' not found in workbook"));
            }
        }
        _ => sheets[0].clone(),
    };

    let range = workbook
        .worksheet_range(&selected)
        .map_err(|e| format!("Failed to read worksheet '{selected}': {e}"))?;

    let mut rows_iter = range.rows();
    let header_row = rows_iter
        .next()
        .ok_or_else(|| format!("Worksheet '{selected}' is empty"))?;

    let columns = extract_headers(header_row);
    let num_cols = columns.len();
    let mut rows = Vec::new();
    let mut finite_counts = vec![0usize; num_cols];
    let mut total_rows = 0usize;

    for row in rows_iter {
        total_rows += 1;
        if rows.len() < max_rows {
            let mut formatted = Vec::with_capacity(num_cols);
            for col_idx in 0..num_cols {
                let val = row.get(col_idx).map(cell_to_string).unwrap_or_default();
                formatted.push(val);
            }
            rows.push(formatted);
        }
        for col_idx in 0..num_cols {
            if let Some(cell) = row.get(col_idx) {
                if cell_to_f64(cell).is_finite() {
                    finite_counts[col_idx] += 1;
                }
            }
        }
    }

    Ok(FilePreview {
        columns,
        rows,
        sheets: Some(sheets),
        selected_sheet: Some(selected),
        finite_counts,
        total_rows,
    })
}

pub fn parse_excel(bytes: &[u8], sheet_name: Option<&str>) -> Result<RawTable, String> {
    let cursor = Cursor::new(bytes);
    let mut workbook = open_workbook_auto_from_rs(cursor)
        .map_err(|e| format!("Failed to open Excel workbook: {e}"))?;

    let sheets = workbook.sheet_names();
    if sheets.is_empty() {
        return Err("Workbook has no worksheets".to_string());
    }

    let selected = match sheet_name {
        Some(name) if !name.trim().is_empty() => {
            if sheets.iter().any(|s| s == name) {
                name.to_string()
            } else {
                return Err(format!("Worksheet '{name}' not found in workbook"));
            }
        }
        _ => sheets[0].clone(),
    };

    let range = workbook
        .worksheet_range(&selected)
        .map_err(|e| format!("Failed to read worksheet '{selected}': {e}"))?;

    let mut rows_iter = range.rows();
    let header_row = rows_iter
        .next()
        .ok_or_else(|| format!("Worksheet '{selected}' is empty"))?;

    let columns = extract_headers(header_row);
    let num_cols = columns.len();
    let mut data: Vec<Vec<f64>> = vec![Vec::new(); num_cols];
    let mut row_count = 0usize;

    for row in rows_iter {
        row_count += 1;
        for col_idx in 0..num_cols {
            let val = row.get(col_idx).map(cell_to_f64).unwrap_or(f64::NAN);
            data[col_idx].push(val);
        }
    }

    Ok(RawTable {
        columns,
        data,
        row_count,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cell_to_f64_conversions() {
        assert_eq!(cell_to_f64(&Data::Float(3.5)), 3.5);
        assert_eq!(cell_to_f64(&Data::Int(7)), 7.0);
        assert_eq!(cell_to_f64(&Data::String(" 12.25 ".into())), 12.25);
        assert!(cell_to_f64(&Data::String("abc".into())).is_nan());
        assert_eq!(cell_to_f64(&Data::Bool(true)), 1.0);
        assert_eq!(cell_to_f64(&Data::Bool(false)), 0.0);
        assert!(cell_to_f64(&Data::Empty).is_nan());
    }

    #[test]
    fn test_invalid_excel_bytes_returns_err() {
        assert!(preview_excel(b"not an excel file", None, 10).is_err());
        assert!(parse_excel(b"not an excel file", None).is_err());
    }
}
