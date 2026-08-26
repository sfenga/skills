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

    @staticmethod
    def valid_qa_record(stage: str, index: int) -> dict:
        question_types = ("scenario", "counterfactual", "failure-analysis", "tradeoff")
        return {
            "stage": stage,
            "question_index": index,
            "question_total": 4,
            "question_type": question_types[index - 1],
            "coverage": D2A.QUESTION_COVERAGE[stage][index - 1],
            "option_kind": "runtime-behavior",
            "scenario": "一个请求在进程重启后继续执行，需要恢复既有状态并重新进入主流程。",
            "question": "在该场景下，哪条调用顺序符合当前实现且没有把恢复职责放错模块？",
            "options": {
                "A": "请求先由 main 建立运行上下文，再调用 load_state 恢复状态",
                "B": "请求先由 load_state 建立运行上下文，再调用 main 恢复状态",
                "C": "请求由 main 跳过状态恢复，直接把运行上下文标记为完成",
                "D": "请求由 load_state 持久化新上下文，再由 main 只读取最终结果",
            },
            "correct_option": "A",
            "correct_reasoning": "main 负责组织主流程，load_state 负责恢复既有状态，两处职责共同决定调用顺序。",
            "reasoning_anchors": ["main.py::main", "main.py::load_state"],
            "distractor_bases": [
                {
                    "option": "B",
                    "concept": "load_state",
                    "evidence": "main.py::load_state",
                    "plausible_reason": "load_state 确实参与恢复且位于启动主路径附近",
                    "wrong_reason": "它把运行上下文建立和主流程编排错误交给恢复函数",
                },
                {
                    "option": "C",
                    "concept": "main",
                    "evidence": "main.py::main",
                    "plausible_reason": "main 确实负责入口，直接完成看起来可以缩短路径",
                    "wrong_reason": "它跳过状态恢复，无法满足重启后继续执行的场景约束",
                },
            ],
            "blind_elimination_check": "四项都使用真实函数并描述可运行顺序，必须结合入口和恢复职责才能排除。",
            "answer_leak_check": "四项长度接近且语气一致，正确项没有绝对词或文档原句。",
            "answer": "A",
            "evaluation": "correct",
            "explanation": "结合入口编排与状态恢复职责判断。",
        }

    def valid_qa_args(self, root: Path, stage: str, index: int, score: str | None = None) -> argparse.Namespace:
        record = self.valid_qa_record(stage, index)
        return argparse.Namespace(
            root=str(root),
            question_type=record["question_type"],
            coverage=record["coverage"],
            option_kind=record["option_kind"],
            scenario=record["scenario"],
            question=record["question"],
            option_a=record["options"]["A"],
            option_b=record["options"]["B"],
            option_c=record["options"]["C"],
            option_d=record["options"]["D"],
            correct_option=record["correct_option"],
            correct_reasoning=record["correct_reasoning"],
            reasoning_anchor=record["reasoning_anchors"],
            distractor_basis=[
                "|".join((basis["option"], basis["concept"], basis["evidence"], basis["plausible_reason"], basis["wrong_reason"]))
                for basis in record["distractor_bases"]
            ],
            blind_elimination_check=record["blind_elimination_check"],
            answer_leak_check=record["answer_leak_check"],
            answer=record["answer"],
            evaluation=record["evaluation"],
            explanation=record["explanation"],
            score=score,
        )

    def complete_boundary_questions(self, root: Path) -> None:
        (root / "main.py").write_text("def load_state():\n    return 'ready'\n\ndef main():\n    return load_state()\n", encoding="utf-8")
        D2A.cmd_align(argparse.Namespace(root=str(root), question=["系统边界是什么？"], summary="问题已对齐"))
        (root / ".d2a/architecture/01_boundary.md").write_text("# 系统边界\n\n证据：main.py::main\n", encoding="utf-8")
        self.write_json(root / ".d2a/architecture/evidence/01_boundary.json", {"schema_version": 1, "stage": "architecture-01-boundary", "claims": [self.claim("architecture-01-boundary")]})
        D2A.cmd_start_questions(argparse.Namespace(root=str(root), summary="分析完成"))
        for index in range(1, 5):
            D2A.cmd_record_qa(self.valid_qa_args(root, "architecture-01-boundary", index, "理解度良好" if index == 4 else None))

    def prepare_strict_report_fixture(self, root: Path) -> None:
        (root / "main.py").write_text("def load_state():\n    return 'ready'\n\ndef main():\n    return load_state()\n", encoding="utf-8")
        (root / ".d2a/mini/source/main.py").write_text("def main():\n    print('mini ok')\n\nmain()\n", encoding="utf-8")
        for path in (root / ".d2a").rglob("*.md"):
            value = path.read_text(encoding="utf-8").replace(D2A.PENDING_MARKER, "")
            path.write_text(value + "\n证据：main.py::main\n", encoding="utf-8")
        for stage, relative in D2A.EVIDENCE_STAGE_FILES.items():
            self.write_json(root / ".d2a" / relative, {"schema_version": 1, "stage": stage, "claims": [self.claim(stage)]})
        for stage in D2A.QUESTION_STAGES:
            if stage in D2A.ARCH_QUESTION_STAGES:
                self.write_json(root / f".d2a/qa/{stage}.json", {"schema_version": 1, "stage": stage, "questions": ["本阶段原子问题"]})
            records = []
            for index in range(1, 5):
                record = self.valid_qa_record(stage, index)
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
        self.write_json(
            root / ".d2a/mini/architecture-alignment.json",
            {
                "schema_version": 1,
                "principle": "preserve-architecture-reduce-detail",
                "component_mappings": [
                    {
                        "full_component": "主流程编排器",
                        "mini_component": "主流程编排器",
                        "full_responsibility": "组织请求进入与状态恢复",
                        "mini_responsibility": "组织请求进入与状态恢复",
                        "responsibility_preserved": True,
                        "full_evidence": "main.py::main",
                        "mini_evidence": ".d2a/mini/source/main.py::main",
                    }
                ],
                "dependency_direction": {"preserved": True, "rationale": "入口仍向内调用状态逻辑", "full_evidence": "main.py::main", "mini_evidence": ".d2a/mini/source/main.py::main"},
                "state_ownership": {"preserved": True, "rationale": "状态仍由主流程持有", "full_evidence": "main.py::main", "mini_evidence": ".d2a/mini/source/main.py::main"},
                "boundary_semantics": {"preserved": True, "rationale": "入口边界保持一致", "full_evidence": "main.py::main", "mini_evidence": ".d2a/mini/source/main.py::main"},
                "simplifications": [{"detail": "省略外部集成", "reason": "不影响主流程职责", "responsibility_unchanged": True}],
                "deviations": [],
            },
        )
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

    def test_mini_gate_requires_full_to_mini_architecture_alignment(self) -> None:
        root = self.init_project()
        self.write_json(
            root / ".d2a/mini/gates/scope.json",
            {
                "schema_version": 1,
                "provider": {"matched": True, "rationale": "沿用项目技术栈"},
                "timebox": {"minutes": 20, "within_budget": True, "fallback": "缩小功能范围"},
                "intent": {"anchor_type": "cooperation", "anchor": "请求主链", "evidence": "main.py::main"},
                "stack_confirmation": {"recommended": "Python", "final": "Python", "changed": False, "user_confirmed": True},
            },
        )
        errors = D2A.gate_errors(root, "mini-scope")
        self.assertTrue(any("架构一致性" in error or "职责映射" in error for error in errors))

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

    def test_obvious_recall_question_is_rejected(self) -> None:
        root = self.init_project()
        (root / "main.py").write_text("def load_state():\n    return 'ready'\n\ndef main():\n    return load_state()\n", encoding="utf-8")
        state_path = root / ".d2a/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update({"current_phase": "confirmation-questions", "question_index": 0, "question_total": 4})
        self.write_json(state_path, state)
        args = argparse.Namespace(
            root=str(root),
            question_type="scenario",
            coverage="boundary-consequence",
            option_kind="runtime-behavior",
            scenario="一个新请求到达服务，团队需要判断它将从哪里进入并开始处理。",
            question="哪个描述符合主入口？",
            option_a="main 是真实主入口",
            option_b="main 只负责界面渲染",
            option_c="return 是独立持久化服务",
            option_d="系统没有运行入口",
            correct_option="A",
            correct_reasoning="main 定义了主流程并调用 load_state，因此它承担请求进入后的编排职责。",
            reasoning_anchor=["main.py::main", "main.py::load_state"],
            distractor_basis=[
                "B|main|main.py::main|main 确实是入口附近的真实概念|它与界面渲染职责没有对应代码关系",
                "C|return|main.py::main|return 确实出现在入口函数的实现中|它只是语言控制流而不是持久化服务",
            ],
            blind_elimination_check="四个选项都来自当前项目概念，需要阅读实现以后才能判断职责。",
            answer_leak_check="四个选项没有通过措辞或长度泄漏正确答案。",
            answer="A",
            evaluation="correct",
            explanation="理解正确",
            score=None,
        )
        with self.assertRaisesRegex(RuntimeError, "难度"):
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
