#!/usr/bin/env python3
"""为 d2a Skill 提供确定性的项目本地工作区管理。"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path


SCHEMA_VERSION = 1
PENDING_MARKER = "<!-- d2a:pending -->"
STAGES = [
    "architecture-01-boundary",
    "architecture-02-runtime-driver",
    "architecture-03-core-objects",
    "architecture-04-state-evolution",
    "architecture-05-module-cooperation",
    "architecture-06-constraints-tradeoffs",
    "architecture-99-code-map",
    "architecture-07-overview",
    "architecture-challenge",
    "mini-scope",
    "mini-design",
    "mini-build",
    "mini-test",
    "report",
    "complete",
]
STAGE_LABELS = {
    "architecture-01-boundary": "分析 1/8｜系统边界",
    "architecture-02-runtime-driver": "分析 2/8｜运行驱动",
    "architecture-03-core-objects": "分析 3/8｜核心对象",
    "architecture-04-state-evolution": "分析 4/8｜状态演化",
    "architecture-05-module-cooperation": "分析 5/8｜模块协作",
    "architecture-06-constraints-tradeoffs": "分析 6/8｜约束与取舍",
    "architecture-99-code-map": "分析 7/8｜代码地图",
    "architecture-07-overview": "分析 8/8｜架构总览",
    "architecture-challenge": "质疑 1/1｜架构质疑",
    "mini-scope": "实现 1/4｜最小范围",
    "mini-design": "实现 2/4｜最小设计",
    "mini-build": "实现 3/4｜最小构建",
    "mini-test": "实现 4/4｜最小测试",
    "report": "报告 1/1｜报告构建",
    "complete": "已完成",
}
PHASE_LABELS = {
    "atomic-question-alignment": "原子问题对齐",
    "analysis-generation": "分析生成",
    "confirmation-questions": "确认题",
    "stage-ready": "阶段就绪",
    "challenge-preparation": "质疑准备",
    "challenge-dialogue": "质疑对话",
    "challenge-summary": "质疑汇总",
    "review-required": "需要复审",
}
ARCH_QUESTION_STAGES = {
    "architecture-01-boundary",
    "architecture-02-runtime-driver",
    "architecture-03-core-objects",
    "architecture-04-state-evolution",
    "architecture-05-module-cooperation",
    "architecture-06-constraints-tradeoffs",
    "architecture-07-overview",
}
MINI_STAGES = {"mini-scope", "mini-design", "mini-build", "mini-test"}
QUESTION_STAGES = ARCH_QUESTION_STAGES | MINI_STAGES
EVIDENCE_STAGE_FILES = {
    "architecture-01-boundary": "architecture/evidence/01_boundary.json",
    "architecture-02-runtime-driver": "architecture/evidence/02_runtime_driver.json",
    "architecture-03-core-objects": "architecture/evidence/03_core_objects.json",
    "architecture-04-state-evolution": "architecture/evidence/04_state_evolution.json",
    "architecture-05-module-cooperation": "architecture/evidence/05_module_cooperation.json",
    "architecture-06-constraints-tradeoffs": "architecture/evidence/06_constraints_tradeoffs.json",
}
GATE_STAGE_FILES = {
    "mini-scope": "mini/gates/scope.json",
    "mini-design": "mini/gates/design.json",
    "mini-build": "mini/gates/build.json",
    "mini-test": "mini/gates/test.json",
}
ARTIFACTS = {
    "architecture-01-boundary": ["architecture/01_boundary.md", EVIDENCE_STAGE_FILES["architecture-01-boundary"]],
    "architecture-02-runtime-driver": ["architecture/02_runtime_driver.md", EVIDENCE_STAGE_FILES["architecture-02-runtime-driver"]],
    "architecture-03-core-objects": ["architecture/03_core_objects.md", EVIDENCE_STAGE_FILES["architecture-03-core-objects"]],
    "architecture-04-state-evolution": ["architecture/04_state_evolution.md", EVIDENCE_STAGE_FILES["architecture-04-state-evolution"]],
    "architecture-05-module-cooperation": ["architecture/05_module_cooperation.md", EVIDENCE_STAGE_FILES["architecture-05-module-cooperation"]],
    "architecture-06-constraints-tradeoffs": ["architecture/06_constraints_tradeoffs.md", EVIDENCE_STAGE_FILES["architecture-06-constraints-tradeoffs"]],
    "architecture-99-code-map": [
        "architecture/99_code_map.md",
        "architecture/99_evidence.json",
    ],
    "architecture-07-overview": ["architecture/07_overview.md"],
    "architecture-challenge": ["challenge/challenge.md"],
    "mini-scope": ["mini/scope.md", GATE_STAGE_FILES["mini-scope"]],
    "mini-design": ["mini/design.md", GATE_STAGE_FILES["mini-design"]],
    "mini-build": ["mini/build-plan.md", "mini/source/README.md", "mini/build-evidence.json", GATE_STAGE_FILES["mini-build"]],
    "mini-test": ["tests/test-plan.md", "tests/evidence.json", GATE_STAGE_FILES["mini-test"]],
    "report": ["report/outline.md"],
}


def stage_label(stage: str | None) -> str:
    return STAGE_LABELS.get(str(stage), str(stage))


def phase_label(phase: str | None) -> str:
    return PHASE_LABELS.get(str(phase), str(phase))


def initial_phase(stage: str) -> str:
    if stage in ARCH_QUESTION_STAGES:
        return "atomic-question-alignment"
    if stage == "architecture-challenge":
        return "challenge-preparation"
    return "analysis-generation"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def resolve_root(raw: str | None) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
        return Path(result.stdout.strip()).resolve()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return Path.cwd().resolve()


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"缺少文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON 格式无效：{path}：{exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON 顶层必须是对象：{path}")
    return value


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_history(d2a_dir: Path, event: dict) -> None:
    path = d2a_dir / "history.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def workspace(root: Path) -> Path:
    return root / ".d2a"


def template_root() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "workspace-template"


def copy_templates_missing(d2a_dir: Path) -> list[str]:
    source = template_root()
    if not source.is_dir():
        raise RuntimeError(f"缺少工作区模板：{source}")
    created: list[str] = []
    for item in sorted(source.rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(source)
        destination = d2a_dir / relative
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, destination)
        created.append(relative.as_posix())
    return created


def cmd_init(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    if not root.is_dir():
        raise RuntimeError(f"项目根目录不存在：{root}")
    d2a_dir = workspace(root)
    d2a_dir.mkdir(exist_ok=True)
    config_path = d2a_dir / "config.json"
    if config_path.exists():
        config = load_json(config_path)
        configured_root = Path(str(config.get("project_root", ""))).resolve()
        if configured_root != root:
            raise RuntimeError(
                f"现有工作区属于 {configured_root}，不是 {root}"
            )
    else:
        write_json(
            config_path,
            {
                "schema_version": SCHEMA_VERSION,
                "project_name": root.name,
                "project_root": str(root),
                "created_at": utc_now(),
            },
        )

    created = copy_templates_missing(d2a_dir)
    state_path = d2a_dir / "state.json"
    if not state_path.exists():
        timestamp = utc_now()
        write_json(
            state_path,
            {
                "schema_version": SCHEMA_VERSION,
                "current_stage": STAGES[0],
                "current_phase": initial_phase(STAGES[0]),
                "completed_stages": [],
                "next_stage": STAGES[1],
                "question_index": 0,
                "question_total": 1,
                "updated_at": timestamp,
            },
        )
        append_history(
            d2a_dir,
            {
                "timestamp": timestamp,
                "event": "initialized",
                "stage": STAGES[0],
                "summary": "创建项目本地 d2a 工作区。",
            },
        )
        created.extend(["config.json", "state.json", "history.jsonl"])
    else:
        state = load_json(state_path)
        validate_state(state)
        if "current_phase" not in state:
            state.update(
                {
                    "current_phase": initial_phase(state["current_stage"]),
                    "question_index": 0,
                    "question_total": 1 if state["current_stage"] in ARCH_QUESTION_STAGES else 0,
                    "updated_at": utc_now(),
                }
            )
            write_json(state_path, state)

    print(f"d2a 工作区：{d2a_dir}")
    print(f"本次创建文件：{len(created)}")
    print(f"当前阶段：{stage_label(load_json(state_path)['current_stage'])}")
    return 0


def validate_state(state: dict) -> None:
    if state.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError(
            f"不支持的状态结构版本：{state.get('schema_version')!r}"
        )
    current = state.get("current_stage")
    if current not in STAGES:
        raise RuntimeError(f"未知当前阶段：{current!r}")
    completed = state.get("completed_stages")
    if not isinstance(completed, list) or any(item not in STAGES for item in completed):
        raise RuntimeError("completed_stages 只能包含已知阶段")
    phase = state.get("current_phase")
    if phase is not None and not isinstance(phase, str):
        raise RuntimeError("current_phase 必须是字符串")


def read_state(root: Path) -> tuple[Path, dict]:
    d2a_dir = workspace(root)
    state = load_json(d2a_dir / "state.json")
    validate_state(state)
    return d2a_dir, state


def cmd_status(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    d2a_dir, state = read_state(root)
    print(f"项目：{root}")
    print(f"工作区：{d2a_dir}")
    print(f"当前阶段：{stage_label(state['current_stage'])}")
    print(f"当前步骤：{phase_label(state.get('current_phase')) if state.get('current_phase') else '未记录'}")
    print(f"问题进度：{state.get('question_index', 0)}/{state.get('question_total', 0)}")
    print(f"下一阶段：{stage_label(state.get('next_stage')) if state.get('next_stage') else '无'}")
    print(f"已完成：{len(state['completed_stages'])}/{len(STAGES) - 1}")
    print("当前产物：")
    for relative in ARTIFACTS.get(state["current_stage"], []):
        print(f"- .d2a/{relative}")
    return 0


def project_file_error(root: Path, relative: str) -> str | None:
    root = root.resolve()
    if not relative or Path(relative).is_absolute():
        return f"不是项目内相对路径：{relative!r}"
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return f"路径越出项目根目录：{relative!r}"
    if not candidate.is_file():
        return f"文件不存在：{relative!r}"
    return None


def claim_errors(root: Path, claim: object, context: str, require_stage: bool = False) -> list[str]:
    if not isinstance(claim, dict):
        return [f"{context} 不是对象"]
    errors: list[str] = []
    required = ["claim", "symbol", "proves", "confidence"]
    if require_stage:
        required.append("source_stage")
    for key in required:
        if not str(claim.get(key, "")).strip():
            errors.append(f"{context} 缺少 {key}")
    if claim.get("confidence") not in {"low", "medium", "high"}:
        errors.append(f"{context} 的 confidence 必须是 low、medium 或 high")
    evidence = claim.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{context} 没有代码证据")
        return errors
    for index, item in enumerate(evidence, start=1):
        if not isinstance(item, dict):
            errors.append(f"{context} 第 {index} 条证据不是对象")
            continue
        relative = str(item.get("file", ""))
        path_error = project_file_error(root, relative)
        if path_error:
            errors.append(f"{context} 第 {index} 条证据{path_error}")
    return errors


def stage_evidence_errors(root: Path, stage: str) -> list[str]:
    relative = EVIDENCE_STAGE_FILES[stage]
    try:
        data = load_json(workspace(root) / relative)
    except RuntimeError as exc:
        return [str(exc)]
    if data.get("stage") != stage:
        return [f"{relative} 的 stage 与当前阶段不一致"]
    claims = data.get("claims")
    if not isinstance(claims, list) or not claims:
        return [f"{stage_label(stage)} 至少需要一项真实代码证据"]
    errors: list[str] = []
    for index, claim in enumerate(claims, start=1):
        errors.extend(claim_errors(root, claim, f"{stage_label(stage)} 第 {index} 项结论"))
    return errors


def gate_errors(root: Path, stage: str) -> list[str]:
    relative = GATE_STAGE_FILES[stage]
    try:
        data = load_json(workspace(root) / relative)
    except RuntimeError as exc:
        return [str(exc)]
    errors: list[str] = []
    provider = data.get("provider")
    timebox = data.get("timebox")
    intent = data.get("intent")
    if not isinstance(provider, dict) or not isinstance(provider.get("matched"), bool) or not str(provider.get("rationale", "")).strip():
        errors.append(f"{relative} 缺少 Provider 命中结论或理由")
    if (
        not isinstance(timebox, dict)
        or not isinstance(timebox.get("minutes"), int)
        or timebox.get("minutes", 0) <= 0
        or not isinstance(timebox.get("within_budget"), bool)
        or not str(timebox.get("fallback", "")).strip()
    ):
        errors.append(f"{relative} 缺少有效 Timebox 预算、预算结论或降级方案")
    if (
        not isinstance(intent, dict)
        or intent.get("anchor_type") not in {"object", "state", "cooperation"}
        or not str(intent.get("anchor", "")).strip()
        or not str(intent.get("evidence", "")).strip()
    ):
        errors.append(f"{relative} 缺少有效 Intent 锚点及证据")
    if stage == "mini-scope":
        stack = data.get("stack_confirmation")
        if (
            not isinstance(stack, dict)
            or not str(stack.get("recommended", "")).strip()
            or not str(stack.get("final", "")).strip()
            or not isinstance(stack.get("changed"), bool)
            or stack.get("user_confirmed") is not True
        ):
            errors.append(f"{relative} 缺少用户确认后的最终技术栈")
    return errors


def build_evidence_errors(root: Path) -> list[str]:
    relative = "mini/build-evidence.json"
    try:
        data = load_json(workspace(root) / relative)
    except RuntimeError as exc:
        return [str(exc)]
    errors: list[str] = []
    sources = data.get("source_paths")
    if not isinstance(sources, list) or not sources:
        errors.append("Mini 构建证据至少需要一个源码文件")
    else:
        for item in sources:
            value = str(item)
            path_error = project_file_error(root, value)
            if path_error or not value.startswith(".d2a/mini/source/") or value.endswith("README.md"):
                errors.append(f"Mini 源码无效：{value!r}")
    run = data.get("run")
    if (
        not isinstance(run, dict)
        or not str(run.get("command", "")).strip()
        or run.get("exit_code") != 0
        or not str(run.get("output", "")).strip()
    ):
        errors.append("Mini 构建证据必须包含真实命令、成功退出码和可观察输出")
    if not str(data.get("entrypoint", "")).strip() or not str(data.get("architecture_intent", "")).strip():
        errors.append("Mini 构建证据缺少入口或架构意图")
    return errors


def artifact_errors(root: Path, stage: str) -> list[str]:
    d2a_dir = workspace(root)
    errors: list[str] = []
    for relative in ARTIFACTS.get(stage, []):
        path = d2a_dir / relative
        if not path.is_file():
            errors.append(f"缺少阶段产物：.d2a/{relative}")
            continue
        if path.suffix == ".md" and PENDING_MARKER in path.read_text(encoding="utf-8"):
            errors.append(f"阶段产物仍处于待完成状态：.d2a/{relative}")
    if stage == "architecture-99-code-map":
        errors.extend(evidence_errors(root))
    if stage in EVIDENCE_STAGE_FILES:
        errors.extend(stage_evidence_errors(root, stage))
    if stage in GATE_STAGE_FILES:
        errors.extend(gate_errors(root, stage))
    if stage == "mini-build":
        errors.extend(build_evidence_errors(root))
    if stage == "mini-test":
        errors.extend(test_evidence_errors(root))
    if stage == "architecture-challenge":
        errors.extend(challenge_errors(root))
    return errors


def evidence_errors(root: Path) -> list[str]:
    path = workspace(root) / "architecture" / "99_evidence.json"
    try:
        data = load_json(path)
    except RuntimeError as exc:
        return [str(exc)]
    claims = data.get("claims")
    if not isinstance(claims, list) or not claims:
        return ["S99 证据至少需要一项架构结论"]
    errors: list[str] = []
    covered: set[str] = set()
    for index, claim in enumerate(claims, start=1):
        errors.extend(claim_errors(root, claim, f"S99 第 {index} 项结论", require_stage=True))
        if isinstance(claim, dict) and claim.get("source_stage") in EVIDENCE_STAGE_FILES:
            covered.add(str(claim["source_stage"]))
    missing = set(EVIDENCE_STAGE_FILES) - covered
    if missing:
        errors.append("S99 尚未覆盖阶段：" + "、".join(stage_label(item) for item in STAGES if item in missing))
    return errors


def test_evidence_errors(root: Path) -> list[str]:
    path = workspace(root) / "tests" / "evidence.json"
    try:
        data = load_json(path)
    except RuntimeError as exc:
        return [str(exc)]
    success = data.get("success_case")
    failure = data.get("failure_case")
    errors: list[str] = []
    success_fields = ["command", "expected_behavior", "output", "observable_success_signal", "architecture_intent_proven"]
    if (
        not isinstance(success, dict)
        or success.get("exit_code") != 0
        or any(not str(success.get(field, "")).strip() for field in success_fields)
    ):
        errors.append("成功用例必须包含真实命令、预期行为、退出码 0、输出、成功信号和意图证据")
    failure_fields = ["command", "expected_failure_behavior", "output", "observable_failure_signal", "architecture_intent_proven"]
    if (
        not isinstance(failure, dict)
        or not failure.get("observed_expected_failure")
        or any(not str(failure.get(field, "")).strip() for field in failure_fields)
    ):
        errors.append("失败用例必须包含真实命令、预期失败、实际输出、失败信号和意图证据")
    return errors


def distractor_errors(
    root: Path,
    bases: object,
    options: dict[str, str],
    correct_option: str,
    context: str,
) -> list[str]:
    if not isinstance(bases, list) or len(bases) < 2:
        return [f"{context} 至少需要两个带代码证据的项目概念干扰项"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, basis in enumerate(bases, start=1):
        if not isinstance(basis, dict):
            errors.append(f"{context} 第 {index} 个干扰项依据不是对象")
            continue
        option = str(basis.get("option", ""))
        concept = str(basis.get("concept", "")).strip()
        evidence = str(basis.get("evidence", "")).strip()
        if option not in {"A", "B", "C", "D"} or option == correct_option or option in seen:
            errors.append(f"{context} 第 {index} 个干扰项选项无效或重复")
        else:
            seen.add(option)
        if not concept or concept not in options.get(option, ""):
            errors.append(f"{context} 第 {index} 个项目概念未出现在对应选项中")
        file_part, separator, symbol = evidence.partition("::")
        path_error = project_file_error(root, file_part)
        if not separator or not symbol.strip() or path_error:
            errors.append(f"{context} 第 {index} 个干扰项缺少有效的 文件::符号 证据")
    if len(seen) < 2:
        errors.append(f"{context} 必须覆盖至少两个不同的错误选项")
    return errors


def qa_errors(root: Path, stage: str) -> list[str]:
    d2a_dir = workspace(root)
    errors: list[str] = []
    if stage in ARCH_QUESTION_STAGES:
        try:
            aligned = load_json(d2a_dir / "qa" / f"{stage}.json")
        except RuntimeError as exc:
            errors.append(str(exc))
        else:
            questions = aligned.get("questions")
            if not isinstance(questions, list) or not questions or any(not str(item).strip() for item in questions):
                errors.append(f"{stage_label(stage)} 缺少对齐后的原子问题")
    path = d2a_dir / "qa" / f"{stage}.jsonl"
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        records = [json.loads(line) for line in lines]
    except FileNotFoundError:
        return errors + [f"{stage_label(stage)} 缺少四道确认题记录"]
    except json.JSONDecodeError:
        return errors + [f"{stage_label(stage)} 的确认题记录不是有效 JSONL"]
    if len(records) != 4:
        errors.append(f"{stage_label(stage)} 必须恰好记录四道确认题")
    for index, record in enumerate(records[:4], start=1):
        context = f"{stage_label(stage)} 第 {index} 题"
        if not isinstance(record, dict) or record.get("question_index") != index:
            errors.append(f"{context} 序号无效")
            continue
        options = record.get("options")
        if not isinstance(options, dict) or set(options) != {"A", "B", "C", "D"} or any(not str(value).strip() for value in options.values()):
            errors.append(f"{context} 必须包含非空的 A/B/C/D 四个选项")
            options = {}
        correct = str(record.get("correct_option", ""))
        answer = str(record.get("answer", ""))
        if correct not in {"A", "B", "C", "D"} or answer not in {"A", "B", "C", "D"}:
            errors.append(f"{context} 的正确项或用户答案无效")
        errors.extend(distractor_errors(root, record.get("distractor_bases"), options, correct, context))
        if index == 4:
            score = str(record.get("understanding_score", ""))
            if not score or len(score) > 80:
                errors.append(f"{context} 缺少 80 字以内的理解度评分")
    return errors


def challenge_errors(root: Path) -> list[str]:
    path = workspace(root) / "challenge" / "challenge.json"
    try:
        data = load_json(path)
    except RuntimeError as exc:
        return [str(exc)]
    rounds = data.get("rounds")
    if not isinstance(rounds, list) or len(rounds) != 6:
        return ["架构质疑必须完成六轮并写入 challenge.json"]
    expected = ["boundary", "driver", "core-objects", "state-evolution", "cooperation", "dominant-constraint"]
    errors: list[str] = []
    for index, (round_data, decision) in enumerate(zip(rounds, expected), start=1):
        if not isinstance(round_data, dict) or round_data.get("decision") != decision:
            errors.append(f"架构质疑第 {index} 轮决策顺序无效")
            continue
        for field in ("objection", "response", "reason"):
            if not str(round_data.get(field, "")).strip():
                errors.append(f"架构质疑第 {index} 轮缺少 {field}")
        if round_data.get("strength") not in {"strong", "partial", "weak"}:
            errors.append(f"架构质疑第 {index} 轮强度无效")
        evidence = round_data.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"架构质疑第 {index} 轮缺少代码证据")
        else:
            for item_index, item in enumerate(evidence, start=1):
                file_part, separator, symbol = str(item).partition("::")
                if not separator or not symbol.strip() or project_file_error(root, file_part):
                    errors.append(f"架构质疑第 {index} 轮第 {item_index} 条证据必须是有效的 文件::符号")
    if data.get("recommendation") not in {"继续推进", "复审", "回到架构重审"}:
        errors.append("架构质疑缺少有效最终建议")
    unresolved = any(item.get("strength") == "strong" and not item.get("resolved") for item in rounds if isinstance(item, dict))
    if unresolved and data.get("review_status") != "resolved":
        errors.append("存在尚未完成复审的 strong 架构质疑")
    return errors


def persist_progress(d2a_dir: Path, state: dict, event: str, summary: str) -> None:
    timestamp = utc_now()
    state["updated_at"] = timestamp
    write_json(d2a_dir / "state.json", state)
    append_history(
        d2a_dir,
        {
            "timestamp": timestamp,
            "event": event,
            "stage": state["current_stage"],
            "phase": state.get("current_phase"),
            "question_index": state.get("question_index", 0),
            "question_total": state.get("question_total", 0),
            "summary": summary,
        },
    )


def require_stage_phase(state: dict, stages: set[str], phase: str) -> str:
    stage = str(state["current_stage"])
    if stage not in stages or state.get("current_phase") != phase:
        raise RuntimeError(
            f"当前状态不允许该操作：{stage_label(stage)} / {phase_label(state.get('current_phase'))}"
        )
    return stage


def cmd_align(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    d2a_dir, state = read_state(root)
    stage = require_stage_phase(state, ARCH_QUESTION_STAGES, "atomic-question-alignment")
    questions = [item.strip() for item in args.question if item.strip()]
    if not questions:
        raise RuntimeError("至少需要一个对齐后的原子问题")
    write_json(
        d2a_dir / "qa" / f"{stage}.json",
        {"schema_version": 1, "stage": stage, "questions": questions, "aligned_at": utc_now()},
    )
    state.update({"current_phase": "analysis-generation", "question_index": 0, "question_total": 0})
    persist_progress(d2a_dir, state, "atomic-questions-aligned", args.summary)
    print(f"原子问题已对齐：{stage_label(stage)}")
    return 0


def cmd_start_questions(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    d2a_dir, state = read_state(root)
    stage = require_stage_phase(state, QUESTION_STAGES, "analysis-generation")
    errors = artifact_errors(root, stage)
    if errors:
        raise RuntimeError("分析产物尚未满足确认题门禁：\n- " + "\n- ".join(errors))
    state.update({"current_phase": "confirmation-questions", "question_index": 0, "question_total": 4})
    persist_progress(d2a_dir, state, "confirmation-questions-started", args.summary)
    print(f"确认题已开始：{stage_label(stage)}，共 4 题")
    return 0


def cmd_record_qa(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    d2a_dir, state = read_state(root)
    stage = require_stage_phase(state, QUESTION_STAGES, "confirmation-questions")
    next_index = int(state.get("question_index", 0)) + 1
    if next_index > 4:
        raise RuntimeError("当前阶段的四道确认题已经完成")
    if next_index == 4 and not str(args.score or "").strip():
        raise RuntimeError("第 4 题必须同时记录简短理解回顾与理解度打分")
    if args.score and len(args.score) > 80:
        raise RuntimeError("理解度打分必须控制在 80 字以内")
    options = {"A": args.option_a.strip(), "B": args.option_b.strip(), "C": args.option_c.strip(), "D": args.option_d.strip()}
    if not args.question.strip() or any(not value for value in options.values()):
        raise RuntimeError("确认题必须包含非空题干和 A/B/C/D 四个选项")
    bases = []
    for raw in args.distractor_basis:
        parts = raw.split("|", 2)
        if len(parts) != 3:
            raise RuntimeError("干扰项依据格式必须是 选项|项目概念|文件::符号")
        bases.append({"option": parts[0].strip().upper(), "concept": parts[1].strip(), "evidence": parts[2].strip()})
    basis_errors = distractor_errors(root, bases, options, args.correct_option, f"第 {next_index} 题")
    if basis_errors:
        raise RuntimeError("确认题干扰项门禁未通过：\n- " + "\n- ".join(basis_errors))
    if args.answer == args.correct_option and args.evaluation != "correct":
        raise RuntimeError("用户选择正确项时，判定必须为 correct")
    if args.answer != args.correct_option and args.evaluation == "correct":
        raise RuntimeError("用户未选择正确项时，判定不能为 correct")
    record = {
        "timestamp": utc_now(),
        "stage": stage,
        "question_index": next_index,
        "question_total": 4,
        "question": args.question,
        "options": options,
        "correct_option": args.correct_option,
        "distractor_bases": bases,
        "answer": args.answer,
        "evaluation": args.evaluation,
        "explanation": args.explanation,
    }
    if args.score:
        record["understanding_score"] = args.score
    qa_path = d2a_dir / "qa" / f"{stage}.jsonl"
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    with qa_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    state["question_index"] = next_index
    if next_index == 4:
        state["current_phase"] = "stage-ready"
    persist_progress(d2a_dir, state, "confirmation-answer-recorded", args.explanation)
    print(f"已记录确认题：{next_index}/4")
    return 0


def cmd_ready(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    d2a_dir, state = read_state(root)
    stage = str(state["current_stage"])
    if stage != "architecture-99-code-map" or state.get("current_phase") != "analysis-generation":
        raise RuntimeError("ready 命令仅用于完成 S99 代码地图阶段")
    errors = artifact_errors(root, stage)
    if errors:
        raise RuntimeError("S99 尚未满足证据门禁：\n- " + "\n- ".join(errors))
    state["current_phase"] = "stage-ready"
    persist_progress(d2a_dir, state, "stage-ready", args.summary)
    print("S99 代码地图已通过强制证据门")
    return 0


def cmd_start_challenge(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    d2a_dir, state = read_state(root)
    require_stage_phase(state, {"architecture-challenge"}, "challenge-preparation")
    path = d2a_dir / "challenge" / "challenge.json"
    data = load_json(path)
    data.update({"schema_version": 1, "rounds": data.get("rounds", []), "recommendation": "", "review_status": "not-required"})
    write_json(path, data)
    state.update({"current_phase": "challenge-dialogue", "question_index": len(data["rounds"]), "question_total": 6})
    persist_progress(d2a_dir, state, "challenge-started", args.summary)
    print("架构质疑已开始，共六轮")
    return 0


def cmd_record_challenge(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    d2a_dir, state = read_state(root)
    require_stage_phase(state, {"architecture-challenge"}, "challenge-dialogue")
    path = d2a_dir / "challenge" / "challenge.json"
    data = load_json(path)
    rounds = data.get("rounds")
    if not isinstance(rounds, list):
        raise RuntimeError("challenge.json 的 rounds 无效")
    decisions = ["boundary", "driver", "core-objects", "state-evolution", "cooperation", "dominant-constraint"]
    if len(rounds) >= 6 or args.decision != decisions[len(rounds)]:
        expected = decisions[len(rounds)] if len(rounds) < 6 else "无"
        raise RuntimeError(f"质疑决策顺序无效，下一项应为 {expected}")
    if not args.evidence:
        raise RuntimeError("每轮架构质疑至少需要一条 文件::符号 代码证据")
    evidence = []
    for relative in args.evidence:
        file_part, separator, symbol = relative.partition("::")
        path_error = project_file_error(root, file_part)
        if not separator or not symbol.strip() or path_error:
            raise RuntimeError("质疑证据必须使用有效的 文件::符号 格式")
        evidence.append(relative)
    record = {
        "decision": args.decision,
        "objection": args.objection,
        "response": args.response,
        "strength": args.strength,
        "reason": args.reason,
        "evidence": evidence,
        "resolved": bool(args.resolved),
    }
    rounds.append(record)
    write_json(path, data)
    log_path = d2a_dir / "challenge" / "challenge_log.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": utc_now(), **record}, ensure_ascii=False) + "\n")
    state["question_index"] = len(rounds)
    if len(rounds) == 6:
        state["current_phase"] = "challenge-summary"
    persist_progress(d2a_dir, state, "challenge-round-recorded", args.reason)
    print(f"已记录架构质疑：{len(rounds)}/6")
    return 0


def cmd_finalize_challenge(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    d2a_dir, state = read_state(root)
    require_stage_phase(state, {"architecture-challenge"}, "challenge-summary")
    path = d2a_dir / "challenge" / "challenge.json"
    data = load_json(path)
    if len(data.get("rounds", [])) != 6:
        raise RuntimeError("必须完成六轮质疑后才能汇总")
    challenge_md = d2a_dir / "challenge" / "challenge.md"
    if PENDING_MARKER in challenge_md.read_text(encoding="utf-8"):
        raise RuntimeError("请先完成 challenge.md 的六轮汇总并删除待完成标记")
    data["recommendation"] = args.recommendation
    unresolved = any(item.get("strength") == "strong" and not item.get("resolved") for item in data["rounds"])
    data["review_status"] = "required" if unresolved else "not-required"
    write_json(path, data)
    state["current_phase"] = "review-required" if unresolved else "stage-ready"
    persist_progress(d2a_dir, state, "challenge-finalized", args.summary)
    print("架构质疑需要复审" if unresolved else "架构质疑已完成，可继续推进")
    return 0


def cmd_resolve_challenge(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    d2a_dir, state = read_state(root)
    require_stage_phase(state, {"architecture-challenge"}, "review-required")
    for relative in args.evidence:
        path_error = project_file_error(root, relative.split("::", 1)[0])
        if path_error:
            raise RuntimeError(f"复审证据{path_error}")
    data_path = d2a_dir / "challenge" / "challenge.json"
    data = load_json(data_path)
    data.update({"review_status": "resolved", "review_summary": args.summary, "review_evidence": args.evidence})
    write_json(data_path, data)
    state["current_phase"] = "stage-ready"
    persist_progress(d2a_dir, state, "challenge-review-resolved", args.summary)
    print("strong 架构质疑复审已完成")
    return 0


def cmd_advance(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    d2a_dir, state = read_state(root)
    current = state["current_stage"]
    if current != args.expect:
        raise RuntimeError(f"阶段已经变化：期望 {args.expect}，实际为 {current}")
    if current in {"report", "complete"}:
        raise RuntimeError("进入 report 阶段后请使用 report 命令")
    if not args.confirmed:
        raise RuntimeError("推进下一阶段前必须先向用户展示下一动作，并在用户确认后传入 --confirmed")
    if state.get("current_phase") != "stage-ready":
        raise RuntimeError(f"当前步骤尚未完成：{phase_label(state.get('current_phase'))}")
    errors = artifact_errors(root, current)
    if current in QUESTION_STAGES:
        errors.extend(qa_errors(root, current))
    if errors:
        raise RuntimeError("无法推进阶段：\n- " + "\n- ".join(errors))
    position = STAGES.index(current)
    next_stage = STAGES[position + 1]
    completed = list(state["completed_stages"])
    if current not in completed:
        completed.append(current)
    timestamp = utc_now()
    state.update(
        {
            "current_stage": next_stage,
            "current_phase": initial_phase(next_stage),
            "completed_stages": completed,
            "next_stage": STAGES[position + 2] if position + 2 < len(STAGES) else None,
            "question_index": 0,
            "question_total": 1 if next_stage in ARCH_QUESTION_STAGES else 0,
            "updated_at": timestamp,
        }
    )
    write_json(d2a_dir / "state.json", state)
    append_history(
        d2a_dir,
        {
            "timestamp": timestamp,
            "event": "stage-completed",
            "stage": current,
            "next_stage": next_stage,
            "summary": args.summary,
        },
    )
    print(f"已完成阶段：{stage_label(current)}")
    print(f"当前阶段：{stage_label(next_stage)}")
    return 0


def all_required_errors(root: Path) -> list[str]:
    errors: list[str] = []
    for stage in STAGES:
        errors.extend(artifact_errors(root, stage))
        if stage in QUESTION_STAGES:
            errors.extend(qa_errors(root, stage))
    return errors


def cmd_check(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    _, state = read_state(root)
    config = load_json(workspace(root) / "config.json")
    errors: list[str] = []
    if Path(str(config.get("project_root", ""))).resolve() != root:
        errors.append("config.json 中的 project_root 与请求的项目根目录不一致")
    if args.strict:
        errors.extend(all_required_errors(root))
        if state["current_stage"] not in {"report", "complete"}:
            errors.append(
                f"工作流尚未进入报告阶段：{stage_label(state['current_stage'])}"
            )
    else:
        current = state["current_stage"]
        if current in ARTIFACTS:
            errors.extend(artifact_errors(root, current))
    if errors:
        for error in errors:
            print(f"错误：{error}")
        return 1
    print("d2a 检查通过")
    return 0


def read_artifact(d2a_dir: Path, relative: str) -> str:
    path = d2a_dir / relative
    return path.read_text(encoding="utf-8") if path.is_file() else "不可用"


def compact_text(value: str, limit: int = 260) -> str:
    lines = [line.strip("# -*\t") for line in value.splitlines() if line.strip() and PENDING_MARKER not in line]
    result = " ".join(lines)
    return result if len(result) <= limit else result[: limit - 1].rstrip() + "…"


def build_brief_html(root: Path) -> str:
    d2a_dir = workspace(root)
    architecture_rows = [
        ("边界", "architecture/01_boundary.md"),
        ("驱动", "architecture/02_runtime_driver.md"),
        ("核心对象", "architecture/03_core_objects.md"),
        ("状态机", "architecture/04_state_evolution.md"),
        ("模块协作", "architecture/05_module_cooperation.md"),
        ("约束", "architecture/06_constraints_tradeoffs.md"),
    ]
    rows = "".join(
        f"<tr><th>{html.escape(title)}</th><td>{html.escape(compact_text(read_artifact(d2a_dir, relative), 210))}</td></tr>"
        for title, relative in architecture_rows
    )
    state_diagram = html.escape(read_artifact(d2a_dir, "architecture/04_state_evolution.md"))
    mini_items = [
        ("技术栈与 20% 切片", "mini/scope.md"),
        ("最小设计", "mini/design.md"),
        ("构建摘要", "mini/build-plan.md"),
        ("测试证据", "tests/test-plan.md"),
        ("刻意未实现", "mini/source/README.md"),
    ]
    mini_cards = "".join(
        f"<section><h2>{html.escape(title)}</h2><p>{html.escape(compact_text(read_artifact(d2a_dir, relative), 330))}</p></section>"
        for title, relative in mini_items
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>D2A 双页简报 — {html.escape(root.name)}</title>
<style>
@page{{size:A4;margin:0}}*{{box-sizing:border-box}}body{{margin:0;background:#dde3ea;color:#17202a;font-family:system-ui,sans-serif}}
.page{{width:210mm;height:297mm;padding:13mm 14mm;background:white;margin:8mm auto;overflow:hidden;break-after:page;page-break-after:always}}
.page:last-child{{break-after:auto;page-break-after:auto}}h1{{font-size:22px;margin:0 0 8px}}h2{{font-size:14px;margin:7px 0 3px;color:#174a72}}
table{{width:100%;border-collapse:collapse;font-size:11px;line-height:1.35}}th,td{{border:1px solid #cad3dc;padding:5px;vertical-align:top}}th{{width:18%;background:#eef3f7}}
pre{{font-size:9px;line-height:1.25;max-height:74mm;overflow:hidden;background:#f5f7f9;padding:7px;white-space:pre-wrap}}
section{{border-bottom:1px solid #dfe5eb;padding:3px 0}}section p{{font-size:11px;line-height:1.45;margin:0}}footer{{font-size:9px;color:#667;margin-top:7px}}
@media print{{body{{background:white}}.page{{margin:0}}}}
</style></head><body>
<article class="page" data-page="1"><h1>D2A 架构简报｜{html.escape(root.name)}</h1><h2>状态机 / 架构图</h2><pre>{state_diagram}</pre><h2>六要素</h2><table>{rows}</table><footer>第 1 页 / 2｜证据入口：architecture/99_code_map.md</footer></article>
<article class="page" data-page="2"><h1>D2A Mini 实现简报｜{html.escape(root.name)}</h1>{mini_cards}<footer>第 2 页 / 2｜完整报告：index.html</footer></article>
</body></html>"""


def build_report_html(root: Path) -> str:
    d2a_dir = workspace(root)
    sections = [
        ("架构总览", "architecture/07_overview.md"),
        ("状态演化", "architecture/04_state_evolution.md"),
        ("代码地图", "architecture/99_code_map.md"),
        ("架构质疑", "challenge/challenge.md"),
        ("Mini 范围", "mini/scope.md"),
        ("Mini 设计", "mini/design.md"),
        ("Mini 构建", "mini/build-plan.md"),
        ("测试计划", "tests/test-plan.md"),
    ]
    cards = []
    for title, relative in sections:
        body = html.escape(read_artifact(d2a_dir, relative))
        cards.append(
            f'<section><h2>{html.escape(title)}</h2><p><a href="../{relative}">{relative}</a></p><pre>{body}</pre></section>'
        )
    artifact_links = []
    for path in sorted(d2a_dir.rglob("*")):
        if not path.is_file() or path.name in {"index.html", "brief.html", "brief.md"}:
            continue
        relative = path.relative_to(d2a_dir).as_posix()
        artifact_links.append(f'<li><a href="../{html.escape(relative)}">{html.escape(relative)}</a></li>')
    return f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>D2A 架构报告 — {html.escape(root.name)}</title>
<style>body{{max-width:1100px;margin:auto;padding:32px;font:16px/1.6 system-ui;background:#f5f7fa;color:#17202a}}section{{background:white;border:1px solid #dfe5eb;border-radius:12px;padding:20px;margin:18px 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}a{{color:#1769aa}}@media print{{body{{background:white}}section{{break-inside:avoid}}}}</style></head>
    <body><h1>D2A 架构报告</h1><p>项目：{html.escape(root.name)}｜<a href="brief.html">双页 A4 简报</a>｜<a href="brief.md">Markdown 简报</a></p>{''.join(cards)}<section><h2>全部 .d2a 产物</h2><ul>{''.join(artifact_links)}</ul></section></body></html>"""


def cmd_report(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    d2a_dir, state = read_state(root)
    if state["current_stage"] not in {"report", "complete"}:
        raise RuntimeError(f"生成报告需要进入报告阶段，当前为 {stage_label(state['current_stage'])}")
    errors = all_required_errors(root)
    if errors:
        raise RuntimeError("报告门禁未通过：\n- " + "\n- ".join(errors))
    report_dir = d2a_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    overview = read_artifact(d2a_dir, "architecture/07_overview.md")
    mini = read_artifact(d2a_dir, "mini/scope.md")
    tests = load_json(d2a_dir / "tests" / "evidence.json")
    brief = (
        f"# D2A 双页简报 — {root.name}\n\n## 第 1 页：架构\n\n{overview}\n\n"
        f"## 第 2 页：Mini 与测试\n\n{mini}\n\n### 已执行测试证据\n\n```json\n"
        f"{json.dumps(tests, ensure_ascii=False, indent=2)}\n```\n"
    )
    (report_dir / "brief.md").write_text(brief, encoding="utf-8")
    (report_dir / "brief.html").write_text(build_brief_html(root), encoding="utf-8")
    (report_dir / "index.html").write_text(build_report_html(root), encoding="utf-8")
    required_reports = [report_dir / "brief.md", report_dir / "brief.html", report_dir / "index.html"]
    if any(not path.is_file() or path.stat().st_size == 0 for path in required_reports):
        raise RuntimeError("报告 DoD 未满足：brief.md、brief.html、index.html 必须全部生成")
    brief_html = (report_dir / "brief.html").read_text(encoding="utf-8")
    if brief_html.count('class="page"') != 2 or 'data-page="1"' not in brief_html or 'data-page="2"' not in brief_html:
        raise RuntimeError("报告 DoD 未满足：brief.html 必须严格包含两张 A4 页面")
    if state["current_stage"] == "report":
        timestamp = utc_now()
        completed = list(state["completed_stages"])
        if "report" not in completed:
            completed.append("report")
        state.update(
            {
                "current_stage": "complete",
                "completed_stages": completed,
                "next_stage": None,
                "updated_at": timestamp,
            }
        )
        write_json(d2a_dir / "state.json", state)
        append_history(
            d2a_dir,
            {
                "timestamp": timestamp,
                "event": "report-generated",
                "stage": "report",
                "next_stage": "complete",
                "summary": "严格证据检查通过后生成双页 brief.md、brief.html 和 index.html。",
            },
        )
    print(f"报告：{report_dir / 'index.html'}")
    print(f"双页简报：{report_dir / 'brief.html'}")
    print("当前阶段：已完成")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "status", "check", "report"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--root")
        if name == "check":
            sub.add_argument("--strict", action="store_true")
    advance = subparsers.add_parser("advance")
    advance.add_argument("--root")
    advance.add_argument("--expect", required=True, choices=STAGES)
    advance.add_argument("--summary", required=True)
    advance.add_argument("--confirmed", action="store_true")
    align = subparsers.add_parser("align")
    align.add_argument("--root")
    align.add_argument("--question", action="append", required=True)
    align.add_argument("--summary", required=True)
    start_questions = subparsers.add_parser("start-questions")
    start_questions.add_argument("--root")
    start_questions.add_argument("--summary", required=True)
    record_qa = subparsers.add_parser("record-qa")
    record_qa.add_argument("--root")
    record_qa.add_argument("--question", required=True)
    record_qa.add_argument("--option-a", required=True)
    record_qa.add_argument("--option-b", required=True)
    record_qa.add_argument("--option-c", required=True)
    record_qa.add_argument("--option-d", required=True)
    record_qa.add_argument("--correct-option", required=True, choices=("A", "B", "C", "D"))
    record_qa.add_argument("--distractor-basis", action="append", required=True, help="格式：选项|项目概念|文件::符号；至少提供两个")
    record_qa.add_argument("--answer", required=True, choices=("A", "B", "C", "D"))
    record_qa.add_argument("--evaluation", required=True, choices=("correct", "partial", "incorrect"))
    record_qa.add_argument("--explanation", required=True)
    record_qa.add_argument("--score")
    ready = subparsers.add_parser("ready")
    ready.add_argument("--root")
    ready.add_argument("--summary", required=True)
    start_challenge = subparsers.add_parser("start-challenge")
    start_challenge.add_argument("--root")
    start_challenge.add_argument("--summary", required=True)
    record_challenge = subparsers.add_parser("record-challenge")
    record_challenge.add_argument("--root")
    record_challenge.add_argument("--decision", required=True, choices=("boundary", "driver", "core-objects", "state-evolution", "cooperation", "dominant-constraint"))
    record_challenge.add_argument("--objection", required=True)
    record_challenge.add_argument("--response", required=True)
    record_challenge.add_argument("--strength", required=True, choices=("strong", "partial", "weak"))
    record_challenge.add_argument("--reason", required=True)
    record_challenge.add_argument("--evidence", action="append", required=True, help="格式：文件::符号；至少提供一条")
    record_challenge.add_argument("--resolved", action="store_true")
    finalize_challenge = subparsers.add_parser("finalize-challenge")
    finalize_challenge.add_argument("--root")
    finalize_challenge.add_argument("--recommendation", required=True, choices=("继续推进", "复审", "回到架构重审"))
    finalize_challenge.add_argument("--summary", required=True)
    resolve_challenge = subparsers.add_parser("resolve-challenge")
    resolve_challenge.add_argument("--root")
    resolve_challenge.add_argument("--evidence", action="append", required=True)
    resolve_challenge.add_argument("--summary", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    commands = {
        "init": cmd_init,
        "status": cmd_status,
        "advance": cmd_advance,
        "align": cmd_align,
        "start-questions": cmd_start_questions,
        "record-qa": cmd_record_qa,
        "ready": cmd_ready,
        "start-challenge": cmd_start_challenge,
        "record-challenge": cmd_record_challenge,
        "finalize-challenge": cmd_finalize_challenge,
        "resolve-challenge": cmd_resolve_challenge,
        "check": cmd_check,
        "report": cmd_report,
    }
    try:
        return commands[args.command](args)
    except RuntimeError as exc:
        print(f"d2a 错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
