# Telethon 频道更新延迟调查（2026-11-09）

## 结论

已在 **0.1.1** 中实现：保留 Telethon 和现有 `NewMessage` 处理链，将无更新时的补取超时从默认 900 秒缩短为 60 秒，并在当前监听客户端中加载频道更新状态。版本更新见 [CHANGELOG.md](../CHANGELOG.md)。

此方案已通过离线机制验证和回归测试，测试完成后已按用户要求清理测试文件，尚未在实际 Telegram 账号上测量。调查时当前机器没有运行中的监听进程、默认 `~/.telegram-archiver/` 配置或运行日志，因此无法确认生产环境的 Telethon 版本，也不能将实际的全部延迟归因于这一机制。

0.1.1 同步更新了 skill 版本元数据、使用说明和包版本，将 Telethon 固定为已验证的 `1.45.0`，并确保监听初始化或运行异常时关闭存储、断开客户端。原候选补丁已合入源码，独立补丁文件已移除。

## 为什么它能解释分钟级延迟

Telegram 官方说明：某些频道/超级群可能停止被动推送，或只推送部分更新；正在查看频道的官方客户端会额外调用 `updates.getChannelDifference`。因此桌面客户端显示得更快，与纯推送监听并不矛盾，但需要实测确认是否属于这一情况。[官方更新协议](https://core.telegram.org/api/updates#subscribing-to-updates-of-channels-supergroups)

本次从 PyPI 安装的 Telethon **1.45.0** 中，`telethon/_updates/messagebox.py` 仍定义 `NO_UPDATES_TIMEOUT = 15 * 60`。已知更新状态的频道超时后，由更新循环发起 `GetChannelDifferenceRequest`，返回的新消息继续转换成 `UpdateNewChannelMessage`，进入原有事件处理链。[PyPI](https://pypi.org/project/Telethon/)、[上游更新状态实现](https://github.com/LonamiWebs/Telethon/blob/v1/telethon/_updates/messagebox.py)

上游 issue #4345 有相同现象，维护者确认默认补取超时是 15 分钟；2026-01 的跟帖报告将其改成 60 秒后改善。这是可行性旁证，并非本项目生产环境的测量结果。[上游 issue](https://github.com/LonamiWebs/Telethon/issues/4345)

15 分钟也不是端到端延迟上限。频道状态缺失、网络重连、服务端错误、限流等待和一次补取多个频道的耗时，都可能进一步拉长时间。

## 修复前的代码发现

| 位置 | 发现 | 含义 |
| --- | --- | --- |
| `src/telegram_archiver/listener.py:35` | 启动只调用 `get_entity()` 解析频道 | 得到频道实体不等于加载频道更新位置 `pts` |
| `src/telegram_archiver/listener.py:48` | 只注册 `NewMessage`，然后等待断线 | 没有额外的频道刷新措施 |
| `src/telegram_archiver/client.py:24` | 使用默认 `catch_up=False` | 在本次检查的 1.45.0 中，连接时不会通过 `catch_up` 分支恢复 session 中的频道更新状态 |
| `src/telegram_archiver/cli.py:179` | `channels sync` 使用另一个命令里的客户端加载 dialogs | 不能据此认定后续 `watch` 客户端内存中的频道状态已经初始化 |
| `src/telegram_archiver/client.py:30` | `timeout=15` | 它控制连接超时，不是频道更新/轮询周期 |
| `src/telegram_archiver/client.py:31` | `flood_sleep_threshold=60` | 它控制触发限流后是否自动等待，不会把正常推送延迟设为 60 秒 |
| `src/telegram_archiver/listener.py:54` | 收到事件后再 `get_chat()`，然后同步写入 | 需要区分事件到达延迟与处理/写盘延迟，当前日志无法分别测量 |
| `src/telegram_archiver/storage/parquet_backend.py` | 每频道积累 2000 条才写 part，退出时也会刷新 | 如果以 Parquet 文件可见时间判断“收到消息”，可能测到的是缓冲等待 |

`sequential_updates` 默认已经为 `False`，现有业务回调也没有主动等待几分钟的代码。因此没有依据先从切换并发开关入手。[客户端参数文档](https://docs.telethon.dev/en/stable/modules/client.html)

## 0.1.1 实现

降低补取等待的实现涉及两个位置：

1. `_watch()` 在构造和连接客户端前设置：

   ```python
   from telethon._updates import messagebox
   messagebox.NO_UPDATES_TIMEOUT = 60
   ```

2. `LiveListener.start()` 注册消息处理器后、进入 `run_until_disconnected()` 前执行一次：

   ```python
   await self.client.get_dialogs(limit=None)
   ```

第二步会同时加载订阅频道的 `pts` 和 `access_hash`。先注册处理器，可以处理加载期间到达的实时消息；这一步不会把已有历史消息逐条作为新事件重放，也不负责恢复程序离线期间的完整历史。

第一步必须放在连接前。连接后再改常量不会自动重写已经存在的 900 秒 deadline。这里使用的是内部接口，包依赖已固定为验证过的 Telethon `1.45.0`，升级时应重新核对并在临时目录执行相应验证，完成后清理测试文件。

`_watch()` 同时用 `try/finally` 保证断开连接。如果新增的 dialogs 加载失败，异常会向上传递，存储和客户端会关闭。

预期改善范围是：**对已加载状态、能够成功调用差量接口的频道，将无更新时的补取等待从 15 分钟缩短到约 1 分钟量级**。它不保证所有消息在 60 秒内到达，也不保证与桌面客户端同时显示。

该常量作用于当前进程内所有使用此模块的客户端及已知消息状态，不能只控制白名单频道。`get_dialogs(limit=None)` 也会加载账号的其他订阅频道。粗略估算，N 个均需周期补取的频道，空闲请求量约为 N/60 次每秒，另加账号级请求、分页和重试；与 900 秒相比频率约增加 15 倍。频道很多时应先确认数量，优先考虑只对少数关键频道实现独立刷新。

Telegram 官方对“正在查看的频道”短轮询另有服务端 `timeout` 和最多 10 个频道的约束。缩短 Telethon 的补取超时只是小规模试验方案，并不等价于完整实现该短轮询协议。若要长期追求秒级延迟，应按协议为有限关键频道维护刷新状态、处理分页、去重及限流。[官方协议](https://core.telegram.org/api/updates#subscribing-to-updates-of-channels-supergroups)

## 已完成的离线验证

环境：Python 3.13.7，PyPI Telethon 1.45.0；临时虚拟环境，不连接 Telegram，不读取账号凭据。使用真实 `MessageBox`、`TelegramClient.get_entity()`、`TelegramClient.get_dialogs()` 和 `NewMessage.build()`，通过虚拟时钟及固定 RPC 响应隔离网络。

| 验证 | 结果 |
| --- | --- |
| 默认 900 秒，第 61 秒检查 | 不发起频道差量请求 |
| 调成 60 秒，第 61 秒检查 | 发起频道差量请求 |
| 返回频道差量中的新消息 | 可以构造正常 `NewMessage` 事件，推进 `pts` 并设置下次 deadline |
| 只有实体/hash，没有频道 `pts` | 超时也无法发起该频道差量请求 |
| 只有频道 `pts`，缺少内存中的 hash | 无法补取，且该频道状态被移除 |
| 单独调用 `catch_up()` | 立即标记账号级补取，未直接标记已知频道补取 |
| 同一个真实客户端先 `get_entity()`、再 `get_dialogs()` | 前者不初始化频道 `pts`；后者初始化 `pts` 和内存 hash |
| 状态以 900 秒加载后再把常量改为 60 | 已有 deadline 仍为 900 秒，不能立即获得预期效果 |
| 运行真实监听器及 SQLite 后端 | 先注册处理器再加载 dialogs；加载期间到达的消息可存储，重复事件仍去重 |
| 调用实际 `_watch()`，模拟正常结束和 dialogs 加载失败 | 连接前设置 60 秒超时；正常或异常退出均关闭存储、断开客户端 |

注意：`catch_up()` 所触发的账号差量响应可能间接带来频道更新/补取信号；上述结果仅说明它不是“立即轮询所有频道”的替代品。[catch_up 实现](https://github.com/LonamiWebs/Telethon/blob/v1/telethon/client/updates.py)

0.1.1 验证覆盖周期补取、事件转换、真实 dialogs 状态初始化、加载期间接收与去重，以及监听生命周期。测试已执行通过；按用户要求，验证完成后删除了 `tests/` 及本次临时测试脚本，只保留本节的验证范围和结果。

发布前检查结果：5 项回归测试通过；skill 格式、CLI 帮助、包/skill 版本一致性检查通过；`0.1.1` wheel 已构建并核实包含两处监听修改及 `telethon==1.45.0` 依赖声明。

## 升级生效

在实际运行监听程序的 Python 环境中，从本仓库目录执行 `python -m pip install --upgrade .`，然后重启 `tg-archiver watch`。只更新仓库或文档不会改变已经安装的包和运行中的进程。

## 实际环境下一步验证

先记录实际版本、启用频道数、订阅频道总数、输出后端、是否有多个进程共用同一 session，以及重连/FloodWait 日志。

在回调入口记录 UTC 接收时间与 `message.date` 的差值；另用单调时钟记录 `get_chat()` 和写入耗时。按频道比较调整前后的 P50/P95/最大消息年龄，并核对 Telethon 的 `Got difference for channel ... updates` 日志：补取时是否成批收到旧消息，是判断这一机制是否为主要原因的直接证据。`message.date` 精度为秒，消息年龄也包含服务端到客户端的其他等待，不能直接当作精确网络时延。

如果延迟主要来自上述补取机制，先试 60 秒有价值；如果已有状态、补取正常，却仍长时间收不到，而历史查询能立即看到消息，再考虑有限关键频道的主动刷新。当前证据不足以支持立即迁移整个库，也不足以承诺缩短超时一定解决实际延迟。
