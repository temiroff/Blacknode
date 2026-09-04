use blacknode_core::{BlacknodeError, Graph, NodeId};
use blacknode_types::Value;
use std::collections::HashMap;
use std::sync::Arc;

/// Async executor that cooks multiple terminal nodes in parallel
/// using tokio tasks. Each branch is independent once inputs are resolved.
pub struct AsyncExecutor;

impl AsyncExecutor {
    /// Cook a set of (node_id, port) targets concurrently.
    pub async fn cook_many(
        graph: Arc<Graph>,
        targets: Vec<(NodeId, String)>,
    ) -> HashMap<(NodeId, String), Result<Value, BlacknodeError>> {
        let mut results = HashMap::new();
        // Graph::cook is internally synchronous (recursive pull).
        // We spawn each target as a blocking task.
        let handles: Vec<_> = targets
            .into_iter()
            .map(|(id, port)| {
                let graph = Arc::clone(&graph);
                let port_clone = port.clone();
                let handle = tokio::task::spawn_blocking(move || {
                    ((id, port_clone.clone()), graph.cook(id, &port_clone))
                });
                handle
            })
            .collect();

        for h in handles {
            if let Ok((key, val)) = h.await {
                results.insert(key, val);
            }
        }
        results
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use blacknode_core::{Node, NodeMeta, Port};

    struct ConstantNode {
        meta: NodeMeta,
        value: i64,
    }

    impl ConstantNode {
        fn new(value: i64) -> Self {
            Self {
                meta: NodeMeta::new("Constant").with_port(Port::output("value", "Int")),
                value,
            }
        }
    }

    impl Node for ConstantNode {
        fn meta(&self) -> &NodeMeta {
            &self.meta
        }

        fn meta_mut(&mut self) -> &mut NodeMeta {
            &mut self.meta
        }

        fn cook(&self, _inputs: HashMap<String, Value>) -> anyhow::Result<HashMap<String, Value>> {
            Ok(HashMap::from([("value".to_string(), Value::Int(self.value))]))
        }
    }

    #[tokio::test]
    async fn cooks_multiple_targets_without_borrowing_graph_memory_into_tasks() {
        let mut graph = Graph::new();
        let first = graph.add_node(Box::new(ConstantNode::new(2)));
        let second = graph.add_node(Box::new(ConstantNode::new(5)));

        let results = AsyncExecutor::cook_many(
            Arc::new(graph),
            vec![(first, "value".to_string()), (second, "value".to_string())],
        )
        .await;

        assert_eq!(results[&(first, "value".to_string())].as_ref().unwrap(), &Value::Int(2));
        assert_eq!(results[&(second, "value".to_string())].as_ref().unwrap(), &Value::Int(5));
    }
}
