use crate::{BlacknodeError, Node, NodeId};
use blacknode_types::Value;
use dashmap::DashMap;
use petgraph::algo::is_cyclic_directed;
use petgraph::stable_graph::{NodeIndex, StableDiGraph};
use petgraph::visit::EdgeRef;
use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct Edge {
    pub from_port: String,
    pub to_port: String,
}

pub struct Graph {
    dag: StableDiGraph<NodeId, Edge>,
    idx_map: HashMap<NodeId, NodeIndex>,
    nodes: HashMap<NodeId, Box<dyn Node>>,
    /// Cached output values keyed by (node_id, port_name).
    cache: DashMap<(NodeId, String), Value>,
    dirty: DashMap<NodeId, bool>,
}

impl Graph {
    pub fn new() -> Self {
        Self {
            dag: StableDiGraph::new(),
            idx_map: HashMap::new(),
            nodes: HashMap::new(),
            cache: DashMap::new(),
            dirty: DashMap::new(),
        }
    }

    pub fn add_node(&mut self, node: Box<dyn Node>) -> NodeId {
        let id = node.meta().id;
        let idx = self.dag.add_node(id);
        self.idx_map.insert(id, idx);
        self.dirty.insert(id, true);
        self.nodes.insert(id, node);
        id
    }

    pub fn connect(
        &mut self,
        from: NodeId,
        from_port: &str,
        to: NodeId,
        to_port: &str,
    ) -> Result<(), BlacknodeError> {
        let &fi = self
            .idx_map
            .get(&from)
            .ok_or_else(|| BlacknodeError::NodeNotFound(from.to_string()))?;
        let &ti = self
            .idx_map
            .get(&to)
            .ok_or_else(|| BlacknodeError::NodeNotFound(to.to_string()))?;

        self.dag.add_edge(
            fi,
            ti,
            Edge {
                from_port: from_port.to_string(),
                to_port: to_port.to_string(),
            },
        );

        if is_cyclic_directed(&self.dag) {
            // roll back the edge we just added
            if let Some(ei) = self.dag.find_edge(fi, ti) {
                self.dag.remove_edge(ei);
            }
            return Err(BlacknodeError::CycleDetected);
        }

        self.propagate_dirty(to);
        Ok(())
    }

    pub fn set_param(&mut self, node: NodeId, key: &str, val: Value) -> Result<(), BlacknodeError> {
        let n = self
            .nodes
            .get_mut(&node)
            .ok_or_else(|| BlacknodeError::NodeNotFound(node.to_string()))?;
        n.meta_mut().params.insert(key.to_string(), val);
        self.propagate_dirty(node);
        Ok(())
    }

    pub fn cook(&self, node_id: NodeId, port: &str) -> Result<Value, BlacknodeError> {
        self.cook_inner(node_id, port)
    }

    fn cook_inner(&self, node_id: NodeId, port: &str) -> Result<Value, BlacknodeError> {
        let cache_key = (node_id, port.to_string());

        let is_dirty = self.dirty.get(&node_id).map(|v| *v).unwrap_or(true);
        if !is_dirty {
            if let Some(v) = self.cache.get(&cache_key) {
                return Ok(v.clone());
            }
        }

        // pull inputs from upstream nodes
        let idx = self
            .idx_map
            .get(&node_id)
            .ok_or_else(|| BlacknodeError::NodeNotFound(node_id.to_string()))?;

        let incoming: Vec<(NodeIndex, Edge)> = self
            .dag
            .edges_directed(*idx, petgraph::Direction::Incoming)
            .map(|e| (e.source(), e.weight().clone()))
            .collect();

        let mut inputs: HashMap<String, Value> = HashMap::new();
        for (src_idx, edge) in incoming {
            if let Some(&src_id) = self.dag.node_weight(src_idx) {
                let val = self.cook_inner(src_id, &edge.from_port)?;
                inputs.insert(edge.to_port.clone(), val);
            }
        }

        // fill remaining from params
        let node = self
            .nodes
            .get(&node_id)
            .ok_or_else(|| BlacknodeError::NodeNotFound(node_id.to_string()))?;
        for (k, v) in &node.meta().params {
            inputs.entry(k.clone()).or_insert_with(|| v.clone());
        }

        let outputs = node.cook(inputs).map_err(|e| BlacknodeError::CookError {
            node: format!("{} ({})", node.meta().label, node_id),
            msg: e.to_string(),
        })?;

        for (k, v) in &outputs {
            self.cache.insert((node_id, k.clone()), v.clone());
        }
        self.dirty.insert(node_id, false);

        outputs
            .get(port)
            .cloned()
            .ok_or_else(|| BlacknodeError::PortNotFound(port.to_string()))
    }

    fn propagate_dirty(&self, id: NodeId) {
        if self.dirty.get(&id).map(|v| *v).unwrap_or(false) {
            return; // already dirty — subtree already marked
        }
        self.dirty.insert(id, true);
        if let Some(&idx) = self.idx_map.get(&id) {
            let downstream: Vec<_> = self
                .dag
                .neighbors_directed(idx, petgraph::Direction::Outgoing)
                .collect();
            for ni in downstream {
                if let Some(&nid) = self.dag.node_weight(ni) {
                    self.propagate_dirty(nid);
                }
            }
        }
    }

    pub fn node_ids(&self) -> Vec<NodeId> {
        self.nodes.keys().cloned().collect()
    }

    pub fn node_meta(&self, id: NodeId) -> Option<&crate::NodeMeta> {
        self.nodes.get(&id).map(|n| n.meta())
    }
}

impl Default for Graph {
    fn default() -> Self {
        Self::new()
    }
}
