use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FilePreview {
    pub columns: Vec<String>,
    pub rows: Vec<Vec<String>>,
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LocalCalcDef {
    #[serde(default)]
    pub name: String,
    pub target_slug: String,
    #[serde(default)]
    pub target_label: String,
    pub formula: String,
    pub inputs: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GlobalCalcDef {
    pub slug: String,
    pub label: String,
    #[serde(rename = "type")]
    pub kind: String, // "system" | "custom" | "calculated"
    #[serde(default)]
    pub unit: String,
    #[serde(default)]
    pub formula: String,
    #[serde(default)]
    pub inputs: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParseSessionConfig {
    pub session_id: String,
    pub file_name: String,
    /// { raw_column_name -> standard_channel_slug }
    pub mapping: HashMap<String, String>,
    #[serde(default)]
    pub local_calculated_channels: Vec<LocalCalcDef>,
    #[serde(default = "default_lap_slug")]
    pub lap_slug: String,
    #[serde(default = "default_time_slug")]
    pub time_slug: String,
    #[serde(default = "default_dist_slug")]
    pub dist_slug: String,
    pub preset_slug: Option<String>,
    pub preset_name: Option<String>,
    pub gap_time_threshold: Option<f64>,
    pub gap_dist_threshold: Option<f64>,
}

fn default_lap_slug() -> String {
    "lap_num".to_string()
}
fn default_time_slug() -> String {
    "lap_time".to_string()
}
fn default_dist_slug() -> String {
    "lap_dist".to_string()
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
    pub channels: Vec<String>,
    pub laps: Vec<LapSummary>,
    pub mapping: HashMap<String, String>,
    pub local_calculated_channels: Vec<LocalCalcDef>,
    pub preset_slug: Option<String>,
    pub preset_name: Option<String>,
    pub gap_time_threshold: Option<f64>,
    pub gap_dist_threshold: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MapData {
    pub x: Vec<f64>,
    pub y: Vec<f64>,
    pub distance: Option<Vec<f64>>,
}
