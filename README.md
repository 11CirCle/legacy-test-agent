# 遗留系统自动化单元测试补全 Agent

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

基于 AST 分析与 LLM 推理的智能测试生成工具，自动为遗留代码生成高覆盖率的单元测试。

## 核心痛点

维护没有测试用例的遗留代码（Legacy Code）极其危险，开发人员不敢重构，导致技术债堆积。手动编写测试用例成本高，且覆盖率难以保证。

## 核心逻辑流

```
代码理解 → 路径分析 → 用例生成 → 自我修正 → 覆盖率达标
```

### 1. 代码理解与路径分析

Agent 扫描目标函数，利用抽象语法树（AST）分析所有可能的代码执行路径（包括边缘情况）。

- 识别所有 if/else、循环、异常处理分支
- 计算圈复杂度
- 提取函数依赖关系
- 自动补充边界条件（None、空集合等）

### 2. 长链推理与用例生成

针对每一条执行路径，Agent 推理出需要的输入参数和预期的输出结果，自动生成符合测试框架的测试代码。

- 支持 OpenAI GPT 系列模型进行推理
- 无 API Key 时自动降级为启发式生成
- 输出标准 PyTest / unittest 格式测试代码

### 3. 自我修正循环

Agent 运行生成的测试代码。如果测试失败，它会捕获错误日志，分析是代码逻辑错误还是测试用例写错了，然后自我修正并重新运行，直到测试通过或达到最大重试次数。

- 自动分析错误类型（AssertionError、TypeError、ImportError 等）
- 支持 LLM 辅助修正
- 可配置最大重试次数

### 4. 成果

能够为一组复杂的遗留函数自动生成 80% 以上覆盖率的单元测试，并验证其正确性。

## 项目结构

```
legacy-test-agent/
├── src/legacy_test_agent/
│   ├── __init__.py
│   ├── main.py                 # CLI 入口
│   ├── agent.py                # 主调度器 Agent
│   ├── analyzer/
│   │   ├── __init__.py
│   │   ├── ast_analyzer.py     # AST 扫描与代码分析
│   │   └── path_enumerator.py  # 执行路径枚举
│   ├── generator/
│   │   ├── __init__.py
│   │   ├── llm_reasoner.py     # LLM 推理测试用例
│   │   └── test_writer.py      # 测试代码生成
│   ├── executor/
│   │   ├── __init__.py
│   │   ├── test_runner.py      # 测试执行器
│   │   └── coverage_collector.py # 覆盖率收集
│   └── corrector/
│       ├── __init__.py
│       └── self_corrector.py   # 自我修正循环
├── tests/
│   └── test_core.py            # 单元测试
├── examples/
│   └── sample_legacy_code.py   # 示例遗留代码
├── config.yaml                 # 配置文件
├── pyproject.toml
└── README.md
```

## 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/your-username/legacy-test-agent.git
cd legacy-test-agent

# 安装
pip install -e .

# 安装开发依赖
pip install -e ".[dev]"
```

### 配置

设置 OpenAI API Key（可选，不设置则使用启发式生成）：

```bash
export OPENAI_API_KEY="sk-your-api-key"    # Linux/macOS
$env:OPENAI_API_KEY="sk-your-api-key"      # Windows PowerShell
```

编辑 `config.yaml` 自定义参数：

```yaml
llm:
  model: "gpt-4o"
correction:
  max_retries: 5
execution:
  coverage_threshold: 80
```

### 使用

#### 为单个文件生成测试

```bash
legacy-test-agent generate examples/sample_legacy_code.py -o tests/generated
```

#### 分析代码结构

```bash
legacy-test-agent analyze examples/sample_legacy_code.py
```

#### 快速测试一段代码

```bash
legacy-test-agent test-one "def add(a, b): return a + b"
```

#### 验证生成的测试

```bash
legacy-test-agent verify tests/generated/test_calculate_order_total.py -s examples/sample_legacy_code.py
```

## API 使用

```python
from legacy_test_agent import LegacyTestAgent

agent = LegacyTestAgent(config_path="config.yaml")

# 分析文件
functions = agent.analyze_file("path/to/legacy_code.py")

# 为单个函数生成测试
report = agent.generate_tests_for_function(functions[0], output_dir="tests")

# 为整个目录生成测试
report = agent.run("path/to/legacy_project/", output_dir="tests/generated")

# 导出 JSON 报告
agent.export_report(report, "report.json")
```

## 示例

运行示例遗留代码分析：

```bash
legacy-test-agent analyze examples/sample_legacy_code.py
```

输出示例：

```
代码分析: examples/sample_legacy_code.py

calculate_order_total
├── 文件: examples/sample_legacy_code.py
├── 行数: 43-61
├── 参数: order
├── 圈复杂度: 7
├── 执行路径 (12 条)
│   ├── ✅ [1] 当 items为空时
│   ├── ❌ [2] 当 item.quantity <= 0时
│   ├── ✅ [3] 当 NOT (items为空) 且 NOT (item.quantity <= 0) 且 NOT (item.unit_price < 0) ...
│   └── ...
```

## 运行测试

```bash
pytest tests/ -v
```

## License

MIT License
