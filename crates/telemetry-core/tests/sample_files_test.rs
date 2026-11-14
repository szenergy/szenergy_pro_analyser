use std::path::PathBuf;
use telemetry_core::{csv_parser, excel_parser, tdms_parser};

fn sample_path(rel: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../samples")
        .join(rel)
}

#[test]
fn test_real_csv_sample() {
    let bytes = std::fs::read(sample_path("csv/laps_2026-06-10_08-53-28.csv")).unwrap();
    let preview = csv_parser::preview_csv(&bytes, 5).unwrap();
    assert!(!preview.columns.is_empty());
    assert_eq!(preview.columns[0], "Lap Number");
    assert_eq!(preview.rows.len(), 5);

    let table = csv_parser::parse_csv(&bytes).unwrap();
    assert!(table.row_count >= 20);
    let lap_col = table.column("Lap Number").unwrap();
    assert_eq!(lap_col[0], 1.0);
    // Trailing summary rows have empty Lap Number -> NaN preserved
    assert!(lap_col.last().unwrap().is_nan());
}

#[test]
fn test_real_xlsx_sample() {
    let bytes = std::fs::read(sample_path("xlsx/Test_10_06_2026_15_54_32.xlsx")).unwrap();
    let preview = excel_parser::preview_excel(&bytes, None, 5).unwrap();
    assert!(!preview.columns.is_empty());
    assert_eq!(preview.rows.len(), 5);
    assert_eq!(preview.sheets.as_deref(), Some(&["data".to_string(), "calc".to_string()][..]));
    assert_eq!(preview.selected_sheet.as_deref(), Some("data"));

    let table = excel_parser::parse_excel(&bytes, None).unwrap();
    assert!(table.row_count > 100);
    assert_eq!(table.columns.len(), table.data.len());

    let calc_preview = excel_parser::preview_excel(&bytes, Some("calc"), 5).unwrap();
    assert_eq!(calc_preview.selected_sheet.as_deref(), Some("calc"));
}

#[test]
fn test_real_tdms_samples() {
    for rel in [
        "tdms/Test_10_06_2026_09_25_43.tdms",
        "tdms/Test_10_06_2026_12_55_43.tdms",
        "tdms/Test_10_06_2026_17_26_48.tdms",
        "tdms/Test_6_10_2026_15_24_46.tdms",
    ] {
        let bytes = std::fs::read(sample_path(rel)).unwrap();
        let preview = tdms_parser::preview_tdms(&bytes, 5).unwrap();
        assert_eq!(preview.columns.len(), 95, "expected 95 channels in {rel}");
        assert_eq!(preview.rows.len(), 5, "expected 5 preview rows in {rel}");

        let table = tdms_parser::parse_tdms(&bytes).unwrap();
        assert_eq!(table.columns.len(), 95, "expected 95 channels in {rel}");
        assert!(table.row_count > 1000, "expected >1000 rows in {rel}");
        assert!(
            table.columns.iter().any(|c| c == "Lap_Number"),
            "missing Lap_Number in {rel}"
        );
    }
}
