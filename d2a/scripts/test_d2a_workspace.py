#!/usr/bin/env python3
"""项目本地 d2a 工作区辅助脚本的行为测试。"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("d2a_workspace.py")
SPEC = importlib.util.spec_from_file_location("d2a_workspace", MODULE_PATH)
assert SPEC and SPEC.loader
D2A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D2A)


class WorkspaceTests(unittest.TestCase):
    def init_project(self) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "project"
        root.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            result = D2A.cmd_init(argparse.Namespace(root=str(root)))
        self.assertEqual(result, 0)
        return root

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def claim(stage: str, file: str = "main.py") -> dict:
        return {"source_stage": stage, "claim": f"{stage} 的结论", "symbol": "main", "proves": "证明测试项目的主入口", "confidence": "high", "evidence": [{"file": file}]}

    def complete_boundary_questions(self, root: Path) -> None:
        (root / "main.py").write_text("def main():\n    return 0\n", encoding="utf-8")
        D2A.cmd_align(argparse.Namespace(root=str(root), question=["系统边界是什么？"], summary="问题已对齐"))
        (root / ".d2a/architecture/01_boundary.md").write_text("# 系统边界\n\n证据：main.py::main\n", encoding="utf-8")
        self.write_json(root / ".d2a/architecture/evidence/01_boundary.json", {"schema_version": 1, "stage": "architecture-01-boundary", "claims": [self.claim("architecture-01-boundary")]})
        D2A.cmd_start_questions(argparse.Namespace(root=str(root), summary="分析完成"))
        for index in range(1, 5):
            D2A.cmd_record_qa(argparse.Namespace(root=str(root), question=f"第 {index} 题：哪个描述符合主入口？", option_a="main 是真实主入口", option_b="main 只负责界面渲染", option_c="return 是独立持久化服务", option_d="系统没有运行入口", correct_option="A", distractor_basis=["B|main|main.py::main", "C|return|main.py::main"], answer="A", evaluation="correct", explanation="理解正确", score="理解度良好" if index == 4 else None))

    def prepare_strict_report_fixture(self, root: Path) -> None:
        (root / "main.py").write_text("def main():\n    return 0\n", encoding="utf-8")
        (root / ".d2a/mini/source/main.py").write_text("print('mini ok')\n", encoding="utf-8")
        for path in (root / ".d2a").rglob("*.md"):
            value = path.read_text(encoding="utf-8").replace(D2A.PENDING_MARKER, "")
            path.write_text(value + "\n证据：main.py::main\n", encoding="utf-8")
        for stage, relative in D2A.EVIDENCE_STAGE_FILES.items():
            self.write_json(root / ".d2a" / relative, {"schema_version": 1, "stage": stage, "claims": [self.claim(stage)]})
        qa_record = {"question_total": 4, "question": "哪个描述符合主入口？", "options": {"A": "main 是真实主入口", "B": "main 只负责界面渲染", "C": "return 是独立持久化服务", "D": "系统没有运行入口"}, "correct_option": "A", "distractor_bases": [{"option": "B", "concept": "main", "evidence": "main.py::main"}, {"option": "C", "concept": "return", "evidence": "main.py::main"}], "answer": "A", "evaluation": "correct", "explanation": "理解正确"}
        for stage in D2A.QUESTION_STAGES:
            if stage in D2A.ARCH_QUESTION_STAGES:
                self.write_json(root / f".d2a/qa/{stage}.json", {"schema_version": 1, "stage": stage, "questions": ["本阶段原子问题"]})
            records = []
            for index in range(1, 5):
                record = {**qa_record, "stage": stage, "question_index": index}
                if index == 4:
                    record["understanding_score"] = "理解度良好"
                records.append(json.dumps(record, ensure_ascii=False))
            qa_path = root / f".d2a/qa/{stage}.jsonl"
            qa_path.parent.mkdir(parents=True, exist_ok=True)
            qa_path.write_text("\n".join(records) + "\n", encoding="utf-8")
        self.write_json(root / ".d2a/architecture/99_evidence.json", {"schema_version": 1, "claims": [self.claim(stage) for stage in D2A.EVIDENCE_STAGE_FILES]})
        decisions = ("boundary", "driver", "core-objects", "state-evolution", "cooperation", "dominant-constraint")
        rounds = [{"decision": item, "objection": "质疑", "response": "回应", "strength": "weak", "reason": "代码证据充分", "evidence": ["main.py::main"], "resolved": True} for item in decisions]
        self.write_json(root / ".d2a/challenge/challenge.json", {"schema_version": 1, "rounds": rounds, "recommendation": "继续推进", "review_status": "not-required"})
        for stage, relative in D2A.GATE_STAGE_FILES.items():
            gate = {"schema_version": 1, "provider": {"matched": True, "rationale": "沿用项目技术栈"}, "timebox": {"minutes": 10, "within_budget": True, "fallback": "缩小到单一路径"}, "intent": {"anchor_type": "state", "anchor": "运行状态", "evidence": "main.py::main"}}
            if stage == "mini-scope":
                gate["stack_confirmation"] = {"recommended": "Python", "final": "Python", "changed": False, "user_confirmed": True}
            self.write_json(root / ".d2a" / relative, gate)
        self.write_json(root / ".d2a/mini/build-evidence.json", {"schema_version": 1, "architecture_intent": "运行状态", "entrypoint": "main.py", "source_paths": [".d2a/mini/source/main.py"], "run": {"command": "python3 .d2a/mini/source/main.py", "exit_code": 0, "output": "mini ok"}, "intentionally_unimplemented": ["外部集成"]})
        self.write_json(root / ".d2a/tests/evidence.json", {"schema_version": 1, "success_case": {"command": "python3 .d2a/mini/source/main.py", "expected_behavior": "输出成功信号", "exit_code": 0, "output": "mini ok", "observable_success_signal": "mini ok", "architecture_intent_proven": "状态主路径可运行"}, "failure_case": {"command": "python3 .d2a/mini/source/main.py --invalid", "expected_failure_behavior": "拒绝无效输入", "exit_code": 2, "output": "invalid", "observable_failure_signal": "invalid", "architecture_intent_proven": "错误边界可观察", "observed_expected_failure": True}})

    def test_init_is_additive_and_does_not_inject_project_instructions(self) -> None:
        root = self.init_project()
        boundary = root / ".d2a/architecture/01_boundary.md"
        boundary.write_text("user-owned\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            D2A.cmd_init(argparse.Namespace(root=str(root)))
        self.assertEqual(boundary.read_text(encoding="utf-8"), "user-owned\n")
        self.assertFalse((root / "AGENTS.md").exists())
        self.assertFalse((root / ".gitignore").exists())

    def test_pending_analysis_cannot_start_questions(self) -> None:
        root = self.init_project()
        D2A.cmd_align(argparse.Namespace(root=str(root), question=["边界是什么？"], summary="已对齐"))
        with self.assertRaisesRegex(RuntimeError, "待完成状态"):
            D2A.cmd_start_questions(argparse.Namespace(root=str(root), summary="分析完成"))

    def test_four_questions_and_confirmation_are_required_to_advance(self) -> None:
        root = self.init_project()
        self.complete_boundary_questions(root)
        args = argparse.Namespace(root=str(root), expect="architecture-01-boundary", summary="边界完成", confirmed=False)
        with self.assertRaisesRegex(RuntimeError, "用户确认"):
            D2A.cmd_advance(args)
        args.confirmed = True
        D2A.cmd_advance(args)
        state = json.loads((root / ".d2a/state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["current_stage"], "architecture-02-runtime-driver")
        self.assertEqual(state["current_phase"], "atomic-question-alignment")

    def test_s99_requires_all_six_stages_and_rejects_outside_paths(self) -> None:
        root = self.init_project()
        self.write_json(root / ".d2a/architecture/99_evidence.json", {"schema_version": 1, "claims": [self.claim("architecture-01-boundary", "../outside.txt")]})
        errors = D2A.evidence_errors(root)
        self.assertTrue(any("越出项目根目录" in error for error in errors))
        self.assertTrue(any("尚未覆盖阶段" in error for error in errors))

    def test_empty_mini_source_cannot_pass_build_gate(self) -> None:
        root = self.init_project()
        errors = D2A.build_evidence_errors(root)
        self.assertTrue(any("源码" in error for error in errors))
        self.assertTrue(any("真实命令" in error for error in errors))

    def test_handwritten_minimal_test_flags_do_not_pass(self) -> None:
        root = self.init_project()
        self.write_json(root / ".d2a/tests/evidence.json", {"success_case": {"exit_code": 0}, "failure_case": {"observed_expected_failure": True}})
        self.assertTrue(D2A.test_evidence_errors(root))

    def test_confirmation_question_requires_four_options_and_two_evidenced_distractors(self) -> None:
        root = self.init_project()
        (root / "main.py").write_text("def main():\n    return 0\n", encoding="utf-8")
        state_path = root / ".d2a/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update({"current_phase": "confirmation-questions", "question_index": 0, "question_total": 4})
        self.write_json(state_path, state)
        args = argparse.Namespace(root=str(root), question="占位题", option_a="正确", option_b="错误", option_c="错误", option_d="错误", correct_option="A", distractor_basis=[], answer="A", evaluation="correct", explanation="说明", score=None)
        with self.assertRaisesRegex(RuntimeError, "至少需要两个"):
            D2A.cmd_record_qa(args)

    def test_strong_challenge_requires_recorded_review(self) -> None:
        root = self.init_project()
        (root / "main.py").write_text("def main():\n    return 0\n", encoding="utf-8")
        state_path = root / ".d2a/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update({"current_stage": "architecture-challenge", "current_phase": "challenge-preparation", "question_index": 0, "question_total": 0})
        self.write_json(state_path, state)
        D2A.cmd_start_challenge(argparse.Namespace(root=str(root), summary="开始六轮质疑"))
        decisions = ("boundary", "driver", "core-objects", "state-evolution", "cooperation", "dominant-constraint")
        for index, decision in enumerate(decisions):
            D2A.cmd_record_challenge(argparse.Namespace(root=str(root), decision=decision, objection="质疑", response="回应", strength="strong" if index == 0 else "weak", reason="需要代码复审", evidence=["main.py::main"], resolved=index != 0))
        challenge_md = root / ".d2a/challenge/challenge.md"
        challenge_md.write_text(challenge_md.read_text(encoding="utf-8").replace(D2A.PENDING_MARKER, ""), encoding="utf-8")
        D2A.cmd_finalize_challenge(argparse.Namespace(root=str(root), recommendation="复审", summary="存在强质疑"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["current_phase"], "review-required")
        D2A.cmd_resolve_challenge(argparse.Namespace(root=str(root), evidence=["main.py::main"], summary="已复审并修正"))
        self.assertFalse(D2A.challenge_errors(root))

    def test_challenge_round_requires_file_and_symbol_evidence(self) -> None:
        root = self.init_project()
        state_path = root / ".d2a/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update({"current_stage": "architecture-challenge", "current_phase": "challenge-preparation", "question_index": 0, "question_total": 0})
        self.write_json(state_path, state)
        D2A.cmd_start_challenge(argparse.Namespace(root=str(root), summary="开始六轮质疑"))
        args = argparse.Namespace(root=str(root), decision="boundary", objection="质疑", response="回应", strength="weak", reason="理由", evidence=[], resolved=False)
        with self.assertRaisesRegex(RuntimeError, "至少需要一条"):
            D2A.cmd_record_challenge(args)

    def test_report_generates_exactly_two_a4_pages_and_three_files(self) -> None:
        root = self.init_project()
        self.prepare_strict_report_fixture(root)
        state_path = root / ".d2a/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update({"current_stage": "report", "current_phase": "analysis-generation", "next_stage": "complete"})
        self.write_json(state_path, state)
        with contextlib.redirect_stdout(io.StringIO()):
            D2A.cmd_report(argparse.Namespace(root=str(root)))
        report = root / ".d2a/report"
        for name in ("brief.md", "brief.html", "index.html"):
            self.assertTrue((report / name).is_file())
        brief_html = (report / "brief.html").read_text(encoding="utf-8")
        self.assertEqual(brief_html.count('class="page"'), 2)
        self.assertIn("size:A4", brief_html)
        completed = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(completed["current_stage"], "complete")


if __name__ == "__main__":
    unittest.main()
