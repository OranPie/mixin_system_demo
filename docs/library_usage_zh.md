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
- `ci.call_original()`：仅 `INVOKE` 注入点可用。

不同注入点的回调参数：

- `HEAD` / `TAIL` / `PARAMETER`：目标函数参数/关键字参数
- `INVOKE`：被拦截调用点的参数/关键字参数
- `ATTRIBUTE`：将要写入的新值
- `CONST`：无额外位置参数（通过 context 读取）

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

## 位置约束

通过 `location=Loc(...)` 限定最终匹配节点：

- `ordinal` 与 `occurrence`（`FIRST` / `LAST` / `ALL`）
- `slice=SliceSpec(from_anchor=..., to_anchor=...)`（支持单边）
- `near=NearSpec(anchor=..., max_distance=N)`（按语句距离）
- `anchor=AnchorSpec(anchor=..., offset=..., inclusive=...)`

过滤顺序：`slice -> near -> anchor -> occurrence -> ordinal`。

## 调试方式

设置环境变量：

```bash
MIXIN_DEBUG=True
```

重写后的代码会输出到 `__pycache__/mixin_dump/`。

## 实践建议

- 将 patch 注册集中在单独模块（如 `demo_game/patches.py`）。
- 注入器尽量保持确定性与低副作用。
- 每种注入行为和 selector/location 边界都补回归测试。
- 若 patch 未生效，优先检查导入顺序：`init()` 前已导入的目标模块不会被重写。
