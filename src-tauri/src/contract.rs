use serde_json::{Map, Value};
use std::collections::{HashMap, HashSet};
use std::sync::OnceLock;

const CONTRACT_JSON: &str =
    include_str!("../../src/agent_quota/resources/renderer_contract_v1.json");

#[derive(Debug, thiserror::Error)]
pub enum ContractError {
    #[error("renderer contract is unavailable")]
    Unavailable,
    #[error("unknown renderer command")]
    UnknownCommand,
    #[error("invalid DTO at {0}")]
    InvalidDto(String),
}

struct Contract {
    commands: HashMap<String, (String, String)>,
    schemas: HashMap<String, Value>,
}

fn contract() -> Result<&'static Contract, ContractError> {
    static CONTRACT: OnceLock<Result<Contract, ContractError>> = OnceLock::new();
    CONTRACT
        .get_or_init(|| {
            let document: Value =
                serde_json::from_str(CONTRACT_JSON).map_err(|_| ContractError::Unavailable)?;
            let command_ids = document["command_ids"]
                .as_array()
                .ok_or(ContractError::Unavailable)?;
            let commands_array = document["commands"]
                .as_array()
                .ok_or(ContractError::Unavailable)?;
            let schema_array = document["dto_schemas"]
                .as_array()
                .ok_or(ContractError::Unavailable)?;
            if command_ids.len() != 10 || commands_array.len() != 10 || schema_array.len() != 29 {
                return Err(ContractError::Unavailable);
            }
            let mut commands = HashMap::new();
            for (index, row) in commands_array.iter().enumerate() {
                let id = row["command_id"]
                    .as_str()
                    .ok_or(ContractError::Unavailable)?;
                if command_ids[index].as_str() != Some(id) {
                    return Err(ContractError::Unavailable);
                }
                commands.insert(
                    id.to_owned(),
                    (
                        row["request_schema_ref"]
                            .as_str()
                            .ok_or(ContractError::Unavailable)?
                            .to_owned(),
                        row["response_schema_ref"]
                            .as_str()
                            .ok_or(ContractError::Unavailable)?
                            .to_owned(),
                    ),
                );
            }
            let schemas = schema_array
                .iter()
                .map(|row| {
                    Ok((
                        row["schema_ref"]
                            .as_str()
                            .ok_or(ContractError::Unavailable)?
                            .to_owned(),
                        row.clone(),
                    ))
                })
                .collect::<Result<HashMap<_, _>, ContractError>>()?;
            if commands.len() != 10 || schemas.len() != 29 {
                return Err(ContractError::Unavailable);
            }
            Ok(Contract { commands, schemas })
        })
        .as_ref()
        .map_err(|_| ContractError::Unavailable)
}

fn string_bytes(value: &str) -> usize {
    value.len()
}

fn validate_field(
    contract: &Contract,
    field: &Value,
    value: &Value,
    path: &str,
) -> Result<(), ContractError> {
    match field["type"].as_str() {
        Some("string") => {
            let text = value
                .as_str()
                .ok_or_else(|| ContractError::InvalidDto(path.to_owned()))?;
            let maximum = field["max_utf8_bytes"]
                .as_u64()
                .ok_or(ContractError::Unavailable)? as usize;
            if string_bytes(text) > maximum {
                return Err(ContractError::InvalidDto(path.to_owned()));
            }
            let allowed = field["allowed_values"]
                .as_array()
                .ok_or(ContractError::Unavailable)?;
            if !allowed.is_empty() && !allowed.iter().any(|item| item.as_str() == Some(text)) {
                return Err(ContractError::InvalidDto(path.to_owned()));
            }
        }
        Some("integer") => {
            let number = value
                .as_i64()
                .ok_or_else(|| ContractError::InvalidDto(path.to_owned()))?;
            let minimum = field["minimum"]
                .as_i64()
                .ok_or(ContractError::Unavailable)?;
            let maximum = field["maximum"]
                .as_i64()
                .ok_or(ContractError::Unavailable)?;
            if number < minimum || number > maximum {
                return Err(ContractError::InvalidDto(path.to_owned()));
            }
        }
        Some("boolean") => {
            if !value.is_boolean() {
                return Err(ContractError::InvalidDto(path.to_owned()));
            }
        }
        Some("object") => {
            let reference = field["ref"].as_str().ok_or(ContractError::Unavailable)?;
            validate_schema(contract, reference, value, path)?;
        }
        Some("array") => {
            let items = value
                .as_array()
                .ok_or_else(|| ContractError::InvalidDto(path.to_owned()))?;
            let maximum = field["max_items"]
                .as_u64()
                .ok_or(ContractError::Unavailable)? as usize;
            let reference = field["ref"].as_str().ok_or(ContractError::Unavailable)?;
            if items.len() > maximum {
                return Err(ContractError::InvalidDto(path.to_owned()));
            }
            for (index, item) in items.iter().enumerate() {
                validate_schema(contract, reference, item, &format!("{path}[{index}]"))?;
            }
        }
        _ => return Err(ContractError::Unavailable),
    }
    Ok(())
}

fn validate_schema(
    contract: &Contract,
    schema_ref: &str,
    payload: &Value,
    path: &str,
) -> Result<(), ContractError> {
    let schema = contract
        .schemas
        .get(schema_ref)
        .ok_or(ContractError::Unavailable)?;
    let object = payload
        .as_object()
        .ok_or_else(|| ContractError::InvalidDto(path.to_owned()))?;
    let fields = schema["fields"]
        .as_array()
        .ok_or(ContractError::Unavailable)?;
    let by_name = fields
        .iter()
        .map(|field| {
            Ok((
                field["name"].as_str().ok_or(ContractError::Unavailable)?,
                field,
            ))
        })
        .collect::<Result<HashMap<_, _>, ContractError>>()?;
    let expected: HashSet<&str> = by_name.keys().copied().collect();
    if object.keys().any(|key| !expected.contains(key.as_str())) {
        return Err(ContractError::InvalidDto(path.to_owned()));
    }
    for field in fields {
        let name = field["name"].as_str().ok_or(ContractError::Unavailable)?;
        if field["required"].as_bool() == Some(true) && !object.contains_key(name) {
            return Err(ContractError::InvalidDto(path.to_owned()));
        }
    }
    for (name, value) in object {
        validate_field(
            contract,
            by_name
                .get(name.as_str())
                .ok_or_else(|| ContractError::InvalidDto(path.to_owned()))?,
            value,
            &format!("{path}.{name}"),
        )?;
    }
    Ok(())
}

pub fn validate_request(command_id: &str, payload: &Value) -> Result<(), ContractError> {
    let contract = contract()?;
    let (request, _) = contract
        .commands
        .get(command_id)
        .ok_or(ContractError::UnknownCommand)?;
    validate_schema(contract, request, payload, "request")
}

pub fn validate_response(command_id: &str, payload: Value) -> Result<Value, ContractError> {
    let contract = contract()?;
    let (_, response) = contract
        .commands
        .get(command_id)
        .ok_or(ContractError::UnknownCommand)?;
    validate_schema(contract, response, &payload, "response")?;
    Ok(payload)
}

pub fn safe_error(code: &str, retryable: bool) -> Value {
    Value::Object(Map::from_iter([
        ("code".to_owned(), Value::String(code.to_owned())),
        ("retryable".to_owned(), Value::Bool(retryable)),
    ]))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn closure_and_extra_fields_fail_closed() {
        assert!(contract().is_ok());
        assert!(validate_request("bootstrap_state", &json!({})).is_ok());
        assert!(validate_request("bootstrap_state", &json!({"extra": true})).is_err());
        assert!(validate_request("unknown", &json!({})).is_err());
    }

    #[test]
    fn nested_and_bound_fail_closed() {
        assert!(validate_request("accounts_read", &json!({"scope_ref": "x".repeat(129)})).is_err());
        assert!(
            validate_request(
                "config_validate_apply",
                &json!({
                    "config_change_set": {
                        "changes": [],
                        "expected_generation": -1
                    }
                })
            )
            .is_err()
        );
    }
}
