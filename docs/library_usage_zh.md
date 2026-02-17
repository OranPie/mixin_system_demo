# 库使用指南（中文）

本文档介绍如何使用 `mixin_system` 在 **导入阶段** 通过 AST 重写为 Python 类注入行为。

## 库的核心能力

`mixin_system` 会安装一个 `meta_path` 导入钩子。模块首次导入时，系统会匹配目标类方法并织入注入器回调。

支持的注入点：

- `HEAD`：函数入口
- `TAIL`：所有显式 `return` + 隐式结尾返回
- `PARAMETER`：函数入口参数拦截/修改
- `CONST`：常量值（`ast.Constant`）拦截/替换
- `INVOKE`：调用点拦截
- `ATTRIBUTE`：属性写入拦截（如 `self.health = value`）

## 生命周期（非常重要）

1. 定义 mixin 类与注入器方法。
2. 导入注册这些 mixin 的模块。
3. 调用 `mixin_system.init()`。
4. 再导入并使用目标模块/目标类。

`init()` 会冻结注册表；若在此之后再注册 mixin，会抛出错误。

`init(debug=True)` 等价于先设置 `MIXIN_DEBUG=True` 再初始化。

## 最小示例

```python
import mixin_system
from mixin_system import mixin, inject, At, TYPE, Loc, When, OP

@mixin(target="my_game.player.Player")
class PlayerPatch:
    @inject(
        method="set_health",
        at=At(type=TYPE.PARAMETER, name="value", location=Loc(condition=When("value", OP.LT, 0))),
    )
    def clamp_health(self, ci, value, *args, **kwargs):
        ci.set_value(0)

mixin_system.init()

from my_game.player import Player
```

## 核心 API

### `@mixin(target="pkg.mod.Class")`
将补丁类注册到目标类（完整路径）。

也支持直接传类对象：

```python
@mixin(target=Player)
class PlayerPatch:
    ...
```

### `@inject(method=..., at=..., priority=..., require=..., expect=...)`
- `method`：目标类的方法名。
- `at`：`At(...)` 描述注入点与匹配方式。
- `priority`：越小越先执行。
- `require`：严格匹配数量；不满足会抛 `MixinMatchError`。
- `expect`：调试模式（`MIXIN_DEBUG=True`）下的期望匹配数提示。

`policy` 在当前 demo 实现中仍是占位参数。

## 选项矩阵（选择 -> 效果）

### 目标与初始化选项

| 选择 | 效果 |
| --- | --- |
| `@mixin(target="pkg.mod.Class")` | 直接使用字符串路径；适合补丁模块与目标模块分离的场景。 |
| `@mixin(target=SomeClass)` | 自动解析为 `module.qualname`，可减少目标路径拼写错误。 |
| `init(debug=True)` | 开启 AST 重写结果输出（`__pycache__/mixin_dump/*.py`）。 |
| `init(debug=False)` 或默认 | 不输出 AST dump。 |

### `inject(...)` 关键参数选项

| 字段 | 可选值 | 效果 |
| --- | --- | --- |
| `priority` | int（默认 `100`） | 在同一注入键 `(target, method, type, at_name)` 内，值越小越先执行。 |
| `require` | `None` 或 int | 若实际匹配数不等于该值，抛 `MixinMatchError` 并中止转换。 |
| `expect` | `None` 或 int | 若 debug 开启且不匹配，仅打印告警，不中止。 |
| `policy` | string | 当前 demo 版本中为占位参数，不改变运行时行为。 |

### `TYPE` 行为选项

| `TYPE` | 执行位置 | `cancel(...)` 效果 | `set_value(...)` 效果 |
| --- | --- | --- | --- |
| `HEAD` | 函数入口 | 立即返回指定结果。 | 当前运行时中无直接效果。 |
| `TAIL` | 显式/隐式返回点 | 覆盖返回值。 | 当前运行时中无直接效果。 |
| `PARAMETER` | 入口参数处理阶段 | 立即返回指定结果。 | 在函数体执行前重绑目标参数。 |
| `CONST` | 常量表达式位置 | 用取消结果替换表达式值。 | 替换常量值。 |
| `INVOKE` | 调用点 | 替换调用返回值。 | 当前无直接效果；应使用调用参数 API。 |
| `ATTRIBUTE` | 属性赋值写入路径 | 取消结果作为最终写入值。 | 改写最终写入值。 |

## 易用性辅助 API（推荐）

`At` 构建器：

- `at_head()` / `at_tail()`
- `at_parameter("value")`
- `at_const(1.0)`
- `at_invoke("self.call", selector=...)`
- `at_attribute("self.health")`

快捷装饰器：

- `@inject_head(method="...")`
- `@inject_tail(method="...")`
- `@inject_parameter(method="...", name="...")`
- `@inject_const(method="...", value=...)`
- `@inject_invoke(method="...", name="...", selector=...)`
- `@inject_attribute(method="...", name="...")`

## 回调与 `CallbackInfo`

常用能力：

- `ci.cancel(result=...)`：取消后续流程并返回结果。
- `ci.set_value(...)`：替换当前值（适用于支持变更的注入点）。
- `ci.get_context()`：获取标准化运行时上下文。
- `ci.call_original(*args, **kwargs)`：调用原始函数（仅 `INVOKE`），可传覆盖后的参数。
- `ci.get_call_args()` / `ci.set_call_args(*args, **kwargs)`：读取或改写 `INVOKE` 的调用参数。
- `ci.parameter_name`、`ci.get_parameter()`、`ci.set_parameter(...)`：`PARAMETER` 注入器更易用的参数辅助接口。

若注入器内部已经调用 `ci.call_original(...)`，运行时会复用该结果，不会再次重复调用原函数。

不同注入点的回调参数：

- `HEAD` / `TAIL` / `PARAMETER`：目标函数参数/关键字参数
- `INVOKE`：被拦截调用点的参数/关键字参数
- `ATTRIBUTE`：将要写入的新值
- `CONST`：无额外位置参数（通过 context 读取）

### INVOKE 调用控制选项

| 选择 | 效果 |
| --- | --- |
| `ci.get_call_args()` | 读取当前将用于原始调用的 `(args, kwargs)`。 |
| `ci.set_call_args(*args, **kwargs)` | 更新调用参数；后续注入器与最终原始调用都会看到新参数。 |
| `ci.call_original()` | 使用当前调用参数执行原函数。 |
| `ci.call_original(*args, **kwargs)` | 先覆盖调用参数，再立即执行原函数。 |
| 注入器内已调用 `call_original(...)` 且未取消 | 运行时复用该次调用结果，不会重复再调一次原函数。 |

## 条件表达式（`When` + `OP`）

可通过 `Loc(condition=When(...))` 增加运行时条件。

示例：

```python
Loc(condition=When("kwargs.scale", OP.EQ, 7))
```

路径支持点号访问与索引访问（如 `"args[0]"`）。

## `INVOKE` 选择器

`CallSelector` 支持结构化匹配：

- 函数目标：`func=QualifiedSelector.of("self", "physics2")`
- 位置参数模式：`ArgAny` / `ArgConst` / `ArgName` / `ArgAttr`
- 关键字参数模式：`KwPattern.subset(...)` / `KwPattern.exact(...)`
- 未解析 `**kwargs` 策略 `starstar_policy`：
  - `FAIL`（默认）
  - `IGNORE`
  - `ASSUME_MATCH`

### 选择器模式矩阵

| 选项 | 可选值 | 效果 |
| --- | --- | --- |
| `args_mode` | `PREFIX`（默认） | 调用可包含额外位置参数，前缀匹配即可。 |
| `args_mode` | `EXACT` | 调用位置参数数量必须与模式数量完全一致。 |
| `KwPattern.mode` | `SUBSET` | 关键字模式要求的键必须存在并匹配（除非 ASSUME_MATCH + 未解析 `**kwargs`）。 |
| `KwPattern.mode` | `EXACT` | 已知 kwargs 的键集合必须与模式键集合一致。 |
| `starstar_policy` | `FAIL` | 存在未解析 `**expr` 时直接不匹配。 |
| `starstar_policy` | `IGNORE` | 允许未解析 `**expr`，但它不能补足缺失必需键。 |
| `starstar_policy` | `ASSUME_MATCH` | 对 `SUBSET`：存在未解析 `**expr` 时可假定缺失键被满足；对 `EXACT` 行为与 `IGNORE` 一致。 |

## 位置约束

通过 `location=Loc(...)` 限定最终匹配节点：

- `ordinal` 与 `occurrence`（`FIRST` / `LAST` / `ALL`）
- `slice=SliceSpec(from_anchor=..., to_anchor=...)`（支持单边）
- `near=NearSpec(anchor=..., max_distance=N)`（按语句距离）
- `anchor=AnchorSpec(anchor=..., offset=..., inclusive=...)`

过滤顺序：`slice -> near -> anchor -> occurrence -> ordinal`。

### 位置选项矩阵

| 选项 | 可选值 | 效果 |
| --- | --- | --- |
| `occurrence` | `ALL`（默认） | 保留前序过滤后的全部匹配。 |
| `occurrence` | `FIRST` | 仅保留排序后的第一个匹配。 |
| `occurrence` | `LAST` | 仅保留排序后的最后一个匹配。 |
| `ordinal` | `None` 或 int | 在 occurrence 之后按 0-based 下标选单个匹配。 |
| `slice.from_anchor` / `slice.to_anchor` | `At` 或 `None` | 支持单边区间（只设起点或只设终点）。 |
| `slice.include_from` / `slice.include_to` | bool | 控制是否包含边界锚点。 |
| `near.max_distance` | int | 相对锚点语句的最大语句距离。 |
| `anchor.offset` | `>=0` 或 `<0` | 正数向后选取，负数向前选取。 |
| `anchor.inclusive` | bool | 相对选择时是否包含锚点本身。 |

## 调试方式

设置环境变量：

```bash
MIXIN_DEBUG=True
```

重写后的代码会输出到 `__pycache__/mixin_dump/`。

## 错误模型与运行时说明

- `MixinMatchError`：在转换阶段，`require` 与实际匹配数不一致时抛出。
- `RuntimeError`（注册表冻结）：`init()` 后继续注册 mixin/injector 会失败。
- `RuntimeError`（调用 API 使用错误）：在非 `INVOKE` 注入点使用 `call_original`/`set_call_args` 会报错。
- `TypeError`（`merge_kwargs`）：显式 kwargs 与 `**kwargs` 合并时出现重复键。
- 导入钩子会优先从源码重新编译，以确保 AST 注入逻辑更新后不被旧 `.pyc` 行为“粘住”。

## 实践建议

- 将 patch 注册集中在单独模块（如 `demo_game/patches.py`）。
- 注入器尽量保持确定性与低副作用。
- 每种注入行为和 selector/location 边界都补回归测试。
- 若 patch 未生效，优先检查导入顺序：`init()` 前已导入的目标模块不会被重写。
