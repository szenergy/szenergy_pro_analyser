use crate::types::{FilePreview, RawTable};
use std::collections::HashMap;

const TDMS_MAGIC: &[u8; 4] = b"TDSm";
const LEAD_IN_LEN: usize = 28;
const TDMS_VERSION_1: u32 = 4712;
const TDMS_VERSION_2: u32 = 4713;

// ToC bit flags
const K_TOC_META_DATA: u32 = 1 << 1;
const K_TOC_NEW_OBJ_LIST: u32 = 1 << 2;
const K_TOC_RAW_DATA: u32 = 1 << 3;
const K_TOC_INTERLEAVED_DATA: u32 = 1 << 5;
const K_TOC_BIG_ENDIAN: u32 = 1 << 6;
const K_TOC_DAQMX_RAW_DATA: u32 = 1 << 7;

// Raw data index markers
const RAW_IDX_NONE: u32 = 0xFFFF_FFFF;
const RAW_IDX_REUSE: u32 = 0x0000_0000;
const RAW_IDX_DAQMX_FORMAT_CHANGING: u32 = 0x0000_1269;
const RAW_IDX_DAQMX_DIGITAL_LINE: u32 = 0x0000_126A;

// TDMS data type codes
const TDS_TYPE_VOID: u32 = 0x00;
const TDS_TYPE_I8: u32 = 0x01;
const TDS_TYPE_I16: u32 = 0x02;
const TDS_TYPE_I32: u32 = 0x03;
const TDS_TYPE_I64: u32 = 0x04;
const TDS_TYPE_U8: u32 = 0x05;
const TDS_TYPE_U16: u32 = 0x06;
const TDS_TYPE_U32: u32 = 0x07;
const TDS_TYPE_U64: u32 = 0x08;
const TDS_TYPE_SINGLE_FLOAT: u32 = 0x09;
const TDS_TYPE_DOUBLE_FLOAT: u32 = 0x0A;
const TDS_TYPE_EXTENDED_FLOAT: u32 = 0x0B;
const TDS_TYPE_SINGLE_FLOAT_WITH_UNIT: u32 = 0x19;
const TDS_TYPE_DOUBLE_FLOAT_WITH_UNIT: u32 = 0x1A;
const TDS_TYPE_EXTENDED_FLOAT_WITH_UNIT: u32 = 0x1B;
const TDS_TYPE_STRING: u32 = 0x20;
const TDS_TYPE_BOOLEAN: u32 = 0x21;
const TDS_TYPE_TIMESTAMP: u32 = 0x44;
const TDS_TYPE_COMPLEX_SINGLE_FLOAT: u32 = 0x08_000C;
const TDS_TYPE_COMPLEX_DOUBLE_FLOAT: u32 = 0x10_000D;
const TDS_TYPE_DAQMX_RAW_DATA: u32 = 0xFFFF_FFFF;

#[derive(Debug, Clone)]
struct RawDataIndex {
    data_type: u32,
    array_dim: u32,
    num_values: u64,
    total_string_bytes: u64,
}

impl RawDataIndex {
    fn chunk_byte_size(&self) -> Result<usize, String> {
        if self.data_type == TDS_TYPE_STRING {
            usize::try_from(self.total_string_bytes)
                .map_err(|_| "TDMS string chunk size overflows usize".to_string())
        } else {
            let elem_size = fixed_type_byte_size(self.data_type).ok_or_else(|| {
                format!("Unsupported TDMS channel data type: 0x{:X}", self.data_type)
            })?;
            let count = self
                .num_values
                .checked_mul(self.array_dim as u64)
                .and_then(|v| v.checked_mul(elem_size as u64))
                .ok_or_else(|| "TDMS raw chunk size overflow".to_string())?;
            usize::try_from(count).map_err(|_| "TDMS raw chunk size overflows usize".to_string())
        }
    }

    fn value_count(&self) -> Result<usize, String> {
        let count = self
            .num_values
            .checked_mul(self.array_dim as u64)
            .ok_or_else(|| "TDMS value count overflow".to_string())?;
        usize::try_from(count).map_err(|_| "TDMS value count overflows usize".to_string())
    }
}

#[derive(Debug, Clone)]
struct ActiveObject {
    object_path: String,
    channel_idx: Option<usize>,
    raw_index: RawDataIndex,
}

struct Cursor<'a> {
    bytes: &'a [u8],
    pos: usize,
    big_endian: bool,
}

impl<'a> Cursor<'a> {
    fn new(bytes: &'a [u8], pos: usize, big_endian: bool) -> Self {
        Self {
            bytes,
            pos,
            big_endian,
        }
    }

    fn read_bytes(&mut self, len: usize) -> Result<&'a [u8], String> {
        let end = self
            .pos
            .checked_add(len)
            .ok_or_else(|| "TDMS cursor overflow".to_string())?;
        if end > self.bytes.len() {
            return Err(format!(
                "Unexpected EOF in TDMS data at offset {} (needed {} bytes, {} remaining)",
                self.pos,
                len,
                self.bytes.len().saturating_sub(self.pos)
            ));
        }
        let slice = &self.bytes[self.pos..end];
        self.pos = end;
        Ok(slice)
    }

    fn skip(&mut self, len: usize) -> Result<(), String> {
        let end = self
            .pos
            .checked_add(len)
            .ok_or_else(|| "TDMS cursor overflow".to_string())?;
        if end > self.bytes.len() {
            return Err(format!(
                "Unexpected EOF while skipping {} TDMS bytes at offset {}",
                len, self.pos
            ));
        }
        self.pos = end;
        Ok(())
    }

    fn read_u32(&mut self) -> Result<u32, String> {
        let b = self.read_bytes(4)?;
        let arr: [u8; 4] = b.try_into().unwrap();
        Ok(if self.big_endian {
            u32::from_be_bytes(arr)
        } else {
            u32::from_le_bytes(arr)
        })
    }

    fn read_u64(&mut self) -> Result<u64, String> {
        let b = self.read_bytes(8)?;
        let arr: [u8; 8] = b.try_into().unwrap();
        Ok(if self.big_endian {
            u64::from_be_bytes(arr)
        } else {
            u64::from_le_bytes(arr)
        })
    }

    fn read_string(&mut self) -> Result<String, String> {
        let len = self.read_u32()? as usize;
        let raw = self.read_bytes(len)?;
        let trimmed = match raw.last() {
            Some(0) => &raw[..raw.len() - 1],
            _ => raw,
        };
        Ok(String::from_utf8_lossy(trimmed).into_owned())
    }
}

fn fixed_type_byte_size(data_type: u32) -> Option<usize> {
    match data_type {
        TDS_TYPE_VOID => Some(0),
        TDS_TYPE_I8 | TDS_TYPE_U8 | TDS_TYPE_BOOLEAN => Some(1),
        TDS_TYPE_I16 | TDS_TYPE_U16 => Some(2),
        TDS_TYPE_I32 | TDS_TYPE_U32 | TDS_TYPE_SINGLE_FLOAT | TDS_TYPE_SINGLE_FLOAT_WITH_UNIT => {
            Some(4)
        }
        TDS_TYPE_I64
        | TDS_TYPE_U64
        | TDS_TYPE_DOUBLE_FLOAT
        | TDS_TYPE_DOUBLE_FLOAT_WITH_UNIT
        | TDS_TYPE_COMPLEX_SINGLE_FLOAT => Some(8),
        TDS_TYPE_TIMESTAMP
        | TDS_TYPE_EXTENDED_FLOAT
        | TDS_TYPE_EXTENDED_FLOAT_WITH_UNIT
        | TDS_TYPE_COMPLEX_DOUBLE_FLOAT => Some(16),
        _ => None,
    }
}

fn decode_numeric_to_f64(slice: &[u8], data_type: u32, big_endian: bool) -> Result<f64, String> {
    match data_type {
        TDS_TYPE_I8 => Ok((slice[0] as i8) as f64),
        TDS_TYPE_I16 => {
            let arr: [u8; 2] = slice.try_into().unwrap();
            let v = if big_endian {
                i16::from_be_bytes(arr)
            } else {
                i16::from_le_bytes(arr)
            };
            Ok(v as f64)
        }
        TDS_TYPE_I32 => {
            let arr: [u8; 4] = slice.try_into().unwrap();
            let v = if big_endian {
                i32::from_be_bytes(arr)
            } else {
                i32::from_le_bytes(arr)
            };
            Ok(v as f64)
        }
        TDS_TYPE_I64 => {
            let arr: [u8; 8] = slice.try_into().unwrap();
            let v = if big_endian {
                i64::from_be_bytes(arr)
            } else {
                i64::from_le_bytes(arr)
            };
            Ok(v as f64)
        }
        TDS_TYPE_U8 => Ok(slice[0] as f64),
        TDS_TYPE_U16 => {
            let arr: [u8; 2] = slice.try_into().unwrap();
            let v = if big_endian {
                u16::from_be_bytes(arr)
            } else {
                u16::from_le_bytes(arr)
            };
            Ok(v as f64)
        }
        TDS_TYPE_U32 => {
            let arr: [u8; 4] = slice.try_into().unwrap();
            let v = if big_endian {
                u32::from_be_bytes(arr)
            } else {
                u32::from_le_bytes(arr)
            };
            Ok(v as f64)
        }
        TDS_TYPE_U64 => {
            let arr: [u8; 8] = slice.try_into().unwrap();
            let v = if big_endian {
                u64::from_be_bytes(arr)
            } else {
                u64::from_le_bytes(arr)
            };
            Ok(v as f64)
        }
        TDS_TYPE_SINGLE_FLOAT | TDS_TYPE_SINGLE_FLOAT_WITH_UNIT => {
            let arr: [u8; 4] = slice.try_into().unwrap();
            let v = if big_endian {
                f32::from_be_bytes(arr)
            } else {
                f32::from_le_bytes(arr)
            };
            Ok(v as f64)
        }
        TDS_TYPE_DOUBLE_FLOAT | TDS_TYPE_DOUBLE_FLOAT_WITH_UNIT => {
            let arr: [u8; 8] = slice.try_into().unwrap();
            let v = if big_endian {
                f64::from_be_bytes(arr)
            } else {
                f64::from_le_bytes(arr)
            };
            Ok(v)
        }
        TDS_TYPE_BOOLEAN => Ok(if slice[0] != 0 { 1.0 } else { 0.0 }),
        TDS_TYPE_TIMESTAMP => {
            let (sec, frac) = if big_endian {
                let s = i64::from_be_bytes(slice[0..8].try_into().unwrap());
                let f = u64::from_be_bytes(slice[8..16].try_into().unwrap());
                (s, f)
            } else {
                let f = u64::from_le_bytes(slice[0..8].try_into().unwrap());
                let s = i64::from_le_bytes(slice[8..16].try_into().unwrap());
                (s, f)
            };
            Ok((sec as f64) + (frac as f64) * 2.0_f64.powi(-64))
        }
        TDS_TYPE_STRING => Ok(f64::NAN),
        other => Err(format!("Unsupported TDMS numeric data type: 0x{other:X}")),
    }
}

fn format_preview_f64(v: f64) -> String {
    if v.is_nan() {
        String::new()
    } else if v == 0.0 {
        "0".to_string()
    } else {
        v.to_string()
    }
}

fn decode_string_chunk(
    raw: &[u8],
    num_values: usize,
    big_endian: bool,
) -> Result<Vec<String>, String> {
    let offsets_bytes = num_values
        .checked_mul(4)
        .ok_or_else(|| "TDMS string offset table overflow".to_string())?;
    if raw.len() < offsets_bytes {
        return Err(format!(
            "TDMS string chunk truncated: expected at least {} offset bytes, got {}",
            offsets_bytes,
            raw.len()
        ));
    }
    let payload = &raw[offsets_bytes..];
    let mut out = Vec::with_capacity(num_values);
    let mut prev_end = 0usize;
    for i in 0..num_values {
        let off_slice: [u8; 4] = raw[i * 4..(i + 1) * 4].try_into().unwrap();
        let end = (if big_endian {
            u32::from_be_bytes(off_slice)
        } else {
            u32::from_le_bytes(off_slice)
        }) as usize;
        if end < prev_end || end > payload.len() {
            return Err(format!(
                "Invalid TDMS string offset {} (prev={}, payload_len={})",
                end,
                prev_end,
                payload.len()
            ));
        }
        let s_raw = &payload[prev_end..end];
        let trimmed = match s_raw.last() {
            Some(0) => &s_raw[..s_raw.len() - 1],
            _ => s_raw,
        };
        out.push(String::from_utf8_lossy(trimmed).into_owned());
        prev_end = end;
    }
    Ok(out)
}

/// Converts a TDMS object path like `/'Group'/'Channel'` into `Some("Group/Channel")`.
/// Returns `None` for root (`"/"`) or group (`"/'Group'"`) objects.
fn parse_channel_name(object_path: &str) -> Option<String> {
    let rest = object_path.strip_prefix('/')?;
    if rest.is_empty() {
        return None;
    }

    let (group, after_group) = parse_path_component(rest)?;
    let after_slash = after_group.strip_prefix('/')?;
    if after_slash.is_empty() {
        return None;
    }

    let (channel, trailing) = parse_path_component(after_slash)?;
    if !trailing.is_empty() {
        return None;
    }

    Some(format!("{group}/{channel}"))
}

fn parse_path_component(input: &str) -> Option<(String, &str)> {
    if let Some(after_open) = input.strip_prefix('\'') {
        let mut out = String::new();
        let mut chars = after_open.char_indices().peekable();
        while let Some((idx, ch)) = chars.next() {
            if ch == '\'' {
                if let Some(&(_, '\'')) = chars.peek() {
                    out.push('\'');
                    chars.next();
                } else {
                    return Some((out, &after_open[idx + 1..]));
                }
            } else {
                out.push(ch);
            }
        }
        None
    } else {
        match input.find('/') {
            Some(pos) => Some((input[..pos].to_string(), &input[pos..])),
            None => Some((input.to_string(), "")),
        }
    }
}

fn skip_properties(cursor: &mut Cursor<'_>) -> Result<(), String> {
    let num_props = cursor.read_u32()?;
    for _ in 0..num_props {
        let _name = cursor.read_string()?;
        let prop_type = cursor.read_u32()?;
        if prop_type == TDS_TYPE_STRING {
            let len = cursor.read_u32()? as usize;
            cursor.skip(len)?;
        } else if let Some(size) = fixed_type_byte_size(prop_type) {
            cursor.skip(size)?;
        } else {
            return Err(format!(
                "Unsupported TDMS property data type: 0x{prop_type:X}"
            ));
        }
    }
    Ok(())
}

struct ParsedLeadIn {
    toc_mask: u32,
    big_endian: bool,
    raw_start: usize,
    seg_end: usize,
    next_seg_pos: Option<usize>,
}

fn parse_lead_in(bytes: &[u8], seg_start: usize) -> Result<ParsedLeadIn, String> {
    if seg_start + LEAD_IN_LEN > bytes.len() {
        return Err(format!(
            "Truncated TDMS segment lead-in at offset {}",
            seg_start
        ));
    }

    if &bytes[seg_start..seg_start + 4] != TDMS_MAGIC {
        return Err(format!(
            "Invalid TDMS segment magic at offset {}: expected 'TDSm'",
            seg_start
        ));
    }

    // ToC bitmask is always stored in little-endian per NI TDMS spec.
    let toc_mask = u32::from_le_bytes(bytes[seg_start + 4..seg_start + 8].try_into().unwrap());
    if (toc_mask & K_TOC_DAQMX_RAW_DATA) != 0 {
        return Err("TDMS segment uses DAQmx raw data, which is not supported".to_string());
    }

    let big_endian = (toc_mask & K_TOC_BIG_ENDIAN) != 0;
    let mut cursor = Cursor::new(bytes, seg_start + 8, big_endian);
    let version = cursor.read_u32()?;
    if version != TDMS_VERSION_2 && version != TDMS_VERSION_1 {
        return Err(format!("Unsupported TDMS version: {version}"));
    }

    let next_segment_offset = cursor.read_u64()?;
    let raw_data_offset = cursor.read_u64()?;

    let body_start = seg_start + LEAD_IN_LEN;
    let raw_off_usize = usize::try_from(raw_data_offset)
        .map_err(|_| "TDMS raw_data_offset overflows usize".to_string())?;
    let raw_start = body_start
        .checked_add(raw_off_usize)
        .ok_or_else(|| "TDMS raw_start overflow".to_string())?;

    let (seg_end, next_seg_pos) = if next_segment_offset == u64::MAX {
        if raw_start > bytes.len() {
            return Err("TDMS raw_data_offset exceeds file length".to_string());
        }
        (bytes.len(), None)
    } else {
        if raw_data_offset > next_segment_offset {
            return Err(format!(
                "TDMS raw_data_offset ({raw_data_offset}) exceeds next_segment_offset ({next_segment_offset})"
            ));
        }
        let next_off_usize = usize::try_from(next_segment_offset)
            .map_err(|_| "TDMS next_segment_offset overflows usize".to_string())?;
        let end = body_start
            .checked_add(next_off_usize)
            .ok_or_else(|| "TDMS next_segment_offset overflow".to_string())?;
        if end > bytes.len() {
            return Err(format!(
                "TDMS segment at {} extends past EOF ({} > {})",
                seg_start,
                end,
                bytes.len()
            ));
        }
        (end, Some(end))
    };

    Ok(ParsedLeadIn {
        toc_mask,
        big_endian,
        raw_start,
        seg_end,
        next_seg_pos,
    })
}

struct TdmsState {
    columns: Vec<String>,
    channel_map: HashMap<String, usize>,
    last_raw_indices: HashMap<String, RawDataIndex>,
    active_objects: Vec<ActiveObject>,
}

impl TdmsState {
    fn new() -> Self {
        Self {
            columns: Vec::new(),
            channel_map: HashMap::new(),
            last_raw_indices: HashMap::new(),
            active_objects: Vec::new(),
        }
    }

    fn ensure_channel(&mut self, object_path: &str) -> Option<usize> {
        let name = parse_channel_name(object_path)?;
        if let Some(&idx) = self.channel_map.get(&name) {
            Some(idx)
        } else {
            let idx = self.columns.len();
            self.columns.push(name.clone());
            self.channel_map.insert(name, idx);
            Some(idx)
        }
    }

    fn process_metadata(
        &mut self,
        bytes: &[u8],
        meta_start: usize,
        meta_end: usize,
        toc_mask: u32,
        big_endian: bool,
    ) -> Result<(), String> {
        let new_obj_list = (toc_mask & K_TOC_NEW_OBJ_LIST) != 0;
        if new_obj_list {
            self.active_objects.clear();
        }

        if (toc_mask & K_TOC_META_DATA) == 0 {
            return Ok(());
        }

        let mut cursor = Cursor::new(&bytes[..meta_end], meta_start, big_endian);
        let num_objects = cursor.read_u32()?;

        for _ in 0..num_objects {
            let object_path = cursor.read_string()?;
            let channel_idx = self.ensure_channel(&object_path);
            let raw_idx_marker = cursor.read_u32()?;

            match raw_idx_marker {
                RAW_IDX_NONE => {
                    if !new_obj_list {
                        self.active_objects
                            .retain(|obj| obj.object_path != object_path);
                    }
                }
                RAW_IDX_DAQMX_FORMAT_CHANGING | RAW_IDX_DAQMX_DIGITAL_LINE => {
                    return Err(
                        "TDMS object uses DAQmx raw data index, which is not supported"
                            .to_string(),
                    );
                }
                RAW_IDX_REUSE => {
                    let cached = self
                        .last_raw_indices
                        .get(&object_path)
                        .cloned()
                        .ok_or_else(|| {
                            format!(
                                "TDMS object '{object_path}' specifies raw_idx == 0 with no previous raw index"
                            )
                        })?;
                    self.upsert_active_object(&object_path, channel_idx, cached, new_obj_list);
                }
                _ => {
                    let data_type = cursor.read_u32()?;
                    if data_type == TDS_TYPE_DAQMX_RAW_DATA {
                        return Err("TDMS object uses DAQmx raw data type, which is not supported"
                            .to_string());
                    }
                    let array_dim = cursor.read_u32()?;
                    if array_dim != 1 {
                        return Err(format!(
                            "Unsupported TDMS array dimension {array_dim} for '{object_path}' (expected 1)"
                        ));
                    }
                    let num_values = cursor.read_u64()?;
                    let total_string_bytes = if data_type == TDS_TYPE_STRING {
                        cursor.read_u64()?
                    } else {
                        0
                    };

                    let raw_index = RawDataIndex {
                        data_type,
                        array_dim,
                        num_values,
                        total_string_bytes,
                    };
                    self.last_raw_indices
                        .insert(object_path.clone(), raw_index.clone());
                    self.upsert_active_object(&object_path, channel_idx, raw_index, new_obj_list);
                }
            }

            skip_properties(&mut cursor)?;
        }

        Ok(())
    }

    fn upsert_active_object(
        &mut self,
        object_path: &str,
        channel_idx: Option<usize>,
        raw_index: RawDataIndex,
        new_obj_list: bool,
    ) {
        if !new_obj_list {
            if let Some(existing) = self
                .active_objects
                .iter_mut()
                .find(|obj| obj.object_path == object_path)
            {
                existing.channel_idx = channel_idx;
                existing.raw_index = raw_index;
                return;
            }
        }
        self.active_objects.push(ActiveObject {
            object_path: object_path.to_string(),
            channel_idx,
            raw_index,
        });
    }
}

fn compute_chunk_layout(
    active_objects: &[ActiveObject],
    segment_raw_bytes: usize,
    unbounded_segment: bool,
) -> Result<(usize, usize), String> {
    if segment_raw_bytes == 0 {
        return Ok((0, 0));
    }

    let mut chunk_total_bytes = 0usize;
    for obj in active_objects {
        chunk_total_bytes = chunk_total_bytes
            .checked_add(obj.raw_index.chunk_byte_size()?)
            .ok_or_else(|| "TDMS chunk_total_bytes overflow".to_string())?;
    }

    if chunk_total_bytes == 0 {
        return Err("TDMS segment contains raw data but chunk_total_bytes is zero".to_string());
    }

    if !unbounded_segment && (segment_raw_bytes % chunk_total_bytes != 0) {
        return Err(format!(
            "TDMS raw data size ({segment_raw_bytes}) is not a multiple of chunk size ({chunk_total_bytes})"
        ));
    }

    Ok((segment_raw_bytes / chunk_total_bytes, chunk_total_bytes))
}

pub fn parse_tdms(bytes: &[u8]) -> Result<RawTable, String> {
    if bytes.is_empty() {
        return Err("Empty TDMS file".to_string());
    }

    let mut state = TdmsState::new();
    let mut channel_data: Vec<Vec<f64>> = Vec::new();
    let mut seg_start = 0usize;

    while seg_start < bytes.len() {
        let lead = parse_lead_in(bytes, seg_start)?;
        let meta_start = seg_start + LEAD_IN_LEN;
        state.process_metadata(
            bytes,
            meta_start,
            lead.raw_start,
            lead.toc_mask,
            lead.big_endian,
        )?;
        channel_data.resize_with(state.columns.len(), Vec::new);

        if (lead.toc_mask & K_TOC_RAW_DATA) != 0 {
            let segment_raw_bytes = lead.seg_end.saturating_sub(lead.raw_start);
            let (chunk_count, _) = compute_chunk_layout(
                &state.active_objects,
                segment_raw_bytes,
                lead.next_seg_pos.is_none(),
            )?;

            if chunk_count > 0 {
                for obj in &state.active_objects {
                    if let Some(ch_idx) = obj.channel_idx {
                        let per_chunk = obj.raw_index.value_count()?;
                        if let Some(total) = per_chunk.checked_mul(chunk_count) {
                            channel_data[ch_idx].reserve(total);
                        }
                    }
                }

                let interleaved = (lead.toc_mask & K_TOC_INTERLEAVED_DATA) != 0;
                let mut pos = lead.raw_start;

                if interleaved {
                    read_interleaved_full(
                        bytes,
                        &mut pos,
                        &state.active_objects,
                        chunk_count,
                        lead.big_endian,
                        &mut channel_data,
                    )?;
                } else {
                    read_contiguous_full(
                        bytes,
                        &mut pos,
                        &state.active_objects,
                        chunk_count,
                        lead.big_endian,
                        &mut channel_data,
                    )?;
                }
            }
        }

        match lead.next_seg_pos {
            Some(next) => seg_start = next,
            None => break,
        }
    }

    let max_len = channel_data.iter().map(|c| c.len()).max().unwrap_or(0);
    for col in &mut channel_data {
        if col.len() < max_len {
            col.resize(max_len, f64::NAN);
        }
    }

    Ok(RawTable {
        columns: state.columns,
        data: channel_data,
        row_count: max_len,
    })
}

fn read_contiguous_full(
    bytes: &[u8],
    pos: &mut usize,
    active_objects: &[ActiveObject],
    chunk_count: usize,
    big_endian: bool,
    channel_data: &mut [Vec<f64>],
) -> Result<(), String> {
    for _ in 0..chunk_count {
        for obj in active_objects {
            let chunk_bytes = obj.raw_index.chunk_byte_size()?;
            let val_count = obj.raw_index.value_count()?;
            let slice = &bytes[*pos..*pos + chunk_bytes];
            *pos += chunk_bytes;

            let Some(ch_idx) = obj.channel_idx else {
                continue;
            };
            let out = &mut channel_data[ch_idx];

            if obj.raw_index.data_type == TDS_TYPE_STRING {
                out.resize(out.len() + val_count, f64::NAN);
            } else {
                let elem_size = fixed_type_byte_size(obj.raw_index.data_type).unwrap();
                if elem_size == 0 {
                    out.resize(out.len() + val_count, f64::NAN);
                } else {
                    for i in 0..val_count {
                        let v = decode_numeric_to_f64(
                            &slice[i * elem_size..(i + 1) * elem_size],
                            obj.raw_index.data_type,
                            big_endian,
                        )?;
                        out.push(v);
                    }
                }
            }
        }
    }
    Ok(())
}

fn read_interleaved_full(
    bytes: &[u8],
    pos: &mut usize,
    active_objects: &[ActiveObject],
    chunk_count: usize,
    big_endian: bool,
    channel_data: &mut [Vec<f64>],
) -> Result<(), String> {
    for obj in active_objects {
        if obj.raw_index.data_type == TDS_TYPE_STRING && obj.raw_index.num_values > 0 {
            return Err("String channels are not supported in interleaved TDMS segments".to_string());
        }
    }

    let mut per_obj_info = Vec::with_capacity(active_objects.len());
    let mut max_vals_per_chunk = 0usize;
    for obj in active_objects {
        let val_count = obj.raw_index.value_count()?;
        let elem_size = fixed_type_byte_size(obj.raw_index.data_type).ok_or_else(|| {
            format!(
                "Unsupported TDMS interleaved data type: 0x{:X}",
                obj.raw_index.data_type
            )
        })?;
        max_vals_per_chunk = max_vals_per_chunk.max(val_count);
        per_obj_info.push((obj.channel_idx, obj.raw_index.data_type, elem_size, val_count));
    }

    for _ in 0..chunk_count {
        for sample_idx in 0..max_vals_per_chunk {
            for &(ch_idx, data_type, elem_size, val_count) in &per_obj_info {
                if sample_idx >= val_count {
                    continue;
                }
                let slice = &bytes[*pos..*pos + elem_size];
                *pos += elem_size;
                if let Some(idx) = ch_idx {
                    if elem_size == 0 {
                        channel_data[idx].push(f64::NAN);
                    } else {
                        let v = decode_numeric_to_f64(slice, data_type, big_endian)?;
                        channel_data[idx].push(v);
                    }
                }
            }
        }
    }

    Ok(())
}

pub fn preview_tdms(bytes: &[u8], max_rows: usize) -> Result<FilePreview, String> {
    if bytes.is_empty() {
        return Err("Empty TDMS file".to_string());
    }

    let mut state = TdmsState::new();
    let mut channel_previews: Vec<Vec<String>> = Vec::new();
    let mut seg_start = 0usize;

    while seg_start < bytes.len() {
        let lead = parse_lead_in(bytes, seg_start)?;
        let meta_start = seg_start + LEAD_IN_LEN;
        state.process_metadata(
            bytes,
            meta_start,
            lead.raw_start,
            lead.toc_mask,
            lead.big_endian,
        )?;
        channel_previews.resize_with(state.columns.len(), Vec::new);

        if max_rows > 0 && (lead.toc_mask & K_TOC_RAW_DATA) != 0 {
            let max_needed = state
                .active_objects
                .iter()
                .filter_map(|obj| obj.channel_idx)
                .map(|idx| max_rows.saturating_sub(channel_previews[idx].len()))
                .max()
                .unwrap_or(0);

            if max_needed > 0 {
                let segment_raw_bytes = lead.seg_end.saturating_sub(lead.raw_start);
                let (chunk_count, _) = compute_chunk_layout(
                    &state.active_objects,
                    segment_raw_bytes,
                    lead.next_seg_pos.is_none(),
                )?;

                if chunk_count > 0 {
                    let interleaved = (lead.toc_mask & K_TOC_INTERLEAVED_DATA) != 0;
                    let mut pos = lead.raw_start;

                    if interleaved {
                        read_interleaved_preview(
                            bytes,
                            &mut pos,
                            &state.active_objects,
                            chunk_count,
                            lead.big_endian,
                            max_rows,
                            &mut channel_previews,
                        )?;
                    } else {
                        read_contiguous_preview(
                            bytes,
                            &mut pos,
                            &state.active_objects,
                            chunk_count,
                            lead.big_endian,
                            max_rows,
                            &mut channel_previews,
                        )?;
                    }
                }
            }
        }

        match lead.next_seg_pos {
            Some(next) => seg_start = next,
            None => break,
        }
    }

    let preview_row_count = channel_previews
        .iter()
        .map(|c| c.len())
        .max()
        .unwrap_or(0)
        .min(max_rows);

    let mut rows = Vec::with_capacity(preview_row_count);
    for r in 0..preview_row_count {
        let mut row = Vec::with_capacity(state.columns.len());
        for col in &channel_previews {
            if r < col.len() {
                row.push(col[r].clone());
            } else {
                row.push(String::new());
            }
        }
        rows.push(row);
    }

    Ok(FilePreview {
        columns: state.columns,
        rows,
    })
}

fn read_contiguous_preview(
    bytes: &[u8],
    pos: &mut usize,
    active_objects: &[ActiveObject],
    chunk_count: usize,
    big_endian: bool,
    max_rows: usize,
    channel_previews: &mut [Vec<String>],
) -> Result<(), String> {
    for _ in 0..chunk_count {
        let mut any_needed = false;
        for obj in active_objects {
            if let Some(ch_idx) = obj.channel_idx {
                if channel_previews[ch_idx].len() < max_rows {
                    any_needed = true;
                    break;
                }
            }
        }
        if !any_needed {
            break;
        }

        for obj in active_objects {
            let chunk_bytes = obj.raw_index.chunk_byte_size()?;
            let val_count = obj.raw_index.value_count()?;
            let slice = &bytes[*pos..*pos + chunk_bytes];
            *pos += chunk_bytes;

            let Some(ch_idx) = obj.channel_idx else {
                continue;
            };
            let out = &mut channel_previews[ch_idx];
            if out.len() >= max_rows {
                continue;
            }
            let take = val_count.min(max_rows - out.len());
            if take == 0 {
                continue;
            }

            if obj.raw_index.data_type == TDS_TYPE_STRING {
                let strings = decode_string_chunk(slice, val_count, big_endian)?;
                out.extend(strings.into_iter().take(take));
            } else {
                let elem_size = fixed_type_byte_size(obj.raw_index.data_type).unwrap();
                if elem_size == 0 {
                    out.resize(out.len() + take, String::new());
                } else {
                    for i in 0..take {
                        let v = decode_numeric_to_f64(
                            &slice[i * elem_size..(i + 1) * elem_size],
                            obj.raw_index.data_type,
                            big_endian,
                        )?;
                        out.push(format_preview_f64(v));
                    }
                }
            }
        }
    }
    Ok(())
}

fn read_interleaved_preview(
    bytes: &[u8],
    pos: &mut usize,
    active_objects: &[ActiveObject],
    chunk_count: usize,
    big_endian: bool,
    max_rows: usize,
    channel_previews: &mut [Vec<String>],
) -> Result<(), String> {
    for obj in active_objects {
        if obj.raw_index.data_type == TDS_TYPE_STRING && obj.raw_index.num_values > 0 {
            return Err("String channels are not supported in interleaved TDMS segments".to_string());
        }
    }

    let mut per_obj_info = Vec::with_capacity(active_objects.len());
    let mut max_vals_per_chunk = 0usize;
    for obj in active_objects {
        let val_count = obj.raw_index.value_count()?;
        let elem_size = fixed_type_byte_size(obj.raw_index.data_type).ok_or_else(|| {
            format!(
                "Unsupported TDMS interleaved data type: 0x{:X}",
                obj.raw_index.data_type
            )
        })?;
        max_vals_per_chunk = max_vals_per_chunk.max(val_count);
        per_obj_info.push((obj.channel_idx, obj.raw_index.data_type, elem_size, val_count));
    }

    for _ in 0..chunk_count {
        for sample_idx in 0..max_vals_per_chunk {
            let mut any_needed = false;
            for &(ch_idx, _, _, _) in &per_obj_info {
                if let Some(idx) = ch_idx {
                    if channel_previews[idx].len() < max_rows {
                        any_needed = true;
                        break;
                    }
                }
            }
            if !any_needed {
                return Ok(());
            }

            for &(ch_idx, data_type, elem_size, val_count) in &per_obj_info {
                if sample_idx >= val_count {
                    continue;
                }
                let slice = &bytes[*pos..*pos + elem_size];
                *pos += elem_size;
                if let Some(idx) = ch_idx {
                    if channel_previews[idx].len() < max_rows {
                        if elem_size == 0 {
                            channel_previews[idx].push(String::new());
                        } else {
                            let v = decode_numeric_to_f64(slice, data_type, big_endian)?;
                            channel_previews[idx].push(format_preview_f64(v));
                        }
                    }
                }
            }
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn push_str(buf: &mut Vec<u8>, s: &str, be: bool) {
        let len = s.len() as u32;
        buf.extend_from_slice(&if be {
            len.to_be_bytes()
        } else {
            len.to_le_bytes()
        });
        buf.extend_from_slice(s.as_bytes());
    }

    fn push_u32(buf: &mut Vec<u8>, v: u32, be: bool) {
        buf.extend_from_slice(&if be { v.to_be_bytes() } else { v.to_le_bytes() });
    }

    fn push_u64(buf: &mut Vec<u8>, v: u64, be: bool) {
        buf.extend_from_slice(&if be { v.to_be_bytes() } else { v.to_le_bytes() });
    }

    fn build_segment(
        toc_mask: u32,
        meta_bytes: &[u8],
        raw_bytes: &[u8],
        unbounded: bool,
    ) -> Vec<u8> {
        let be = (toc_mask & K_TOC_BIG_ENDIAN) != 0;
        let mut seg = Vec::new();
        seg.extend_from_slice(TDMS_MAGIC);
        // ToC is always little-endian
        seg.extend_from_slice(&toc_mask.to_le_bytes());
        push_u32(&mut seg, TDMS_VERSION_2, be);

        let raw_data_offset = meta_bytes.len() as u64;
        let next_segment_offset = if unbounded {
            u64::MAX
        } else {
            (meta_bytes.len() + raw_bytes.len()) as u64
        };
        push_u64(&mut seg, next_segment_offset, be);
        push_u64(&mut seg, raw_data_offset, be);
        seg.extend_from_slice(meta_bytes);
        seg.extend_from_slice(raw_bytes);
        seg
    }

    #[test]
    fn test_all_numeric_types_contiguous_and_properties() {
        let mut meta = Vec::new();
        // 13 objects: 1 group + 12 typed channels
        push_u32(&mut meta, 13, false);

        // Group with properties (string + timestamp + i32)
        push_str(&mut meta, "/'Test''Group'", false);
        push_u32(&mut meta, RAW_IDX_NONE, false);
        push_u32(&mut meta, 3, false); // 3 props
        push_str(&mut meta, "author", false);
        push_u32(&mut meta, TDS_TYPE_STRING, false);
        push_str(&mut meta, "szenergy", false);
        push_str(&mut meta, "start", false);
        push_u32(&mut meta, TDS_TYPE_TIMESTAMP, false);
        meta.extend_from_slice(&0u64.to_le_bytes());
        meta.extend_from_slice(&100i64.to_le_bytes());
        push_str(&mut meta, "run", false);
        push_u32(&mut meta, TDS_TYPE_I32, false);
        meta.extend_from_slice(&42i32.to_le_bytes());

        let channels: &[(&str, u32)] = &[
            ("c_i8", TDS_TYPE_I8),
            ("c_i16", TDS_TYPE_I16),
            ("c_i32", TDS_TYPE_I32),
            ("c_i64", TDS_TYPE_I64),
            ("c_u8", TDS_TYPE_U8),
            ("c_u16", TDS_TYPE_U16),
            ("c_u32", TDS_TYPE_U32),
            ("c_u64", TDS_TYPE_U64),
            ("c_f32", TDS_TYPE_SINGLE_FLOAT),
            ("c_f64", TDS_TYPE_DOUBLE_FLOAT),
            ("c_bool", TDS_TYPE_BOOLEAN),
            ("c_ts", TDS_TYPE_TIMESTAMP),
        ];

        for &(name, dt) in channels {
            push_str(&mut meta, &format!("/'Test''Group'/'{name}'"), false);
            push_u32(&mut meta, 20, false);
            push_u32(&mut meta, dt, false);
            push_u32(&mut meta, 1, false); // array_dim
            push_u64(&mut meta, 2, false); // num_values
            push_u32(&mut meta, 0, false); // 0 props
        }

        let mut raw = Vec::new();
        raw.extend_from_slice(&[(-5i8) as u8, 5u8]);
        raw.extend_from_slice(&(-1000i16).to_le_bytes());
        raw.extend_from_slice(&1000i16.to_le_bytes());
        raw.extend_from_slice(&(-100_000i32).to_le_bytes());
        raw.extend_from_slice(&100_000i32.to_le_bytes());
        raw.extend_from_slice(&(-1_000_000_000_000i64).to_le_bytes());
        raw.extend_from_slice(&1_000_000_000_000i64.to_le_bytes());
        raw.extend_from_slice(&[0u8, 255u8]);
        raw.extend_from_slice(&10u16.to_le_bytes());
        raw.extend_from_slice(&65000u16.to_le_bytes());
        raw.extend_from_slice(&1u32.to_le_bytes());
        raw.extend_from_slice(&3_000_000_000u32.to_le_bytes());
        raw.extend_from_slice(&2u64.to_le_bytes());
        raw.extend_from_slice(&5_000_000_000u64.to_le_bytes());
        raw.extend_from_slice(&1.5f32.to_le_bytes());
        raw.extend_from_slice(&(-2.25f32).to_le_bytes());
        raw.extend_from_slice(&3.125f64.to_le_bytes());
        raw.extend_from_slice(&(-9.5f64).to_le_bytes());
        raw.extend_from_slice(&[1u8, 0u8]);
        // Timestamps: (0.5s at sec 10), (0.25s at sec 20)
        raw.extend_from_slice(&(1u64 << 63).to_le_bytes());
        raw.extend_from_slice(&10i64.to_le_bytes());
        raw.extend_from_slice(&(1u64 << 62).to_le_bytes());
        raw.extend_from_slice(&20i64.to_le_bytes());

        let file = build_segment(
            K_TOC_META_DATA | K_TOC_NEW_OBJ_LIST | K_TOC_RAW_DATA,
            &meta,
            &raw,
            false,
        );

        let table = parse_tdms(&file).unwrap();
        assert_eq!(table.row_count, 2);
        assert_eq!(table.columns.len(), 12);
        assert_eq!(table.columns[0], "Test'Group/c_i8");
        assert_eq!(table.column("Test'Group/c_i8").unwrap(), &[-5.0, 5.0]);
        assert_eq!(
            table.column("Test'Group/c_i16").unwrap(),
            &[-1000.0, 1000.0]
        );
        assert_eq!(
            table.column("Test'Group/c_i32").unwrap(),
            &[-100_000.0, 100_000.0]
        );
        assert_eq!(
            table.column("Test'Group/c_i64").unwrap(),
            &[-1e12, 1e12]
        );
        assert_eq!(table.column("Test'Group/c_u8").unwrap(), &[0.0, 255.0]);
        assert_eq!(table.column("Test'Group/c_u16").unwrap(), &[10.0, 65000.0]);
        assert_eq!(
            table.column("Test'Group/c_u32").unwrap(),
            &[1.0, 3_000_000_000.0]
        );
        assert_eq!(
            table.column("Test'Group/c_u64").unwrap(),
            &[2.0, 5_000_000_000.0]
        );
        assert_eq!(table.column("Test'Group/c_f32").unwrap(), &[1.5, -2.25]);
        assert_eq!(table.column("Test'Group/c_f64").unwrap(), &[3.125, -9.5]);
        assert_eq!(table.column("Test'Group/c_bool").unwrap(), &[1.0, 0.0]);
        assert_eq!(table.column("Test'Group/c_ts").unwrap(), &[10.5, 20.25]);
    }

    #[test]
    fn test_interleaved_multichunk_and_reuse_segments() {
        let mut file = Vec::new();

        // Segment 0: root metadata only
        let mut meta0 = Vec::new();
        push_u32(&mut meta0, 1, false);
        push_str(&mut meta0, "/", false);
        push_u32(&mut meta0, RAW_IDX_NONE, false);
        push_u32(&mut meta0, 0, false);
        file.extend_from_slice(&build_segment(
            K_TOC_META_DATA | K_TOC_NEW_OBJ_LIST,
            &meta0,
            &[],
            false,
        ));

        // Segment 1: interleaved, 2 channels, num_values=1 per chunk, 3 chunks
        let mut meta1 = Vec::new();
        push_u32(&mut meta1, 3, false);
        push_str(&mut meta1, "/'Measurements'", false);
        push_u32(&mut meta1, RAW_IDX_NONE, false);
        push_u32(&mut meta1, 0, false);
        for name in ["Time", "Speed"] {
            push_str(&mut meta1, &format!("/'Measurements'/'{name}'"), false);
            push_u32(&mut meta1, 20, false);
            push_u32(&mut meta1, TDS_TYPE_DOUBLE_FLOAT, false);
            push_u32(&mut meta1, 1, false);
            push_u64(&mut meta1, 1, false);
            push_u32(&mut meta1, 0, false);
        }
        let mut raw1 = Vec::new();
        for (t, s) in [(0.0f64, 10.0f64), (1.0, 20.0), (2.0, 30.0)] {
            raw1.extend_from_slice(&t.to_le_bytes());
            raw1.extend_from_slice(&s.to_le_bytes());
        }
        file.extend_from_slice(&build_segment(
            K_TOC_META_DATA | K_TOC_NEW_OBJ_LIST | K_TOC_RAW_DATA | K_TOC_INTERLEAVED_DATA,
            &meta1,
            &raw1,
            false,
        ));

        // Segment 2: kTocNewObjList with raw_idx=0 reuse, 2 more chunks, unbounded next_segment_offset=u64::MAX
        let mut meta2 = Vec::new();
        push_u32(&mut meta2, 2, false);
        for name in ["Time", "Speed"] {
            push_str(&mut meta2, &format!("/'Measurements'/'{name}'"), false);
            push_u32(&mut meta2, RAW_IDX_REUSE, false);
            push_u32(&mut meta2, 0, false);
        }
        let mut raw2 = Vec::new();
        for (t, s) in [(3.0f64, 40.0f64), (4.0, 50.0)] {
            raw2.extend_from_slice(&t.to_le_bytes());
            raw2.extend_from_slice(&s.to_le_bytes());
        }
        file.extend_from_slice(&build_segment(
            K_TOC_META_DATA | K_TOC_NEW_OBJ_LIST | K_TOC_RAW_DATA | K_TOC_INTERLEAVED_DATA,
            &meta2,
            &raw2,
            true,
        ));

        let table = parse_tdms(&file).unwrap();
        assert_eq!(
            table.columns,
            vec!["Measurements/Time", "Measurements/Speed"]
        );
        assert_eq!(table.row_count, 5);
        assert_eq!(
            table.column("Measurements/Time").unwrap(),
            &[0.0, 1.0, 2.0, 3.0, 4.0]
        );
        assert_eq!(
            table.column("Measurements/Speed").unwrap(),
            &[10.0, 20.0, 30.0, 40.0, 50.0]
        );

        let preview = preview_tdms(&file, 3).unwrap();
        assert_eq!(preview.columns, table.columns);
        assert_eq!(
            preview.rows,
            vec![
                vec!["0", "10"],
                vec!["1", "20"],
                vec!["2", "30"],
            ]
        );
    }

    #[test]
    fn test_incremental_obj_list_raw_only_segment_and_nan_padding() {
        let mut file = Vec::new();

        // Segment 0: Ch1 (2 samples)
        let mut meta0 = Vec::new();
        push_u32(&mut meta0, 1, false);
        push_str(&mut meta0, "/'G'/'Ch1'", false);
        push_u32(&mut meta0, 20, false);
        push_u32(&mut meta0, TDS_TYPE_I32, false);
        push_u32(&mut meta0, 1, false);
        push_u64(&mut meta0, 2, false);
        push_u32(&mut meta0, 0, false);
        let mut raw0 = Vec::new();
        raw0.extend_from_slice(&1i32.to_le_bytes());
        raw0.extend_from_slice(&2i32.to_le_bytes());
        file.extend_from_slice(&build_segment(
            K_TOC_META_DATA | K_TOC_NEW_OBJ_LIST | K_TOC_RAW_DATA,
            &meta0,
            &raw0,
            false,
        ));

        // Segment 1: Raw-data-only (no metadata) appending 2 more samples to Ch1
        let mut raw1 = Vec::new();
        raw1.extend_from_slice(&3i32.to_le_bytes());
        raw1.extend_from_slice(&4i32.to_le_bytes());
        file.extend_from_slice(&build_segment(K_TOC_RAW_DATA, &[], &raw1, false));

        // Segment 2: Incremental (no kTocNewObjList), adds Ch2 (6 samples) while Ch1 stays active (2 samples)
        let mut meta2 = Vec::new();
        push_u32(&mut meta2, 1, false);
        push_str(&mut meta2, "/'G'/'Ch2'", false);
        push_u32(&mut meta2, 20, false);
        push_u32(&mut meta2, TDS_TYPE_DOUBLE_FLOAT, false);
        push_u32(&mut meta2, 1, false);
        push_u64(&mut meta2, 6, false);
        push_u32(&mut meta2, 0, false);
        let mut raw2 = Vec::new();
        // Ch1 first (2 values)
        raw2.extend_from_slice(&5i32.to_le_bytes());
        raw2.extend_from_slice(&6i32.to_le_bytes());
        // Ch2 second (6 values)
        for v in [10.0f64, 20.0, 30.0, 40.0, 50.0, 60.0] {
            raw2.extend_from_slice(&v.to_le_bytes());
        }
        file.extend_from_slice(&build_segment(
            K_TOC_META_DATA | K_TOC_RAW_DATA,
            &meta2,
            &raw2,
            false,
        ));

        // Segment 3: kTocNewObjList drops Ch1 and writes 2 more to Ch2 (reuse raw_idx)
        let mut meta3 = Vec::new();
        push_u32(&mut meta3, 1, false);
        push_str(&mut meta3, "/'G'/'Ch2'", false);
        push_u32(&mut meta3, 20, false);
        push_u32(&mut meta3, TDS_TYPE_DOUBLE_FLOAT, false);
        push_u32(&mut meta3, 1, false);
        push_u64(&mut meta3, 2, false);
        push_u32(&mut meta3, 0, false);
        let mut raw3 = Vec::new();
        raw3.extend_from_slice(&70.0f64.to_le_bytes());
        raw3.extend_from_slice(&80.0f64.to_le_bytes());
        file.extend_from_slice(&build_segment(
            K_TOC_META_DATA | K_TOC_NEW_OBJ_LIST | K_TOC_RAW_DATA,
            &meta3,
            &raw3,
            false,
        ));

        let table = parse_tdms(&file).unwrap();
        assert_eq!(table.columns, vec!["G/Ch1", "G/Ch2"]);
        assert_eq!(table.row_count, 8);
        let ch1 = table.column("G/Ch1").unwrap();
        assert_eq!(&ch1[0..6], &[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]);
        assert!(ch1[6].is_nan());
        assert!(ch1[7].is_nan());
        assert_eq!(
            table.column("G/Ch2").unwrap(),
            &[10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]
        );

        let preview = preview_tdms(&file, 7).unwrap();
        assert_eq!(preview.rows.len(), 7);
        assert_eq!(preview.rows[5], vec!["6", "60"]);
        assert_eq!(preview.rows[6], vec!["", "70"]);
    }

    #[test]
    fn test_big_endian_and_string_channel() {
        // Big-endian segment with numeric + string channels
        let mut meta = Vec::new();
        push_u32(&mut meta, 2, true);

        push_str(&mut meta, "/'BE'/'Val'", true);
        push_u32(&mut meta, 20, true);
        push_u32(&mut meta, TDS_TYPE_DOUBLE_FLOAT, true);
        push_u32(&mut meta, 1, true);
        push_u64(&mut meta, 2, true);
        push_u32(&mut meta, 0, true);

        // String channel: ["hi", "ok!"] -> payload "hiok!" (5 bytes), offsets [2, 5] (8 bytes) -> total 13
        push_str(&mut meta, "/'BE'/'Tag'", true);
        push_u32(&mut meta, 28, true);
        push_u32(&mut meta, TDS_TYPE_STRING, true);
        push_u32(&mut meta, 1, true);
        push_u64(&mut meta, 2, true);
        push_u64(&mut meta, 13, true);
        push_u32(&mut meta, 0, true);

        let mut raw = Vec::new();
        raw.extend_from_slice(&12.5f64.to_be_bytes());
        raw.extend_from_slice(&(-3.75f64).to_be_bytes());
        raw.extend_from_slice(&2u32.to_be_bytes());
        raw.extend_from_slice(&5u32.to_be_bytes());
        raw.extend_from_slice(b"hiok!");

        let file = build_segment(
            K_TOC_META_DATA | K_TOC_NEW_OBJ_LIST | K_TOC_RAW_DATA | K_TOC_BIG_ENDIAN,
            &meta,
            &raw,
            false,
        );

        let table = parse_tdms(&file).unwrap();
        assert_eq!(table.columns, vec!["BE/Val", "BE/Tag"]);
        assert_eq!(table.column("BE/Val").unwrap(), &[12.5, -3.75]);
        assert!(table.column("BE/Tag").unwrap().iter().all(|v| v.is_nan()));

        let preview = preview_tdms(&file, 5).unwrap();
        assert_eq!(
            preview.rows,
            vec![vec!["12.5", "hi"], vec!["-3.75", "ok!"]]
        );
    }

    #[test]
    fn test_error_cases() {
        assert!(parse_tdms(&[]).is_err());
        assert!(parse_tdms(b"TDSh0000").is_err());
        assert!(preview_tdms(b"NOT_TDMS_BYTES_LONG_ENOUGH_12345", 5).is_err());

        // DAQmx flag rejected
        let daqmx = build_segment(K_TOC_DAQMX_RAW_DATA, &[], &[], false);
        let err = parse_tdms(&daqmx).unwrap_err();
        assert!(err.contains("DAQmx"), "unexpected error: {err}");
    }
}
