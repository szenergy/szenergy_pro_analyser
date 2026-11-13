use crate::types::{FilePreview, RawTable};
use csv::ReaderBuilder;
use encoding_rs::WINDOWS_1252;

fn decode_bytes(bytes: &[u8]) -> String {
    let stripped = bytes.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(bytes);
    if let Ok(s) = std::str::from_utf8(stripped) {
        return s.trim_start_matches('\u{feff}').to_string();
    }

    let (cow, _, had_errors) = WINDOWS_1252.decode(stripped);
    if !had_errors {
        return cow.into_owned();
    }

    String::from_utf8_lossy(stripped).into_owned()
}

fn sniff_delimiter(text: &str) -> u8 {
    let sample_lines: Vec<&str> = text
        .lines()
        .filter(|l| !l.trim().is_empty())
        .take(10)
        .collect();

    if sample_lines.is_empty() {
        return b',';
    }

    let sample = sample_lines.join("\n");
    let candidates = [b',', b';', b'\t'];
    let mut best: Option<(usize, u8)> = None;

    for &delim in &candidates {
        let mut rdr = ReaderBuilder::new()
            .delimiter(delim)
            .has_headers(false)
            .flexible(true)
            .from_reader(sample.as_bytes());

        let mut counts = Vec::new();
        for rec in rdr.records().flatten() {
            counts.push(rec.len());
        }

        if let Some(&first) = counts.first() {
            if first >= 2 {
                let matching = counts.iter().filter(|&&c| c == first).count();
                let multi_col = counts.iter().filter(|&&c| c >= 2).count();
                // Score prioritizes exact-width consistency, then multi-column rows, then field count
                let score = matching * 1000 + multi_col * 10 + first;
                match best {
                    Some((best_score, _)) if score <= best_score => {}
                    _ => best = Some((score, delim)),
                }
            }
        }
    }

    best.map(|(_, d)| d).unwrap_or(b',')
}

fn extract_headers(record: &csv::StringRecord) -> Vec<String> {
    record
        .iter()
        .enumerate()
        .map(|(i, field)| {
            let trimmed = field.trim();
            if trimmed.is_empty() {
                format!("Unnamed: {i}")
            } else {
                trimmed.to_string()
            }
        })
        .collect()
}

pub fn preview_csv(bytes: &[u8], max_rows: usize) -> Result<FilePreview, String> {
    let text = decode_bytes(bytes);
    let delim = sniff_delimiter(&text);

    let mut rdr = ReaderBuilder::new()
        .delimiter(delim)
        .has_headers(false)
        .flexible(true)
        .from_reader(text.as_bytes());

    let mut records = rdr.records();
    let header_rec = records
        .next()
        .ok_or_else(|| "Empty CSV file".to_string())?
        .map_err(|e| format!("Failed to parse CSV header: {e}"))?;

    let columns = extract_headers(&header_rec);
    let mut rows = Vec::new();

    for rec_res in records.take(max_rows) {
        let rec = rec_res.map_err(|e| format!("Failed to parse CSV row: {e}"))?;
        let mut row: Vec<String> = rec.iter().map(|s| s.to_string()).collect();
        row.resize(columns.len(), String::new());
        rows.push(row);
    }

    Ok(FilePreview { columns, rows })
}

pub fn parse_csv(bytes: &[u8]) -> Result<RawTable, String> {
    let text = decode_bytes(bytes);
    let delim = sniff_delimiter(&text);

    let mut rdr = ReaderBuilder::new()
        .delimiter(delim)
        .has_headers(false)
        .flexible(true)
        .from_reader(text.as_bytes());

    let mut records = rdr.records();
    let header_rec = records
        .next()
        .ok_or_else(|| "Empty CSV file".to_string())?
        .map_err(|e| format!("Failed to parse CSV header: {e}"))?;

    let columns = extract_headers(&header_rec);
    let num_cols = columns.len();
    let mut data: Vec<Vec<f64>> = vec![Vec::new(); num_cols];
    let mut row_count = 0usize;

    for rec_res in records {
        let rec = rec_res.map_err(|e| format!("Failed to parse CSV row: {e}"))?;
        row_count += 1;
        for col_idx in 0..num_cols {
            let val = rec
                .get(col_idx)
                .map(|s| s.trim().parse::<f64>().unwrap_or(f64::NAN))
                .unwrap_or(f64::NAN);
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
    fn test_preview_and_parse_semicolon_csv() {
        let input = b"\xEF\xBB\xBFtime;speed;;rpm\n0.0;12.5;foo;1000\n0.1;;bar\n";
        let preview = preview_csv(input, 5).expect("preview_csv should succeed");
        assert_eq!(preview.columns, vec!["time", "speed", "Unnamed: 2", "rpm"]);
        assert_eq!(preview.rows.len(), 2);
        assert_eq!(preview.rows[1], vec!["0.1", "", "bar", ""]);

        let table = parse_csv(input).expect("parse_csv should succeed");
        assert_eq!(table.row_count, 2);
        assert_eq!(table.column("time").unwrap(), &[0.0, 0.1]);
        assert!(table.column("speed").unwrap()[0] == 12.5);
        assert!(table.column("speed").unwrap()[1].is_nan());
        assert!(table.column("Unnamed: 2").unwrap()[0].is_nan());
        assert_eq!(table.column("rpm").unwrap()[0], 1000.0);
        assert!(table.column("rpm").unwrap()[1].is_nan());
    }

    #[test]
    fn test_windows_1252_decoding() {
        // "sebess\xE9g" in Windows-1252 ("sebesség")
        let input = b"id,sebess\xE9g\n1,42.0\n";
        let preview = preview_csv(input, 5).expect("preview_csv should handle cp1252");
        assert_eq!(preview.columns, vec!["id", "sebesség"]);
        let table = parse_csv(input).expect("parse_csv should handle cp1252");
        assert_eq!(table.column("sebesség").unwrap(), &[42.0]);
    }
}
