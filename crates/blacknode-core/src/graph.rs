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

        let edge_index = self.dag.add_edge(
            fi,
            ti,
            Edge {
                from_port: from_port.to_string(),
                to_port: to_port.to_string(),
            },
        );

        if is_cyclic_directed(&self.dag) {
            self.dag.remove_edge(edge_index);
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{NodeMeta, Port};
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };

    struct AddNode {
        meta: NodeMeta,
        cooks: Arc<AtomicUsize>,
    }

    impl AddNode {
        fn new(value: i64, cooks: Arc<AtomicUsize>) -> Self {
            Self {
                meta: NodeMeta::new("Add")
                    .with_port(Port::input("value", "Int"))
                    .with_port(Port::output("result", "Int"))
                    .with_param("value", value),
                cooks,
            }
        }
    }

    impl Node for AddNode {
        fn meta(&self) -> &NodeMeta {
            &self.meta
        }

        fn meta_mut(&mut self) -> &mut NodeMeta {
            &mut self.meta
        }

        fn cook(&self, inputs: HashMap<String, Value>) -> anyhow::Result<HashMap<String, Value>> {
            self.cooks.fetch_add(1, Ordering::SeqCst);
            let value = inputs.get("value").and_then(Value::as_f64).unwrap_or_default() as i64;
            Ok(HashMap::from([("result".to_string(), Value::Int(value + 1))]))
        }
    }

    #[test]
    fn caches_results_and_invalidates_downstream_after_parameter_update() {
        let first_cooks = Arc::new(AtomicUsize::new(0));
        let second_cooks = Arc::new(AtomicUsize::new(0));
        let mut graph = Graph::new();
        let first = graph.add_node(Box::new(AddNode::new(1, first_cooks.clone())));
        let second = graph.add_node(Box::new(AddNode::new(0, second_cooks.clone())));
        graph.connect(first, "result", second, "value").unwrap();

        assert_eq!(graph.cook(second, "result").unwrap(), Value::Int(3));
        assert_eq!(graph.cook(second, "result").unwrap(), Value::Int(3));
        assert_eq!(first_cooks.load(Ordering::SeqCst), 1);
        assert_eq!(second_cooks.load(Ordering::SeqCst), 1);

        graph.set_param(first, "value", Value::Int(5)).unwrap();
        assert_eq!(graph.cook(second, "result").unwrap(), Value::Int(7));
        assert_eq!(first_cooks.load(Ordering::SeqCst), 2);
        assert_eq!(second_cooks.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn rejects_cycles_without_removing_an_existing_parallel_edge() {
        let mut graph = Graph::new();
        let cooks = Arc::new(AtomicUsize::new(0));
        let first = graph.add_node(Box::new(AddNode::new(1, cooks.clone())));
        let second = graph.add_node(Box::new(AddNode::new(2, cooks)));
        graph.connect(first, "result", second, "value").unwrap();

        assert!(matches!(
            graph.connect(second, "result", first, "value"),
            Err(BlacknodeError::CycleDetected)
        ));
        assert_eq!(graph.cook(second, "result").unwrap(), Value::Int(3));
    }
}
