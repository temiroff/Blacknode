use thiserror::Error;

#[derive(Error, Debug)]
pub enum BlacknodeError {
    #[error("node not found: {0}")]
    NodeNotFound(String),

    #[error("port not found: {0}")]
    PortNotFound(String),

    #[error("type mismatch on port '{port}': expected {expected}, got {got}")]
    TypeMismatch {
        port: String,
        expected: String,
        got: String,
    },

    #[error("cycle detected in graph")]
    CycleDetected,

    #[error("cook error in node '{node}': {msg}")]
    CookError { node: String, msg: String },

    #[error("serialization error: {0}")]
    Serialization(#[from] serde_json::Error),
}
