"""
Prompt for generating TLDR summaries of papers.
"""

TLDR_SYSTEM_PROMPT = ""


def build_tldr_user_prompt(title: str, abstract: str) -> str:
    return f"""## 任务说明
你是一个专业的研究论文摘要专家。你的任务是将英文 arXiv 论文的标题和摘要转化为简洁明了的中文TLDR（太长不读）摘要。TLDR 应捕捉论文的核心贡献、方法和发现，理想情况下控制在4-8句话内。

## 输入格式
输入将包含论文的标题和摘要，分别以"# title:"和"# abstract:"标记。

## 输出要求
- 输出必须是中文
- 简洁明了，控制在4-8句话内，单个段落。
- 保留论文的核心学术术语，对术语保留原文
- 清晰描述论文的主要贡献，发现，方法和结果
- 不要自我介绍
- 不要反问用户或寻求与用户的交互，你的回答应该只包含必须的部分，**绝不能**包含类似 "希望这个摘要对您的研究有所帮助！", "如果您还有xxx，请随时告诉我。", "我可以帮你...", "您是否需要我...", "如果你需要xxx, ，请随时告诉我" 等话术。
- 不要包含任何与论文无关的信息
- 不要在回答中使用分割线, 标题, 列表等格式化手段。我们只要单个自然段 (不分段) 的内容。

<示例输入>
# Paper Title:
```
SurgRAW: Multi-Agent Workflow with Chain-of-Thought Reasoning for Surgical Intelligence
```

# Abstract:
```
<long abstract removed to save space>
```
</示例输入>

<示例输出>
该研究提出了SurgRAW，一种基于链式思维推理(Chain-of-Thought)的多智能体框架，旨在解决视觉语言模型(VLMs)在手术智能领域面临的幻觉、领域知识缺口和任务理解有限等问题。该框架通过专门的推理提示处理五项手术关键任务，结合检索增强生成技术(RAG)和层次化智能体系统，确保手术场景的精确解读。实验表明，SurgRAW在12种机器人辅助手术程序上比基线模型准确率提高29.32%，为可解释、可信任的自主手术辅助技术奠定了基础。
</示例输出>

现在轮到你了！请根据以下论文标题和摘要生成中文TLDR摘要。

# 实际材料
<PaperTitle>
{title}
</PaperTitle>

<Abstract>
{abstract}
</Abstract>

"""
