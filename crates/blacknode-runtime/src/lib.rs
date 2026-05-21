use blacknode_core::{BlacknodeError, Graph, NodeId};
use blacknode_types::Value;
use std::collections::HashMap;

/// Async executor that cooks multiple terminal nodes in parallel
/// using tokio tasks. Each branch is independent once inputs are resolved.
pub struct AsyncExecutor;

impl AsyncExecutor {
    /// Cook a set of (node_id, port) targets concurrently.
    pub async fn cook_many(
        graph: &Graph,
        targets: Vec<(NodeId, String)>,
    ) -> HashMap<(NodeId, String), Result<Value, BlacknodeError>> {
        let mut results = HashMap::new();
        // Graph::cook is internally synchronous (recursive pull).
        // We spawn each target as a blocking task.
        let handles: Vec<_> = targets
            .into_iter()
            .map(|(id, port)| {
                // SAFETY: Graph is Sync — shared reference across tasks.
                let g = graph as *const Graph as usize;
                let port_clone = port.clone();
                let handle = tokio::task::spawn_blocking(move || {
                    let g = unsafe { &*(g as *const Graph) };
                    ((id, port_clone.clone()), g.cook(id, &port_clone))
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
