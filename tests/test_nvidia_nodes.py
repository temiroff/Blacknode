from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from blacknode.node import _NODE_REGISTRY


class NvidiaNodeTests(unittest.TestCase):
    def test_blueprint_plan_selects_video_and_retrieval_stack(self):
        result = _NODE_REGISTRY["NVIDIABlueprintPlan"]({
            "goal": "Build video search with retrieval and benchmark deployment latency."
        })

        self.assertIn("NVIDIA NIM", result["technologies"])
        self.assertIn("Cosmos", result["technologies"])
        self.assertIn("NeMo Retriever", result["technologies"])
        self.assertIn("TensorRT-LLM", result["technologies"])
        self.assertIn("nvidia-video-intelligence-mission-control", result["blueprint"]["recommended_templates"])
        self.assertIn("nvidia-nim-benchmark", result["blueprint"]["recommended_templates"])

    def test_nim_docker_command_returns_cross_platform_commands(self):
        result = _NODE_REGISTRY["NIMDockerCommand"]({
            "image": "nvcr.io/nim/meta/llama-3.1-8b-instruct:latest",
            "container_name": "demo-nim",
            "port": 9000,
            "cache_dir": ".cache/nim",
            "ngc_api_key_env": "NGC_API_KEY",
        })

        self.assertIn("docker run", result["powershell"])
        self.assertIn("--gpus all", result["powershell"])
        self.assertIn("demo-nim", result["bash"])
        self.assertEqual(result["endpoint_url"], "http://127.0.0.1:9000/v1")

    def test_video_folder_input_builds_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "clip.mp4").write_bytes(b"demo")
            (root / "notes.txt").write_text("ignore", encoding="utf-8")

            result = _NODE_REGISTRY["VideoFolderInput"]({
                "folder": str(root),
                "extensions": ".mp4,.mov",
            })

        self.assertEqual(result["manifest"]["file_count"], 1)
        self.assertEqual(result["files"][0]["name"], "clip.mp4")
        self.assertIn("files: 1", result["summary"])

    def test_video_intelligence_nodes_assemble_report(self):
        deployment = _NODE_REGISTRY["NVIDIADeploymentChoice"]({
            "mode": "hybrid",
            "local_endpoint_url": "http://127.0.0.1:8000/v1",
            "model": "nim:nvidia/llama-3.3-nemotron-super-49b-v1.5",
        })
        manifest = {
            "folder": "videos",
            "files": [{"name": "camera-1.mp4", "path": "videos/camera-1.mp4"}],
            "file_count": 1,
        }
        video = _NODE_REGISTRY["NVIDIAVideoSummaryPlan"]({
            "manifest": manifest,
            "goal": "Build video search with retrieval.",
            "deployment": deployment["blueprint"],
        })
        retriever = _NODE_REGISTRY["NVIDIARetrieverIndexPlan"]({
            "manifest": manifest,
            "video_plan": video["plan"],
            "query": "Find key events.",
        })
        qa = _NODE_REGISTRY["NVIDIAQuestionAnswerPlan"]({
            "question": "What happened?",
            "index_plan": retriever["index_plan"],
            "deployment": deployment["blueprint"],
        })
        report = _NODE_REGISTRY["NVIDIAMissionReport"]({
            "goal": "Build video search with retrieval.",
            "folder_summary": "files: 1",
            "video_plan": video["plan"],
            "retriever_plan": retriever["index_plan"],
            "qa_plan": qa["answer_plan"],
            "deployment_route": deployment["route"],
        })

        self.assertIn("Cosmos", video["cosmos_path"])
        self.assertIn("NeMo Retriever", retriever["retriever_stack"][0])
        self.assertIn("Nemotron", qa["answer_plan"])
        self.assertIn("Blacknode NVIDIA AI Mission Control", report["report"])
        self.assertIn("Workflow can export to Python", report["checklist"])


if __name__ == "__main__":
    unittest.main()
