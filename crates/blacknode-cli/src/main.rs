use serde::Deserialize;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::env;
use std::fmt;
use std::fs;
use std::path::PathBuf;
use thiserror::Error;

const USAGE: &str = "usage: blacknode-rs <validate|inspect|run-pure> <workflow.json>";

#[derive(Debug, Error)]
enum CliError {
    #[error("{0}")]
    Usage(&'static str),

    #[error("failed to read {}: {source}", path.display())]
    Read {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },

    #[error("failed to parse {}: {source}", path.display())]
    Parse {
        path: PathBuf,
        #[source]
        source: serde_json::Error,
    },

    #[error("workflow validation failed:\n{0}")]
    Validation(ValidationReport),

    #[error("failed to encode JSON output: {0}")]
    Json(#[from] serde_json::Error),

    #[error("workflow cannot run in the Rust pure runner: {0}")]
    Unsupported(String),

    #[error("{0}")]
    Eval(String),
}

#[derive(Debug)]
struct ValidationReport(Vec<String>);

impl fmt::Display for ValidationReport {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        for error in &self.0 {
            writeln!(f, "- {error}")?;
        }
        Ok(())
    }
}

#[derive(Debug, Deserialize)]
struct Workflow {
    kind: String,
    schema_version: u32,
    name: Option<String>,
    entrypoint: Option<Endpoint>,
    #[serde(default)]
    node_meta: BTreeMap<String, NodeMeta>,
    #[serde(default)]
    edges: Vec<Edge>,
}

#[derive(Debug, Clone, Deserialize)]
struct Endpoint {
    node_id: String,
    port: String,
}

#[derive(Debug, Deserialize)]
struct NodeMeta {
    id: Option<String>,
    #[serde(rename = "type")]
    type_name: String,
    #[serde(default)]
    params: Map<String, Value>,
    #[serde(default)]
    inputs: Vec<String>,
    #[serde(default)]
    outputs: Vec<String>,
    #[serde(default)]
    input_defaults: Map<String, Value>,
}

#[derive(Debug, Clone, Deserialize)]
struct Edge {
    from: String,
    from_port: String,
    to: String,
    to_port: String,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), CliError> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 {
        return Err(CliError::Usage(USAGE));
    }

    let command = &args[1];
    let path = PathBuf::from(&args[2]);
    let workflow = load_workflow(path)?;
    validate_workflow(&workflow)?;

    match command.as_str() {
        "validate" => {
            println!(
                "OK: {} ({} nodes, {} edges)",
                workflow_name(&workflow),
                workflow.node_meta.len(),
                workflow.edges.len()
            );
        }
        "inspect" => {
            let info = inspect_workflow(&workflow)?;
            println!("{}", serde_json::to_string_pretty(&info)?);
        }
        "run-pure" => {
            let unsupported = unsupported_node_types(&workflow);
            if !unsupported.is_empty() {
                return Err(CliError::Unsupported(format!(
                    "unsupported node types: {}",
                    unsupported.join(", ")
                )));
            }
            let result = PureRunner::new(&workflow).run()?;
            print_result(&result)?;
        }
        _ => return Err(CliError::Usage(USAGE)),
    }

    Ok(())
}

fn load_workflow(path: PathBuf) -> Result<Workflow, CliError> {
    let raw = fs::read_to_string(&path).map_err(|source| CliError::Read {
        path: path.clone(),
        source,
    })?;
    serde_json::from_str(&raw).map_err(|source| CliError::Parse { path, source })
}

fn validate_workflow(workflow: &Workflow) -> Result<(), CliError> {
    let mut errors = Vec::new();

    if workflow.kind != "blacknode.workflow" {
        errors.push(format!(
            "kind must be \"blacknode.workflow\", got {:?}",
            workflow.kind
        ));
    }
    if workflow.schema_version != 1 {
        errors.push(format!(
            "schema_version must be 1, got {}",
            workflow.schema_version
        ));
    }
    if workflow.node_meta.is_empty() {
        errors.push("node_meta must contain at least one node".to_string());
    }

    for (key, node) in &workflow.node_meta {
        if let Some(id) = &node.id {
            if id != key {
                errors.push(format!("node key {key:?} does not match id {id:?}"));
            }
        }
        if node.type_name.trim().is_empty() {
            errors.push(format!("node {key:?} has an empty type"));
        }
    }

    let mut target_ports: BTreeMap<(String, String), Vec<String>> = BTreeMap::new();
    for edge in &workflow.edges {
        match workflow.node_meta.get(&edge.from) {
            Some(node) => {
                if !node.outputs.iter().any(|port| port == &edge.from_port) {
                    errors.push(format!(
                        "edge {}.{} -> {}.{} uses missing source output port",
                        edge.from, edge.from_port, edge.to, edge.to_port
                    ));
                }
            }
            None => errors.push(format!(
                "edge {}.{} -> {}.{} references missing source node",
                edge.from, edge.from_port, edge.to, edge.to_port
            )),
        }

        match workflow.node_meta.get(&edge.to) {
            Some(node) => {
                if !node.inputs.iter().any(|port| port == &edge.to_port) {
                    errors.push(format!(
                        "edge {}.{} -> {}.{} uses missing target input port",
                        edge.from, edge.from_port, edge.to, edge.to_port
                    ));
                }
            }
            None => errors.push(format!(
                "edge {}.{} -> {}.{} references missing target node",
                edge.from, edge.from_port, edge.to, edge.to_port
            )),
        }

        target_ports
            .entry((edge.to.clone(), edge.to_port.clone()))
            .or_default()
            .push(format!("{}.{}", edge.from, edge.from_port));
    }

    for ((node_id, port), sources) in target_ports {
        if sources.len() > 1 {
            errors.push(format!(
                "input {node_id}.{port} has multiple incoming edges: {}",
                sources.join(", ")
            ));
        }
    }

    match resolve_entrypoint(workflow) {
        Ok(entrypoint) => match workflow.node_meta.get(&entrypoint.node_id) {
            Some(node) => {
                let is_known_port = node.outputs.iter().any(|port| port == &entrypoint.port)
                    || node.inputs.iter().any(|port| port == &entrypoint.port);
                if !is_known_port {
                    errors.push(format!(
                        "entrypoint {}.{} is not a declared input or output port",
                        entrypoint.node_id, entrypoint.port
                    ));
                }
            }
            None => errors.push(format!(
                "entrypoint references missing node {:?}",
                entrypoint.node_id
            )),
        },
        Err(error) => errors.push(error),
    }

    if has_cycle(workflow) {
        errors.push("workflow graph contains a cycle".to_string());
    }

    if errors.is_empty() {
        Ok(())
    } else {
        Err(CliError::Validation(ValidationReport(errors)))
    }
}

fn resolve_entrypoint(workflow: &Workflow) -> Result<Endpoint, String> {
    if let Some(entrypoint) = &workflow.entrypoint {
        return Ok(entrypoint.clone());
    }

    let output_nodes: Vec<_> = workflow
        .node_meta
        .iter()
        .filter(|(_, node)| node.type_name == "Output")
        .map(|(id, _)| id.clone())
        .collect();

    match output_nodes.as_slice() {
        [node_id] => Ok(Endpoint {
            node_id: node_id.clone(),
            port: "value".to_string(),
        }),
        [] => Err("workflow has no entrypoint and no Output node to infer".to_string()),
        _ => Err("workflow has no entrypoint and multiple Output nodes".to_string()),
    }
}

fn has_cycle(workflow: &Workflow) -> bool {
    let mut adjacency: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for id in workflow.node_meta.keys() {
        adjacency.entry(id.clone()).or_default();
    }
    for edge in &workflow.edges {
        if workflow.node_meta.contains_key(&edge.from) && workflow.node_meta.contains_key(&edge.to)
        {
            adjacency
                .entry(edge.from.clone())
                .or_default()
                .push(edge.to.clone());
        }
    }

    let mut temporary = BTreeSet::new();
    let mut permanent = BTreeSet::new();
    for id in workflow.node_meta.keys() {
        if visit_cycle(id, &adjacency, &mut temporary, &mut permanent) {
            return true;
        }
    }
    false
}

fn visit_cycle(
    id: &str,
    adjacency: &BTreeMap<String, Vec<String>>,
    temporary: &mut BTreeSet<String>,
    permanent: &mut BTreeSet<String>,
) -> bool {
    if permanent.contains(id) {
        return false;
    }
    if !temporary.insert(id.to_string()) {
        return true;
    }

    if let Some(targets) = adjacency.get(id) {
        for target in targets {
            if visit_cycle(target, adjacency, temporary, permanent) {
                return true;
            }
        }
    }

    temporary.remove(id);
    permanent.insert(id.to_string());
    false
}

fn inspect_workflow(workflow: &Workflow) -> Result<Value, CliError> {
    let entrypoint = resolve_entrypoint(workflow).map_err(|error| CliError::Eval(error))?;
    let mut node_types: BTreeMap<String, usize> = BTreeMap::new();
    for node in workflow.node_meta.values() {
        *node_types.entry(node.type_name.clone()).or_insert(0) += 1;
    }
    let unsupported = unsupported_node_types(workflow);

    Ok(json!({
        "name": workflow_name(workflow),
        "schema_version": workflow.schema_version,
        "node_count": workflow.node_meta.len(),
        "edge_count": workflow.edges.len(),
        "entrypoint": {
            "node_id": entrypoint.node_id,
            "port": entrypoint.port,
        },
        "node_types": node_types,
        "pure_runnable": unsupported.is_empty(),
        "unsupported_node_types": unsupported,
    }))
}

fn unsupported_node_types(workflow: &Workflow) -> Vec<String> {
    workflow
        .node_meta
        .values()
        .filter(|node| !is_pure_supported(&node.type_name))
        .map(|node| node.type_name.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn is_pure_supported(type_name: &str) -> bool {
    matches!(
        type_name,
        "Text"
            | "Int"
            | "Float"
            | "Bool"
            | "Dict"
            | "Literal"
            | "Model"
            | "Concat"
            | "Add"
            | "Subtract"
            | "Multiply"
            | "Divide"
            | "Output"
    )
}

struct PureRunner<'a> {
    workflow: &'a Workflow,
    edge_by_target: HashMap<(String, String), (String, String)>,
    memo: HashMap<(String, String), Value>,
    visiting: HashSet<(String, String)>,
}

impl<'a> PureRunner<'a> {
    fn new(workflow: &'a Workflow) -> Self {
        let edge_by_target = workflow
            .edges
            .iter()
            .map(|edge| {
                (
                    (edge.to.clone(), edge.to_port.clone()),
                    (edge.from.clone(), edge.from_port.clone()),
                )
            })
            .collect();

        Self {
            workflow,
            edge_by_target,
            memo: HashMap::new(),
            visiting: HashSet::new(),
        }
    }

    fn run(&mut self) -> Result<Value, CliError> {
        let entrypoint = resolve_entrypoint(self.workflow).map_err(CliError::Eval)?;
        self.eval(&entrypoint.node_id, &entrypoint.port)
    }

    fn eval(&mut self, node_id: &str, port: &str) -> Result<Value, CliError> {
        let key = (node_id.to_string(), port.to_string());
        if let Some(value) = self.memo.get(&key) {
            return Ok(value.clone());
        }
        if !self.visiting.insert(key.clone()) {
            return Err(CliError::Eval(format!(
                "cycle encountered while evaluating {node_id}.{port}"
            )));
        }

        let result = self.eval_uncached(node_id, port);
        self.visiting.remove(&key);
        let result = result?;
        self.memo.insert(key, result.clone());
        Ok(result)
    }

    fn eval_uncached(&mut self, node_id: &str, port: &str) -> Result<Value, CliError> {
        let node = self
            .workflow
            .node_meta
            .get(node_id)
            .ok_or_else(|| CliError::Eval(format!("missing node {node_id:?}")))?;

        match node.type_name.as_str() {
            "Text" | "Int" | "Float" | "Bool" | "Dict" | "Literal" | "Model" => {
                if port != "value" {
                    Err(CliError::Eval(format!(
                        "{} node {node_id:?} does not produce port {port:?}",
                        node.type_name
                    )))
                } else {
                    node.params.get("value").cloned().ok_or_else(|| {
                        CliError::Eval(format!("{} node {node_id:?} has no value", node.type_name))
                    })
                }
            }
            "Concat" => {
                ensure_port(node, node_id, port)?;
                let a = self.input_value(node_id, "a")?;
                let b = self.input_value(node_id, "b")?;
                Ok(Value::String(format!(
                    "{}{}",
                    value_to_text(&a),
                    value_to_text(&b)
                )))
            }
            "Add" | "Subtract" | "Multiply" | "Divide" => {
                ensure_port(node, node_id, port)?;
                let a = self.number_input(node_id, "a")?;
                let b = self.number_input(node_id, "b")?;
                let value = match node.type_name.as_str() {
                    "Add" => a + b,
                    "Subtract" => a - b,
                    "Multiply" => a * b,
                    "Divide" => {
                        if b == 0.0 {
                            return Err(CliError::Eval(format!(
                                "Divide node {node_id:?} cannot divide by zero"
                            )));
                        }
                        a / b
                    }
                    _ => unreachable!(),
                };
                Ok(json!(value))
            }
            "Output" => self.input_value(node_id, port),
            other => Err(CliError::Unsupported(format!(
                "node {node_id:?} has unsupported type {other:?}"
            ))),
        }
    }

    fn input_value(&mut self, node_id: &str, port: &str) -> Result<Value, CliError> {
        let key = (node_id.to_string(), port.to_string());
        if let Some((from, from_port)) = self.edge_by_target.get(&key).cloned() {
            return self.eval(&from, &from_port);
        }

        let node = self
            .workflow
            .node_meta
            .get(node_id)
            .ok_or_else(|| CliError::Eval(format!("missing node {node_id:?}")))?;

        node.params
            .get(port)
            .or_else(|| node.input_defaults.get(port))
            .cloned()
            .ok_or_else(|| CliError::Eval(format!("missing input {node_id}.{port}")))
    }

    fn number_input(&mut self, node_id: &str, port: &str) -> Result<f64, CliError> {
        let value = self.input_value(node_id, port)?;
        value.as_f64().ok_or_else(|| {
            CliError::Eval(format!(
                "input {node_id}.{port} must be numeric, got {}",
                value_type_name(&value)
            ))
        })
    }
}

fn ensure_port(node: &NodeMeta, node_id: &str, port: &str) -> Result<(), CliError> {
    if node.outputs.iter().any(|candidate| candidate == port) {
        Ok(())
    } else {
        Err(CliError::Eval(format!(
            "{} node {node_id:?} does not produce port {port:?}",
            node.type_name
        )))
    }
}

fn value_to_text(value: &Value) -> String {
    match value {
        Value::Null => String::new(),
        Value::String(text) => text.clone(),
        Value::Bool(value) => value.to_string(),
        Value::Number(value) => value.to_string(),
        Value::Array(_) | Value::Object(_) => value.to_string(),
    }
}

fn value_type_name(value: &Value) -> &'static str {
    match value {
        Value::Null => "null",
        Value::Bool(_) => "bool",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

fn workflow_name(workflow: &Workflow) -> &str {
    workflow.name.as_deref().unwrap_or("Untitled Workflow")
}

fn print_result(result: &Value) -> Result<(), CliError> {
    match result {
        Value::String(text) => println!("{text}"),
        other => println!("{}", serde_json::to_string_pretty(other)?),
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn text_workflow() -> Workflow {
        serde_json::from_str(include_str!("../../../templates/text-pipeline.json")).unwrap()
    }

    #[test]
    fn validates_text_workflow() {
        validate_workflow(&text_workflow()).unwrap();
    }

    #[test]
    fn runs_text_workflow() {
        let workflow = text_workflow();
        validate_workflow(&workflow).unwrap();
        let result = PureRunner::new(&workflow).run().unwrap();
        assert_eq!(result, Value::String("Hello World".to_string()));
    }

    #[test]
    fn detects_cycles() {
        let workflow: Workflow = serde_json::from_str(
            r#"{
                "kind": "blacknode.workflow",
                "schema_version": 1,
                "entrypoint": {"node_id": "a", "port": "value"},
                "node_meta": {
                    "a": {
                        "id": "a",
                        "type": "Text",
                        "params": {"value": "A"},
                        "inputs": ["in"],
                        "outputs": ["value"],
                        "input_defaults": {}
                    },
                    "b": {
                        "id": "b",
                        "type": "Text",
                        "params": {"value": "B"},
                        "inputs": ["in"],
                        "outputs": ["value"],
                        "input_defaults": {}
                    }
                },
                "edges": [
                    {"from": "a", "from_port": "value", "to": "b", "to_port": "in"},
                    {"from": "b", "from_port": "value", "to": "a", "to_port": "in"}
                ]
            }"#,
        )
        .unwrap();

        let error = validate_workflow(&workflow).unwrap_err().to_string();
        assert!(error.contains("cycle"));
    }
}
