#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CodeAgent 安全审查与质量评估模块
路径：./scripts/codeagent_security.py
"""

import os
import sys
import json
import ast
import re
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import importlib.util


class RiskLevel(Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityFinding:
    level: RiskLevel
    category: str
    message: str
    line: int
    code_snippet: str = ""
    suggestion: str = ""
    file_path: str = ""
    tool: str = ""


@dataclass
class QualityIssue:
    category: str
    message: str
    line: int
    code_snippet: str = ""
    suggestion: str = ""
    tool: str = ""


@dataclass
class SecurityReport:
    file_path: str
    findings: List[SecurityFinding] = field(default_factory=list)
    quality_issues: List[QualityIssue] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.SAFE
    passed: bool = True
    quality_score: int = 0
    quality_details: Dict[str, Any] = field(default_factory=dict)
    test_coverage: float = 0.0
    test_results: Dict[str, Any] = field(default_factory=dict)
    
    def add_finding(self, finding: SecurityFinding):
        self.findings.append(finding)
        if finding.level == RiskLevel.CRITICAL:
            self.risk_level = RiskLevel.CRITICAL
            self.passed = False
        elif finding.level == RiskLevel.HIGH and self.risk_level.value != "critical":
            self.risk_level = RiskLevel.HIGH
            self.passed = False
        elif finding.level == RiskLevel.MEDIUM and self.risk_level.value not in ["critical", "high"]:
            self.risk_level = RiskLevel.MEDIUM
        elif finding.level == RiskLevel.LOW and self.risk_level.value not in ["critical", "high", "medium"]:
            self.risk_level = RiskLevel.LOW
    
    def add_quality_issue(self, issue: QualityIssue):
        self.quality_issues.append(issue)
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str)


class RuffChecker:
    
    def __init__(self):
        self._ruff_available = self._check_ruff()
    
    def _check_ruff(self) -> bool:
        try:
            import ruff
            return True
        except ImportError:
            return False
    
    def check(self, code: str, file_path: str = "main.py") -> Dict[str, Any]:
        result = {
            "tool": "ruff",
            "issues": [],
            "error": None,
            "formatted": []
        }
        
        if not self._ruff_available:
            result["error"] = "Ruff 未安装，请运行: pip install ruff"
            return result
        
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_path = f.name
            
            import subprocess
            proc = subprocess.run(
                ['ruff', 'check', temp_path, '--output-format', 'json'],
                capture_output=True,
                text=True
            )
            os.unlink(temp_path)
            
            if proc.stdout:
                data = json.loads(proc.stdout)
                for item in data:
                    issue = {
                        "line": item.get("location", {}).get("row", 0),
                        "column": item.get("location", {}).get("column", 0),
                        "message": item.get("message", ""),
                        "code": item.get("code", ""),
                        "severity": self._map_severity(item.get("level", "")),
                        "suggestion": self._get_suggestion(item.get("code", "")),
                        "fixable": item.get("fixable", False)
                    }
                    result["issues"].append(issue)
                    result["formatted"].append(
                        f"[{issue['severity']}] {issue['message']} (行 {issue['line']})"
                    )
            
            return result
        except Exception as e:
            result["error"] = str(e)
            return result
    
    def _map_severity(self, level: str) -> str:
        mapping = {
            "error": "high",
            "warning": "medium",
            "suggestion": "low",
        }
        return mapping.get(level, "medium")
    
    def _get_suggestion(self, code: str) -> str:
        suggestions = {
            "F401": "删除未使用的导入",
            "F841": "删除未使用的变量",
            "E501": "将行拆分为多行",
            "E711": "使用 `is None` 而不是 `== None`",
            "E712": "使用 `is` 比较布尔值",
        }
        return suggestions.get(code, "请参考 Ruff 文档修复")


class MypyChecker:
    
    def __init__(self):
        self._mypy_available = self._check_mypy()
    
    def _check_mypy(self) -> bool:
        try:
            import mypy
            return True
        except ImportError:
            return False
    
    def check(self, code: str, file_path: str = "main.py") -> Dict[str, Any]:
        result = {
            "tool": "mypy",
            "issues": [],
            "error": None,
            "formatted": []
        }
        
        if not self._mypy_available:
            result["error"] = "Mypy 未安装，请运行: pip install mypy"
            return result
        
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_path = f.name
            
            import subprocess
            proc = subprocess.run(
                ['mypy', temp_path, '--no-error-summary', '--no-color'],
                capture_output=True,
                text=True
            )
            os.unlink(temp_path)
            
            for line in proc.stdout.split('\n'):
                if not line.strip():
                    continue
                match = re.search(r'([^:]+):(\d+):\s*(error|warning):\s*(.*)', line)
                if match:
                    issue = {
                        "line": int(match.group(2)),
                        "severity": match.group(3),
                        "message": match.group(4),
                        "suggestion": "请检查类型注解"
                    }
                    result["issues"].append(issue)
                    result["formatted"].append(
                        f"[{issue['severity']}] {issue['message']} (行 {issue['line']})"
                    )
            
            return result
        except Exception as e:
            result["error"] = str(e)
            return result


class BanditChecker:
    
    def __init__(self):
        self._bandit_available = self._check_bandit()
    
    def _check_bandit(self) -> bool:
        try:
            import bandit
            return True
        except ImportError:
            return False
    
    def check(self, code: str, file_path: str = "main.py") -> Dict[str, Any]:
        result = {
            "tool": "bandit",
            "issues": [],
            "error": None,
            "formatted": [],
            "risk_level": "safe"
        }
        
        if not self._bandit_available:
            result["error"] = "Bandit 未安装，请运行: pip install bandit"
            return result
        
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_path = f.name
            
            import subprocess
            proc = subprocess.run(
                ['bandit', '-f', 'json', temp_path],
                capture_output=True,
                text=True
            )
            os.unlink(temp_path)
            
            if proc.stdout:
                data = json.loads(proc.stdout)
                results = data.get("results", [])
                for item in results:
                    issue = {
                        "line": item.get("line_num", 0),
                        "severity": item.get("issue_severity", "MEDIUM"),
                        "confidence": item.get("issue_confidence", "MEDIUM"),
                        "message": item.get("issue_text", ""),
                        "test_id": item.get("test_id", ""),
                        "suggestion": self._get_suggestion(item.get("test_id", ""))
                    }
                    result["issues"].append(issue)
                    result["formatted"].append(
                        f"[{issue['severity']}] {issue['message']} (行 {issue['line']}, 置信度 {issue['confidence']})"
                    )
                
                # 计算风险等级
                if result["issues"]:
                    severities = [i["severity"] for i in result["issues"]]
                    if "HIGH" in severities:
                        result["risk_level"] = "critical"
                    elif "MEDIUM" in severities:
                        result["risk_level"] = "high"
                    else:
                        result["risk_level"] = "medium"
            
            return result
        except Exception as e:
            result["error"] = str(e)
            return result
    
    def _get_suggestion(self, test_id: str) -> str:
        suggestions = {
            "B101": "避免使用 assert 进行安全检查",
            "B102": "避免使用 exec 执行动态代码",
            "B104": "避免使用 eval 执行动态代码",
            "B105": "避免硬编码敏感信息",
            "B106": "避免使用 pickle 加载不可信数据",
            "B110": "避免使用 try/except/pass 忽略异常",
            "B301": "避免使用 pickle",
            "B302": "避免使用 marshal",
            "B303": "避免使用 MD5 或 SHA1",
            "B306": "避免使用 mktemp",
            "B307": "避免使用 eval",
            "B308": "避免使用 mark_safe",
            "B309": "避免使用 httpsconnection",
            "B310": "避免使用 urllib",
            "B311": "避免使用 random",
            "B312": "避免使用 telnetlib",
            "B313": "避免使用 xmlrpclib",
            "B314": "避免使用 xml",
            "B315": "避免使用 xmllib",
            "B316": "避免使用 xmlrpc",
        }
        return suggestions.get(test_id, "请参考 Bandit 文档修复")


class ShellCheckChecker:
    
    def __init__(self):
        self._shellcheck_available = self._check_shellcheck()
    
    def _check_shellcheck(self) -> bool:
        try:
            import subprocess
            proc = subprocess.run(
                ['shellcheck', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return proc.returncode == 0
        except (ImportError, subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def check(self, code: str, file_path: str = "script.sh") -> Dict[str, Any]:
        result = {
            "tool": "shellcheck",
            "issues": [],
            "error": None,
            "formatted": [],
            "risk_level": "safe"
        }
        
        if not self._shellcheck_available:
            result["error"] = "ShellCheck 未安装，请运行: apt install shellcheck 或 brew install shellcheck"
            return result
        
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write(code)
                temp_path = f.name
            
            import subprocess
            proc = subprocess.run(
                ['shellcheck', '-f', 'json', temp_path],
                capture_output=True,
                text=True
            )
            os.unlink(temp_path)
            
            if proc.stdout:
                data = json.loads(proc.stdout)
                for item in data.get("comments", []):
                    issue = {
                        "line": item.get("line", 0),
                        "column": item.get("column", 0),
                        "severity": self._map_severity(item.get("level", "")),
                        "message": item.get("message", ""),
                        "code": item.get("code", 0),
                        "suggestion": self._get_suggestion(item.get("code", 0))
                    }
                    result["issues"].append(issue)
                    result["formatted"].append(
                        f"[{issue['severity']}] 行 {issue['line']}: {issue['message']} (SC{issue['code']})"
                    )
                
                # 计算风险等级
                if result["issues"]:
                    severities = [i["severity"] for i in result["issues"]]
                    if "error" in severities:
                        result["risk_level"] = "high"
                    elif "warning" in severities:
                        result["risk_level"] = "medium"
                    else:
                        result["risk_level"] = "low"
            
            return result
        except Exception as e:
            result["error"] = str(e)
            return result
    
    def _map_severity(self, level: str) -> str:
        mapping = {
            "error": "high",
            "warning": "medium",
            "info": "low",
            "style": "low"
        }
        return mapping.get(level, "medium")
    
    def _get_suggestion(self, code: int) -> str:
        suggestions = {
            1000: "使用 $ 引用变量时应加双引号防止分词",
            1001: "在 [[ ]] 中使用 =~ 时模式必须用引号包裹",
            1003: "使用 -z/-n 检查空字符串",
            1004: "使用 $@ 传递参数时加双引号保留参数边界",
            1007: "使用 ${var} 明确变量边界",
            1010: "使用 'read' 时用 -r 防止转义反斜杠",
            1012: "未使用的变量，建议删除或注释",
            1017: "在指定目录路径时不要以斜杠结尾",
            1034: "使用相对路径时要小心，建议使用绝对路径",
            1035: "使用 -d 检查目录时确保路径正确",
            1036: "使用 -f 检查文件时确保路径正确",
            1044: "使用 'for' 循环时小心分词问题",
            1045: "使用 'while' 循环时小心 IFS 设置",
            1049: "使用 'case' 语句时注意匹配模式",
            1050: "使用 '=' 比较字符串时需加双引号",
            1052: "使用 'function' 关键字不兼容 POSIX",
            1054: "使用 'local' 时确保在函数内",
            1056: "使用 'readonly' 时注意作用域",
            1058: "使用 'export' 时注意变量作用域",
            1061: "使用 'trap' 时注意信号名称",
            1062: "使用 'getopts' 时注意参数格式",
            1066: "使用 'set -u' 时小心未定义变量",
            1071: "使用 '${!var}' 间接引用可能危险",
            1072: "使用 'eval' 时应避免，考虑使用其他方式",
            1073: "使用 'source' 时应使用绝对路径或相对路径",
            1077: "使用 'find' 时小心 -exec 参数",
            1083: "使用 'let' 时应使用算术运算符",
            1087: "使用 'select' 时注意 PS3 提示符设置",
            1090: "使用 'printf' 输出格式字符串",
            1091: "使用 'shift' 时确保参数数量足够",
            1098: "使用 'while read' 循环时注意子 shell",
            1099: "使用 'read' 时未设置 IFS 可能导致问题",
            1102: "使用 'set -e' 时注意错误处理",
            1104: "使用 'ulimit' 时注意权限",
            1111: "使用 'exec' 重定向时注意顺序",
            1112: "使用 'trap' 时捕获信号的顺序",
            1121: "使用 'declare' 时注意作用域",
            1122: "使用 'typeset' 时注意与 declare 的区别",
            1123: "使用 'alias' 时注意是否影响其他命令",
            1124: "使用 'unset' 时确保变量存在",
            1125: "使用 'wait' 时确认后台进程 ID",
            1126: "使用 'sleep' 时注意时间单位",
            1127: "使用 'jobs' 时查看后台作业状态",
            1128: "使用 'bg' 和 'fg' 前后台切换作业",
            1129: "使用 'kill' 时确保信号正确",
            1130: "使用 'nice' 调整进程优先级",
            1131: "使用 'nohup' 时注意重定向输出",
            1132: "使用 'time' 时注意命令路径",
        }
        return suggestions.get(code, f"SC{code}: 请参考 ShellCheck 文档修复")


class PythonTestGenerator:
    
    def __init__(self):
        self._pytest_available = self._check_pytest()
    
    def _check_pytest(self) -> bool:
        try:
            import pytest
            return True
        except ImportError:
            return False
    
    def generate_tests(self, code: str, function_names: List[str] = None) -> str:
        """根据代码生成 Pytest 测试用例"""
        if not function_names:
            function_names = self._extract_functions(code)
        
        test_lines = [
            "import pytest",
            "import sys",
            "from pathlib import Path",
            "",
            "# 导入要测试的模块",
            "# 注意：需要将上面的代码保存为模块后导入",
            "",
            "class TestCode:",
            ""
        ]
        
        for func in function_names:
            test_lines.extend([
                f"    def test_{func}_basic(self):",
                f'        """测试 {func} 基本功能"""',
                f"        # TODO: 替换为实际测试",
                f"        # result = {func}()",
                f"        # assert result is not None",
                f"        assert True  # 占位测试",
                "",
                f"    def test_{func}_edge_cases(self):",
                f'        """测试 {func} 边界情况"""',
                f"        # TODO: 添加边界测试",
                f"        assert True  # 占位测试",
                "",
            ])
        
        test_lines.append("")
        test_lines.append("# 运行测试: pytest test_*.py -v --cov=. --cov-report=term")
        
        return "\n".join(test_lines)
    
    def _extract_functions(self, code: str) -> List[str]:
        """提取代码中的函数名"""
        funcs = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                    funcs.append(node.name)
        except SyntaxError:
            pass
        return funcs
    
    def run_tests(self, code: str, test_code: str, session_id: str = "test") -> Dict[str, Any]:
        """运行 pytest 并返回结果"""
        result = {
            "passed": False,
            "total": 0,
            "passed_count": 0,
            "failed_count": 0,
            "error_count": 0,
            "coverage": 0.0,
            "output": "",
            "error": None,
            "details": []
        }
        
        if not self._pytest_available:
            result["error"] = "Pytest 未安装，请运行: pip install pytest pytest-cov"
            return result
        
        try:
            import tempfile
            import subprocess
            
            workspace = Path(f"./codeagent_workspace/{session_id}")
            workspace.mkdir(parents=True, exist_ok=True)
            
            # 保存主代码
            main_path = workspace / "main.py"
            main_path.write_text(code, encoding='utf-8')
            
            # 保存测试代码
            test_path = workspace / "test_main.py"
            test_path.write_text(test_code, encoding='utf-8')
            
            # 运行 pytest
            proc = subprocess.run(
                [
                    'pytest', str(test_path),
                    '--tb=short',
                    '--maxfail=5',
                    '-q'
                ],
                cwd=str(workspace),
                capture_output=True,
                text=True
            )
            
            result["output"] = proc.stdout + proc.stderr
            result["passed"] = proc.returncode == 0
            
            # 解析结果
            for line in proc.stdout.split('\n'):
                if 'passed' in line:
                    import re
                    match = re.search(r'(\d+)\s+passed', line)
                    if match:
                        result["passed_count"] = int(match.group(1))
                if 'failed' in line:
                    match = re.search(r'(\d+)\s+failed', line)
                    if match:
                        result["failed_count"] = int(match.group(1))
            
            # 运行覆盖率
            try:
                cov_proc = subprocess.run(
                    [
                        'pytest', str(test_path),
                        f'--cov={workspace}',
                        '--cov-report=json'
                    ],
                    cwd=str(workspace),
                    capture_output=True,
                    text=True
                )
                
                cov_path = workspace / "coverage.json"
                if cov_path.exists():
                    cov_data = json.loads(cov_path.open().read())
                    # 计算总覆盖率
                    files = cov_data.get("files", {})
                    if files:
                        total_stmts = 0
                        total_miss = 0
                        for file_data in files.values():
                            total_stmts += file_data.get("summary", {}).get("num_statements", 0)
                            total_miss += file_data.get("summary", {}).get("missing_lines", 0)
                        if total_stmts > 0:
                            result["coverage"] = (total_stmts - total_miss) / total_stmts * 100
            except:
                pass
            
            # 清理临时文件
            # 保留用于调试
            
            return result
        except Exception as e:
            result["error"] = str(e)
            return result


class CodeSecurityScanner:
    
    def __init__(self):
        self.findings: List[SecurityFinding] = []
        self.quality_issues: List[QualityIssue] = []
        
        self.ruff_checker = RuffChecker()
        self.mypy_checker = MypyChecker()
        self.bandit_checker = BanditChecker()
        self.shellcheck_checker = ShellCheckChecker()
        self.test_generator = PythonTestGenerator()
    
    def scan_python(self, code: str, file_path: str = "") -> SecurityReport:
        report = SecurityReport(file_path=file_path)
        
        # 安全检查
        self._check_dangerous_patterns(code, report)
        
        # Ruff 检查
        ruff_result = self.ruff_checker.check(code, file_path)
        if ruff_result.get("error"):
            report.add_finding(SecurityFinding(
                level=RiskLevel.LOW,
                category="tool_error",
                message=f"Ruff 检查失败: {ruff_result['error']}",
                line=0,
                code_snippet="",
                suggestion="请确保 Ruff 已正确安装",
                file_path=file_path,
                tool="ruff"
            ))
        else:
            for issue in ruff_result.get("issues", []):
                level = self._map_ruff_level(issue.get("severity", "medium"))
                report.add_finding(SecurityFinding(
                    level=level,
                    category="style",
                    message=issue.get("message", ""),
                    line=issue.get("line", 0),
                    code_snippet="",
                    suggestion=issue.get("suggestion", ""),
                    file_path=file_path,
                    tool="ruff"
                ))
            
            # 记录质量信息
            report.quality_details["ruff_issues"] = len(ruff_result.get("issues", []))
        
        # Mypy 检查
        mypy_result = self.mypy_checker.check(code, file_path)
        if mypy_result.get("error"):
            report.add_finding(SecurityFinding(
                level=RiskLevel.LOW,
                category="tool_error",
                message=f"Mypy 检查失败: {mypy_result['error']}",
                line=0,
                code_snippet="",
                suggestion="请确保 Mypy 已正确安装",
                file_path=file_path,
                tool="mypy"
            ))
        else:
            for issue in mypy_result.get("issues", []):
                level = RiskLevel.MEDIUM if issue.get("severity") == "error" else RiskLevel.LOW
                report.add_finding(SecurityFinding(
                    level=level,
                    category="type",
                    message=issue.get("message", ""),
                    line=issue.get("line", 0),
                    code_snippet="",
                    suggestion=issue.get("suggestion", ""),
                    file_path=file_path,
                    tool="mypy"
                ))
            
            report.quality_details["mypy_issues"] = len(mypy_result.get("issues", []))
        
        # Bandit 检查
        bandit_result = self.bandit_checker.check(code, file_path)
        if bandit_result.get("error"):
            report.add_finding(SecurityFinding(
                level=RiskLevel.LOW,
                category="tool_error",
                message=f"Bandit 检查失败: {bandit_result['error']}",
                line=0,
                code_snippet="",
                suggestion="请确保 Bandit 已正确安装",
                file_path=file_path,
                tool="bandit"
            ))
        else:
            for issue in bandit_result.get("issues", []):
                level = self._map_bandit_level(issue.get("severity", "MEDIUM"))
                report.add_finding(SecurityFinding(
                    level=level,
                    category="security",
                    message=issue.get("message", ""),
                    line=issue.get("line", 0),
                    code_snippet="",
                    suggestion=issue.get("suggestion", ""),
                    file_path=file_path,
                    tool="bandit"
                ))
            
            report.quality_details["bandit_issues"] = len(bandit_result.get("issues", []))
        
        # 代码质量评估
        quality_score, quality_details = self._assess_quality(code)
        report.quality_score = quality_score
        report.quality_details.update(quality_details)
        
        # 生成测试代码并运行
        test_result = self._generate_and_run_tests(code)
        report.test_coverage = test_result.get("coverage", 0.0)
        report.test_results = test_result
        
        if report.quality_score < 75:
            report.passed = False
        
        # 生成摘要
        self._generate_summary(report)
        
        return report
    
    def scan_shell(self, code: str, file_path: str = "") -> SecurityReport:
        """扫描 Shell 代码"""
        report = SecurityReport(file_path=file_path)
        
        # ShellCheck 检查
        shellcheck_result = self.shellcheck_checker.check(code, file_path)
        
        if shellcheck_result.get("error"):
            report.add_finding(SecurityFinding(
                level=RiskLevel.LOW,
                category="tool_error",
                message=f"ShellCheck 检查失败: {shellcheck_result['error']}",
                line=0,
                code_snippet="",
                suggestion="请确保 ShellCheck 已正确安装",
                file_path=file_path,
                tool="shellcheck"
            ))
        else:
            for issue in shellcheck_result.get("issues", []):
                severity = issue.get("severity", "medium")
                level = self._map_shellcheck_level(severity)
                report.add_finding(SecurityFinding(
                    level=level,
                    category="style" if severity == "low" else "security",
                    message=issue.get("message", ""),
                    line=issue.get("line", 0),
                    code_snippet="",
                    suggestion=issue.get("suggestion", ""),
                    file_path=file_path,
                    tool="shellcheck"
                ))
            
            report.quality_details["shellcheck_issues"] = len(shellcheck_result.get("issues", []))
        
        # 基本质量评估
        quality_score, quality_details = self._assess_shell_quality(code)
        report.quality_score = quality_score
        report.quality_details.update(quality_details)
        
        if report.quality_score < 75:
            report.passed = False
        
        self._generate_summary(report)
        return report
    
    def _check_dangerous_patterns(self, code: str, report: SecurityReport):
        """检查危险模式"""
        dangerous_patterns = [
            (r'os\.system\s*\(', RiskLevel.HIGH, "使用 os.system 执行系统命令"),
            (r'subprocess\.(call|Popen|run|check_output)\s*\(', RiskLevel.HIGH, "使用 subprocess 执行系统命令"),
            (r'eval\s*\(', RiskLevel.CRITICAL, "使用 eval 执行动态代码"),
            (r'exec\s*\(', RiskLevel.CRITICAL, "使用 exec 执行动态代码"),
            (r'__import__\s*\(', RiskLevel.HIGH, "使用 __import__ 动态导入"),
            (r'rm\s+-rf\s+/?', RiskLevel.CRITICAL, "包含 rm -rf / 命令"),
            (r'base64\.b64decode\s*\(', RiskLevel.MEDIUM, "使用 base64 解码"),
            (r'pickle\.loads?\s*\(', RiskLevel.MEDIUM, "使用 pickle 加载数据"),
            (r'socket\.(socket|connect)\s*\(', RiskLevel.HIGH, "使用 socket 网络连接"),
            (r'ctypes\.(CDLL|windll)\s*\(', RiskLevel.CRITICAL, "使用 ctypes 调用动态库"),
        ]
        
        lines = code.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern, level, msg in dangerous_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    report.add_finding(SecurityFinding(
                        level=level,
                        category="dangerous_pattern",
                        message=msg,
                        line=i,
                        code_snippet=line.strip(),
                        suggestion="请使用安全的替代方案",
                        file_path=report.file_path,
                        tool="pattern_checker"
                    ))
    
    def _map_ruff_level(self, severity: str) -> RiskLevel:
        mapping = {
            "high": RiskLevel.HIGH,
            "medium": RiskLevel.MEDIUM,
            "low": RiskLevel.LOW
        }
        return mapping.get(severity, RiskLevel.LOW)
    
    def _map_bandit_level(self, severity: str) -> RiskLevel:
        mapping = {
            "HIGH": RiskLevel.CRITICAL,
            "MEDIUM": RiskLevel.HIGH,
            "LOW": RiskLevel.MEDIUM
        }
        return mapping.get(severity, RiskLevel.MEDIUM)
    
    def _map_shellcheck_level(self, severity: str) -> RiskLevel:
        mapping = {
            "high": RiskLevel.HIGH,
            "medium": RiskLevel.MEDIUM,
            "low": RiskLevel.LOW
        }
        return mapping.get(severity, RiskLevel.LOW)
    
    def _assess_quality(self, code: str) -> Tuple[int, Dict[str, Any]]:
        """评估代码质量"""
        score = 100
        details = {}
        
        lines = code.split('\n')
        total_lines = len([l for l in lines if l.strip()])
        
        # 文档字符串
        docstring_pattern = r'""".*?"""|\'\'\'.*?\'\'\''
        docstrings = re.findall(docstring_pattern, code, re.DOTALL)
        if total_lines > 20 and len(docstrings) < 2:
            score -= 10
            details["docstrings"] = len(docstrings)
            details["docstring_warning"] = "文档字符串不足"
        
        # 嵌套深度
        nesting = 0
        max_nesting = 0
        for line in lines:
            stripped = line.strip()
            if stripped.endswith(':') and not stripped.startswith('#'):
                nesting += 1
                max_nesting = max(max_nesting, nesting)
            elif stripped.startswith(('return', 'break', 'continue')):
                nesting = max(0, nesting - 1)
        if max_nesting > 4:
            score -= 15
            details["max_nesting"] = max_nesting
            details["nesting_warning"] = f"最大嵌套深度 {max_nesting}"
        details["max_nesting"] = max_nesting
        
        # 行长度
        long_lines = [i+1 for i, l in enumerate(lines) if len(l) > 120]
        if long_lines:
            score -= min(10, len(long_lines))
            details["long_lines"] = len(long_lines)
        
        # 注释比例
        comment_lines = [l for l in lines if l.strip().startswith('#')]
        ratio = len(comment_lines) / max(1, total_lines)
        if total_lines > 30 and ratio < 0.05:
            score -= 10
            details["comment_ratio"] = round(ratio * 100, 1)
            details["comment_warning"] = "注释过少"
        
        # 函数检查
        func_pattern = r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)'
        funcs = re.findall(func_pattern, code)
        long_funcs = 0
        for func in funcs:
            pattern = rf'def\s+{func}\s*\([^)]*\):[^\n]*\n((?:\s+.*\n)*?)(?=\n\S|$)'
            match = re.search(pattern, code, re.MULTILINE)
            if match:
                body_lines = [l for l in match.group(1).split('\n') if l.strip()]
                if len(body_lines) > 50:
                    long_funcs += 1
        if long_funcs:
            score -= min(15, long_funcs * 5)
            details["long_functions"] = long_funcs
        
        # 类型注解
        type_hint_pattern = r'[a-zA-Z_][a-zA-Z0-9_]*\s*:\s*[a-zA-Z_][a-zA-Z0-9_]*\s*[=,]|->\s*[a-zA-Z_]'
        hints = len(re.findall(type_hint_pattern, code))
        func_count = len(re.findall(r'def\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(', code))
        if func_count > 5 and hints < func_count * 0.5:
            score -= 10
            details["type_hints"] = hints
            details["type_hint_warning"] = "类型注解不足"
        
        # 代码异味
        smells = 0
        if 'global ' in code:
            smells += 1
        if re.search(r'except\s*:\s*pass', code):
            smells += 1
        if re.search(r'if\s+len\([^)]*\)\s*[=!]=\s*0', code):
            smells += 1
        if re.search(r'type\([^)]*\)\s*==', code):
            smells += 1
        if smells > 0:
            score -= min(10, smells * 3)
            details["code_smells"] = smells
        
        score = max(0, min(100, score))
        return score, details
    
    def _assess_shell_quality(self, code: str) -> Tuple[int, Dict[str, Any]]:
        """评估 Shell 代码质量"""
        score = 100
        details = {}
        
        lines = code.split('\n')
        total_lines = len([l for l in lines if l.strip()])
        
        # 检查 shebang
        if total_lines > 0:
            first_line = lines[0].strip()
            if not first_line.startswith('#!') and total_lines > 3:
                score -= 10
                details["shebang_warning"] = "缺少 shebang 行，建议添加 #!/bin/bash 或 #!/usr/bin/env bash"
        
        # 行长度
        long_lines = [i+1 for i, l in enumerate(lines) if len(l) > 120]
        if long_lines:
            score -= min(10, len(long_lines))
            details["long_lines"] = len(long_lines)
        
        # 注释比例
        comment_lines = [l for l in lines if l.strip().startswith('#')]
        ratio = len(comment_lines) / max(1, total_lines)
        if total_lines > 30 and ratio < 0.05:
            score -= 10
            details["comment_ratio"] = round(ratio * 100, 1)
            details["comment_warning"] = "注释过少"
        
        # 检查是否有 set -e
        if 'set -e' not in code and 'set -o errexit' not in code:
            score -= 10
            details["errexit_warning"] = "建议添加 'set -e' 使脚本在错误时退出"
        
        # 检查是否有 set -u
        if 'set -u' not in code and 'set -o nounset' not in code:
            score -= 5
            details["nounset_warning"] = "建议添加 'set -u' 使脚本在未定义变量时退出"
        
        # 检查是否有 set -o pipefail
        if 'pipefail' not in code:
            score -= 5
            details["pipefail_warning"] = "建议添加 'set -o pipefail' 使管道命令在错误时退出"
        
        score = max(0, min(100, score))
        return score, details
    
    def _generate_and_run_tests(self, code: str) -> Dict[str, Any]:
        result = {
            "coverage": 0.0,
            "passed": False,
            "total": 0,
            "passed_count": 0,
            "failed_count": 0,
            "error": None,
            "test_code": ""
        }
        
        # 提取函数名
        funcs = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                    funcs.append(node.name)
        except SyntaxError:
            funcs = []
        
        if not funcs:
            result["error"] = "没有可测试的函数"
            return result
        
        # 生成测试代码
        test_code = self.test_generator.generate_tests(code, funcs)
        result["test_code"] = test_code
        
        # 运行测试
        test_result = self.test_generator.run_tests(code, test_code)
        result.update(test_result)
        
        # 如果覆盖率低于90%，生成提示
        if result["coverage"] < 90:
            result["coverage_warning"] = f"测试覆盖率 {result['coverage']:.1f}% < 90%，需要增加测试用例"
        
        return result
    
    def _generate_summary(self, report: SecurityReport):
        parts = []
        if report.findings:
            critical = sum(1 for f in report.findings if f.level == RiskLevel.CRITICAL)
            high = sum(1 for f in report.findings if f.level == RiskLevel.HIGH)
            medium = sum(1 for f in report.findings if f.level == RiskLevel.MEDIUM)
            low = sum(1 for f in report.findings if f.level == RiskLevel.LOW)
            
            if critical:
                parts.append(f"{critical} 个严重问题")
            if high:
                parts.append(f"{high} 个高危问题")
            if medium:
                parts.append(f"{medium} 个中危问题")
            if low:
                parts.append(f"{low} 个低危问题")
        
        if report.quality_score < 75:
            parts.append(f"质量评分 {report.quality_score}/100 低于标准")
        else:
            parts.append(f"质量评分 {report.quality_score}/100")
        
        if report.test_coverage > 0:
            parts.append(f"测试覆盖率 {report.test_coverage:.1f}%")
        
        report.summary = "发现 " + ", ".join(parts) if parts else "代码检查通过"
        report.passed = (report.quality_score >= 75 and 
                        not any(f.level in [RiskLevel.CRITICAL, RiskLevel.HIGH] for f in report.findings))


def scan_code(code: str, file_path: str = "", language: str = "auto") -> SecurityReport:
    scanner = CodeSecurityScanner()
    
    if language == "auto":
        if file_path:
            ext = Path(file_path).suffix.lower()
            if ext in ['.py', '.pyw']:
                language = 'python'
            elif ext in ['.sh', '.bash', '.zsh']:
                language = 'shell'
            elif ext in ['.js', '.mjs']:
                language = 'javascript'
            else:
                language = 'python'
        else:
            language = 'python'
    
    if language == 'python':
        return scanner.scan_python(code, file_path)
    elif language == 'shell':
        return scanner.scan_shell(code, file_path)
    else:
        report = SecurityReport(file_path=file_path)
        report.add_finding(SecurityFinding(
            level=RiskLevel.LOW,
            category="unsupported",
            message=f"不支持的语言: {language}",
            line=0,
            code_snippet="",
            suggestion=f"支持的语言: python, shell",
            file_path=file_path,
            tool="scanner"
        ))
        return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description='CodeAgent 安全审查模块')
    parser.add_argument('--code', type=str, help='代码内容')
    parser.add_argument('--code-file', type=str, help='代码文件路径')
    parser.add_argument('--language', type=str, default='auto', help='编程语言 (python/shell/auto)')
    parser.add_argument('--output', type=str, help='输出文件路径')
    parser.add_argument('--test', action='store_true', help='运行测试')
    parser.add_argument('--gen-test', action='store_true', help='仅生成测试代码')
    
    args = parser.parse_args()
    
    if args.test:
        print("运行安全审查测试...")
        test_code = '''
import os
import subprocess
import base64
import pickle

def dangerous_function(data):
    os.system('rm -rf /tmp')
    subprocess.call(['shutdown', '-h', 'now'])
    result = base64.b64decode(data)
    eval(result)
    return pickle.loads(result)

def safe_function(name: str) -> str:
    """安全函数测试"""
    return f"Hello, {name}!"
'''
        report = scan_code(test_code, 'test.py', 'python')
        print(report.to_json())
        
        print(f"风险等级: {report.risk_level.value}")
        print(f"通过: {report.passed}")
        print(f"质量评分: {report.quality_score}/100")
        print(f"测试覆盖率: {report.test_coverage:.1f}%")
        print(f"发现 {len(report.findings)} 个问题")
        
        # 测试 Shell 代码
        print("\n测试 Shell 代码检查...")
        shell_code = '''#!/bin/bash
rm -rf /
echo "Hello"
'''
        report2 = scan_code(shell_code, 'test.sh', 'shell')
        print(f"Shell 风险等级: {report2.risk_level.value}")
        print(f"Shell 质量评分: {report2.quality_score}/100")
        print(f"发现 {len(report2.findings)} 个 Shell 问题")
        return
    
    if args.code:
        code = args.code
    elif args.code_file:
        with open(args.code_file, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()
    else:
        print("错误: 请提供 --code 或 --code-file", file=sys.stderr)
        sys.exit(1)
    
    if args.gen_test:
        generator = PythonTestGenerator()
        funcs = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                    funcs.append(node.name)
        except:
            pass
        test_code = generator.generate_tests(code, funcs)
        print(test_code)
        return
    
    report = scan_code(code, args.code_file or '', args.language)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report.to_json())
    else:
        print(report.to_json())
    
    if not report.passed or report.risk_level in [RiskLevel.CRITICAL, RiskLevel.HIGH]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
