use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;
use blacknode_types::Value;
use crate::port::Port;

pub type NodeId = Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeMeta {
    pub id: NodeId,
    pub type_name: String,
    pub label: String,
    pub params: HashMap<String, Value>,
    pub ports: Vec<Port>,
    /// Visual editor position (x, y).
    pub pos: (f32, f32),
}

impl NodeMeta {
    pub fn new(type_name: impl Into<String>) -> Self {
        let type_name = type_name.into();
        Self {
            id: Uuid::new_v4(),
            label: type_name.clone(),
            type_name,
            params: HashMap::new(),
            ports: Vec::new(),
            pos: (0.0, 0.0),
        }
    }

    pub fn with_port(mut self, port: Port) -> Self {
        self.ports.push(port);
        self
    }

    pub fn with_param(mut self, key: impl Into<String>, val: impl Into<Value>) -> Self {
        self.params.insert(key.into(), val.into());
        self
    }

    pub fn at(mut self, x: f32, y: f32) -> Self {
        self.pos = (x, y);
        self
    }
}

/// Every node implements this trait. Python nodes go through a shim.
pub trait Node: Send + Sync {
    fn meta(&self) -> &NodeMeta;
    fn meta_mut(&mut self) -> &mut NodeMeta;

    /// Cook: receive resolved inputs, return output map.
    fn cook(&self, inputs: HashMap<String, Value>) -> anyhow::Result<HashMap<String, Value>>;
}
