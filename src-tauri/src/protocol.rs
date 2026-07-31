use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::io::{self, Read, Write};

pub const MAX_FRAME_BYTES: usize = 1024 * 1024;
pub const MAX_REMAINING_BUDGET_NS: u64 = 9_000_000_000;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RequestEnvelope {
    pub request_id: u64,
    pub remaining_budget_ns: u64,
    pub command_id: String,
    pub payload: Value,
    pub session_proof: String,
}

#[derive(Debug, thiserror::Error)]
pub enum ProtocolError {
    #[error("I/O failure")]
    Io(#[from] io::Error),
    #[error("frame size is invalid")]
    FrameSize,
    #[error("JSON frame is invalid")]
    Json,
    #[error("request order is invalid")]
    Order,
    #[error("remaining budget is invalid")]
    Budget,
}

pub fn write_frame(writer: &mut impl Write, value: &impl Serialize) -> Result<(), ProtocolError> {
    let body = serde_json::to_vec(value).map_err(|_| ProtocolError::Json)?;
    if body.is_empty() || body.len() > MAX_FRAME_BYTES || body.len() > u32::MAX as usize {
        return Err(ProtocolError::FrameSize);
    }
    writer.write_all(&(body.len() as u32).to_be_bytes())?;
    writer.write_all(&body)?;
    writer.flush()?;
    Ok(())
}

pub fn read_frame(reader: &mut impl Read) -> Result<Value, ProtocolError> {
    let mut header = [0_u8; 4];
    reader.read_exact(&mut header)?;
    let length = u32::from_be_bytes(header) as usize;
    if length == 0 || length > MAX_FRAME_BYTES {
        return Err(ProtocolError::FrameSize);
    }
    let mut body = vec![0_u8; length];
    reader.read_exact(&mut body)?;
    let value: Value = serde_json::from_slice(&body).map_err(|_| ProtocolError::Json)?;
    if !value.is_object() {
        return Err(ProtocolError::Json);
    }
    Ok(value)
}

#[derive(Debug, Default)]
pub struct Sequence {
    next: u64,
}

impl Sequence {
    pub fn next_request(
        &mut self,
        remaining_budget_ns: u64,
        command_id: String,
        payload: Value,
        session_proof: String,
    ) -> Result<RequestEnvelope, ProtocolError> {
        if !(1..=MAX_REMAINING_BUDGET_NS).contains(&remaining_budget_ns) {
            return Err(ProtocolError::Budget);
        }
        let request_id = self.next.checked_add(1).ok_or(ProtocolError::Order)?;
        self.next = request_id;
        Ok(RequestEnvelope {
            request_id,
            remaining_budget_ns,
            command_id,
            payload,
            session_proof,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn frame_round_trip_is_big_endian_and_exact() {
        let mut bytes = Vec::new();
        write_frame(&mut bytes, &json!({"ok": true})).unwrap();
        assert_eq!(
            u32::from_be_bytes(bytes[..4].try_into().unwrap()) as usize,
            bytes.len() - 4
        );
        assert_eq!(
            read_frame(&mut bytes.as_slice()).unwrap(),
            json!({"ok": true})
        );
    }

    #[test]
    fn rejects_zero_oversize_truncation_and_non_object() {
        assert!(matches!(
            read_frame(&mut [0_u8; 4].as_slice()),
            Err(ProtocolError::FrameSize)
        ));
        let length = ((MAX_FRAME_BYTES + 1) as u32).to_be_bytes();
        assert!(matches!(
            read_frame(&mut length.as_slice()),
            Err(ProtocolError::FrameSize)
        ));
        let truncated = [0, 0, 0, 3, b'{'];
        let mut truncated_reader = truncated.as_slice();
        assert!(matches!(
            read_frame(&mut truncated_reader),
            Err(ProtocolError::Io(_))
        ));
        let mut scalar = Vec::new();
        write_frame(&mut scalar, &true).unwrap();
        assert!(matches!(
            read_frame(&mut scalar.as_slice()),
            Err(ProtocolError::Json)
        ));
    }

    #[test]
    fn sequence_is_monotonic_and_budget_bounded() {
        let mut sequence = Sequence::default();
        assert_eq!(
            sequence
                .next_request(1, "a".to_owned(), json!({}), "proof".to_owned())
                .unwrap()
                .request_id,
            1
        );
        assert_eq!(
            sequence
                .next_request(
                    MAX_REMAINING_BUDGET_NS,
                    "b".to_owned(),
                    json!({}),
                    "proof".to_owned(),
                )
                .unwrap()
                .request_id,
            2
        );
        assert!(
            sequence
                .next_request(0, "c".to_owned(), json!({}), "proof".to_owned())
                .is_err()
        );
        assert!(
            sequence
                .next_request(
                    MAX_REMAINING_BUDGET_NS + 1,
                    "c".to_owned(),
                    json!({}),
                    "proof".to_owned(),
                )
                .is_err()
        );
    }
}
