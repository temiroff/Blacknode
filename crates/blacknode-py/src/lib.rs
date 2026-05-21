use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};
use pyo3::IntoPyObjectExt;
use blacknode_core::{Graph as RsGraph, NodeMeta, NodeId, Port};
use blacknode_types::Value;
use std::collections::HashMap;

// ── Value conversion ──────────────────────────────────────────────────────────

fn py_to_value(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    if obj.is_none() {
        return Ok(Value::Null);
    }
    if let Ok(b) = obj.extract::<bool>() {
        return Ok(Value::Bool(b));
    }
    if let Ok(i) = obj.extract::<i64>() {
        return Ok(Value::Int(i));
    }
    if let Ok(f) = obj.extract::<f64>() {
        return Ok(Value::Float(f));
    }
    if let Ok(s) = obj.extract::<String>() {
        return Ok(Value::Text(s));
    }
    if let Ok(list) = obj.cast::<PyList>() {
        let v: PyResult<Vec<Value>> = list.iter().map(|item| py_to_value(&item)).collect();
        return Ok(Value::List(v?));
    }
    if let Ok(dict) = obj.cast::<PyDict>() {
        let mut m = HashMap::new();
        for (k, v) in dict.iter() {
            m.insert(k.extract::<String>()?, py_to_value(&v)?);
        }
        return Ok(Value::Map(m));
    }
    Ok(Value::Text(obj.str()?.to_str()?.to_string()))
}

fn value_to_py(py: Python<'_>, val: &Value) -> PyResult<Py<PyAny>> {
    match val {
        Value::Null => Ok(py.None()),
        Value::Bool(b) => b.into_py_any(py),
        Value::Int(i) => i.into_py_any(py),
        Value::Float(f) => f.into_py_any(py),
        Value::Text(s) => s.into_py_any(py),
        Value::List(l) => {
            let items: PyResult<Vec<Py<PyAny>>> = l.iter().map(|v| value_to_py(py, v)).collect();
            Ok(PyList::new(py, items?)?.into_any().unbind())
        }
        Value::Map(m) => {
            let dict = PyDict::new(py);
            for (k, v) in m {
                dict.set_item(k, value_to_py(py, v)?)?;
            }
            Ok(dict.into_any().unbind())
        }
        Value::Bytes(b) => Ok(PyBytes::new(py, b).into_any().unbind()),
    }
}

// ── Python node shim ──────────────────────────────────────────────────────────

struct PyNodeShim {
    meta: NodeMeta,
    cook_fn: Py<PyAny>,
}

impl blacknode_core::Node for PyNodeShim {
    fn meta(&self) -> &NodeMeta { &self.meta }
    fn meta_mut(&mut self) -> &mut NodeMeta { &mut self.meta }

    fn cook(&self, inputs: HashMap<String, Value>) -> anyhow::Result<HashMap<String, Value>> {
        Python::attach(|py| -> PyResult<HashMap<String, Value>> {
            let ctx = PyDict::new(py);
            for (k, v) in &inputs {
                ctx.set_item(k, value_to_py(py, v)?)?;
            }
            let result = self.cook_fn.bind(py).call1((ctx,))?;

            let mut outputs = HashMap::new();
            if let Ok(dict) = result.cast::<PyDict>() {
                for (k, v) in dict.iter() {
                    outputs.insert(k.extract::<String>()?, py_to_value(&v)?);
                }
            } else {
                outputs.insert("output".to_string(), py_to_value(&result)?);
            }
            Ok(outputs)
        })
        .map_err(|e| anyhow::anyhow!("{}", e))
    }
}

// ── PyGraph ───────────────────────────────────────────────────────────────────

#[pyclass]
struct PyGraph {
    inner: RsGraph,
}

#[pymethods]
impl PyGraph {
    #[new]
    fn new() -> Self {
        Self { inner: RsGraph::new() }
    }

    fn add_node(
        &mut self,
        type_name: &str,
        cook_fn: Py<PyAny>,
        ports: Vec<(String, String, String)>, // (name, dir, type_hint)
        params: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<String> {
        let mut meta = NodeMeta::new(type_name);
        for (name, dir, hint) in ports {
            let port = match dir.as_str() {
                "output" => Port::output(name, hint),
                _        => Port::input(name, hint),
            };
            meta.ports.push(port);
        }
        if let Some(p) = params {
            for (k, v) in p.iter() {
                let key = k.extract::<String>()?;
                let val = py_to_value(&v)?;
                meta.params.insert(key, val);
            }
        }
        let shim = PyNodeShim { meta, cook_fn };
        let id = self.inner.add_node(Box::new(shim));
        Ok(id.to_string())
    }

    fn connect(
        &mut self,
        from_id: &str, from_port: &str,
        to_id: &str,   to_port: &str,
    ) -> PyResult<()> {
        let from: NodeId = from_id.parse().map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("{e}")))?;
        let to:   NodeId = to_id.parse().map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("{e}")))?;
        self.inner.connect(from, from_port, to, to_port)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("{e}")))?;
        Ok(())
    }

    fn cook(&self, py: Python<'_>, node_id: &str, port: &str) -> PyResult<Py<PyAny>> {
        let id: NodeId = node_id.parse().map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("{e}")))?;
        let val = self.inner.cook(id, port)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("{e}")))?;
        value_to_py(py, &val)
    }
}

// ── Module ────────────────────────────────────────────────────────────────────

#[pymodule]
fn blacknode_rs(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyGraph>()?;
    Ok(())
}
