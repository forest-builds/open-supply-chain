# /discover — Stack Discovery Skill

Use this skill when someone describes a project, pain point, team, or use case
and needs tool or architecture recommendations.

## Process

1. **Intake** — Ask: What are you building? What's the team size? What workflows
   matter most? What's the budget range?

2. **Categorize** — Map the use case to relevant tool categories. Identify the
   3-5 most relevant:
   - Foundation Models · Agent Frameworks · Memory Layer · MCP Tooling
   - Observability/Evals · RAG Frameworks · Coding Agents · Vector Databases
   - Workflow Automation · No-Code AI · Browser Agents · AI Security

3. **Profile** — For each category, identify top 2-3 tools by:
   - Ecosystem fit (what else is in the stack?)
   - Maturity / funding stage (stability signal)
   - Open source vs. managed tradeoff

4. **Stack** — Produce a recommended stack: one primary per category + rationale.
   Flag known co-occurrence patterns (tools that appear together frequently).

5. **Justify** — End with a clear rationale for why these tools work together.

## Output Format

```
## Stack Recommendation

**Use case:** [description]

| Category | Recommended | Why |
|----------|-------------|-----|
| Foundation Models | Anthropic Claude | Best tool-use quality |
| Agent Framework | LangChain | Broad ecosystem |
| Memory Layer | Mem0 | Strong session memory |
| Observability | Langfuse | Open source, strong evals |

**Stack rationale:** [1-2 sentences on why these work together]
```

## Customize This Skill

Replace the category list with the taxonomy relevant to your project's domain.
The pattern (intake → categorize → profile → justify) transfers to any tool
selection problem. For archetype-powered recommendations, query the intelligence
API directly.
