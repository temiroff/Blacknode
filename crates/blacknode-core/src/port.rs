use serde::{Deserialize, Serialize};
use blacknode_types::Value;

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct PortId(pub String);

impl PortId {
    pub fn new(name: impl Into<String>) -> Self {
        Self(name.into())
    }
}

impl std::fmt::Display for PortId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum PortDir {
    Input,
    Output,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Port {
    pub id: PortId,
    pub name: String,
    pub dir: PortDir,
    /// Type hint for editor validation: "Text", "Number", "Bool", "Any", etc.
    pub type_hint: String,
    pub default: Option<Value>,
}

impl Port {
    pub fn input(name: impl Into<String>, type_hint: impl Into<String>) -> Self {
        let name = name.into();
        Self {
            id: PortId::new(&name),
            name,
            dir: PortDir::Input,
            type_hint: type_hint.into(),
            default: None,
        }
    }

    pub fn output(name: impl Into<String>, type_hint: impl Into<String>) -> Self {
        let name = name.into();
        Self {
            id: PortId::new(&name),
            name,
            dir: PortDir::Output,
            type_hint: type_hint.into(),
            default: None,
        }
    }

    pub fn with_default(mut self, val: Value) -> Self {
        self.default = Some(val);
        self
    }
}
