# 角色注册表契约（ROLES.md）

> 本文件是「福彩3D 自进化系统」的**机器可读契约的人话版**。任意 AI 或离线任务接入时，
> 先 `python -m workbench.roles list` / `describe --id X` 读取契约，即可驱动进化能力，
> 无需依赖任何特定对话记忆。权威真相源是 `workbench/roles.json`。

## 设计目标
把"谁来审计 / 促进 / 裁判 / 情报 / 思考"固化进项目内部，使进化能力成为**项目的属性**，
而非某个 AI 的属性。无论 AI 在线介入还是完全离线运行，系统都能表现智能进化能力。

## 三种智能（任何角色都标注其主导智能类型）
- **ai（人工智能）**：算法/统计/搜索的自动化循环。
- **human（类人智能）**：判断、怀疑精神、诚实、好奇心——人类式的认知与德性。
- **deep（深度思维）**：反思、元认知、长期记忆与自适应策略。

一个角色可同时体现多种智能（如裁判团 = human + deep）。

## 角色清单（初始 11 个）
| id | 名称 | 智能 | 写闸门 | 隔离 | 状态 |
|---|---|---|---|---|---|
| auditor | 审计团 | ai,deep | none | isolated | active |
| promoter | 促进发展团 | ai,deep | interventions | isolated | active |
| referee | 裁判团 | human,deep | none | isolated | active |
| intel | 情报组 | ai | interventions | isolated | active |
| human_principal | 人类普通用户团 | human | interventions | shared | active（固有） |
| gatekeeper | 诚实闸门守门员 | human,deep | none | isolated | active |
| replicator | 复现验证团 | ai,deep | none | isolated | active |
| archivist | 档案知识管理团 | deep | none | isolated | active |
| ideator | 设想头脑风暴团 | human,deep | interventions | isolated | active |
| bias_auditor | 偏差审计团 | human,deep | none | isolated | active |
| orchestrator | 编排调度团 | ai,deep | none | shared | active |

## 不变量（安全护栏）
1. 任何声明写引擎状态的角色，**required_gate 必须 ∈ {interventions, referee, none}**，
   禁止 `direct`。试图 `direct` 的 spec 被守门员自动拒。
2. 能力用枚举（`read_state/propose/judge/archive/orchestrate/direct/override_via_gate`），
   新枚举需宪章修订(L3)，防权限膨胀。
3. **人类普通用户团是固有角色**：始终存在，是最终消费者；其覆盖仍走高危 reject/quarantine。
4. 编排团仅为**协议/规范**，不是特权守护进程——任意 AI 按本契约即可充当一次性编排者。

## 自驱动循环（离线可跑）
`python -m workbench.selfdrive run --label <批次>` 会按以下顺序自治推进，无需人在环：
1. **checkpoint** 打点（安全网）→ 2. **预测入口**（predictive_eval 模型竞技场）→
3. **对抗入口**（debate_arena 双阵营辩论）→ 4. **进化引擎**（evolution_arena 跨运行累积）→
5. **深度反思**（写 thinking-journal，自适应下一轮策略）→ 6. 若回归则 **rollback** 还原重试。

## 按需新增角色
```
python -m workbench.roles register --spec new_role.json --approver referee --approver gatekeeper
```
新角色进入 `proposed` → 裁判团+守门员法定人数（≥2）审批 → `active` 写回 roles.json；
否则保持 proposed 待复核。这正是"任意 AI 介入后能催生新角色"的落地方式。

## 与治理层的关系
角色系统**架构在已有的 `interventions` 治理层之上**（复用非重复）。所有状态写入、
参数覆盖、因子注册、角色新增，最终都流经 interventions 的 accept/quarantine/reject。
