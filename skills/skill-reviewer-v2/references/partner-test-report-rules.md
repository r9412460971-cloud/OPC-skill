# Partner Test Report Rules

External reports are testing reports, not internal review reports.

Do not mention internal tool names, B-check IDs, blocker/warning labels, scores,
false positives, source metadata bookkeeping, internal workflow names, or AI
review stages. Include only issues that the partner needs to act on.

Tone should be equal and collaborative. Use clear next steps and avoid internal
implementation details.

Use this structure:

```markdown
# {Skill name} 测试报告

**测试时间**：YYYY-MM-DD
**测试对象**：{Skill name}
**Skill 版本**：X.Y.Z
**测试性质**：首次上架前体验测试 / 版本更新体验测试

## 一、总体情况

| 项目 | 结果 |
|------|------|
| 整体状态 | 需修复后上架（N 项必须修复，N 项建议优化） |
| 包体大小 | XX KB |

## 二、结构合规问题

### 必须修复

| 序号 | 问题 | 详情 | 修复方式 |
|------|------|------|----------|

### 建议优化

| 序号 | 问题 | 详情 | 修复方式 |
|------|------|------|----------|

## 三、功能体验反馈

| 方面 | 观察 | 建议 |
|------|------|------|

## 四、修复建议（按优先级）

### P0 - 上架前必须修复
### P1 - 建议同步优化

## 五、总结
```

Exclude platform-only source metadata gaps and confirmed placeholder credential
examples. Prefer phrases such as “建议补充”, “可以优化”, and “需修复后上架”.
