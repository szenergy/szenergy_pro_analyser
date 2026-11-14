use std::collections::HashMap;

use serde::{Deserialize, Serialize};
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FilePreview {
    pub columns: Vec<String>,
    pub rows: Vec<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sheets: Option<Vec<String>>,
    #[serde(rename = "selectedSheet", skip_serializing_if = "Option::is_none")]
    pub selected_sheet: Option<String>,
    #[serde(rename = "finiteCounts")]
    pub finite_counts: Vec<usize>,
    #[serde(rename = "totalRows")]
    pub total_rows: usize,
}

#[derive(Debug, Clone)]
pub struct RawTable {
    pub columns: Vec<String>,
    /// Column-major f64 arrays; length of each inner Vec equals `row_count`.
    /// Missing/non-numeric entries are `f64::NAN`.
    pub data: Vec<Vec<f64>>,
    pub row_count: usize,
}

impl RawTable {
    pub fn column_index(&self, name: &str) -> Option<usize> {
        self.columns.iter().position(|c| c == name)
    }

    pub fn column(&self, name: &str) -> Option<&[f64]> {
        self.column_index(name).map(|i| self.data[i].as_slice())
    }
}

fn default_factor() -> f64 {
    1.0
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChannelTransform {
    #[serde(default = "default_factor")]
    pub factor: f64,
    #[serde(default)]
    pub offset: f64,
}

impl Default for ChannelTransform {
    fn default() -> Self {
        Self {
            factor: 1.0,
            offset: 0.0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupChannelOverride {
    pub channel: String,
    #[serde(default = "default_factor")]
    pub factor: f64,
    #[serde(default)]
    pub offset: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChannelGroupDef {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub unit: String,
    #[serde(default)]
    pub channels: Vec<String>,
    #[serde(default)]
    pub transforms: HashMap<String, ChannelTransform>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParseSessionConfig {
    pub session_id: String,
    pub file_name: String,
    #[serde(default)]
    pub sheet_name: Option<String>,
    pub lap_col: String,
    #[serde(default)]
    pub time_col: Option<String>,
    #[serde(default)]
    pub dist_col: Option<String>,
    #[serde(default)]
    pub gap_time_threshold: Option<f64>,
    #[serde(default)]
    pub gap_dist_threshold: Option<f64>,
    #[serde(default)]
    pub group_overrides: HashMap<String, GroupChannelOverride>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LapSummary {
    pub lap_number: i32,
    pub duration: f64,
    pub distance: f64,
    pub sample_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionSummary {
    pub id: String,
    pub name: String,
    pub sheet_name: Option<String>,
    pub channels: Vec<String>,
    pub skipped_channels: Vec<String>,
    pub available_columns: Vec<String>,
    pub lap_col: String,
    pub time_col: Option<String>,
    pub dist_col: Option<String>,
    pub has_time: bool,
    pub has_dist: bool,
    pub laps: Vec<LapSummary>,
    pub gap_time_threshold: Option<f64>,
    pub gap_dist_threshold: Option<f64>,
    #[serde(default)]
    pub group_overrides: HashMap<String, GroupChannelOverride>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MapData {
    pub x: Vec<f64>,
    pub y: Vec<f64>,
    pub distance: Option<Vec<f64>>,
}
