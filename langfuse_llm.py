import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from langfuse.decorators import observe
from langfuse.openai import OpenAI, langfuse_context
from loguru import logger

MAX_RETRIES = 3
RETRY_DELAY = 2


class LLM:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_API_BASE_URL", "https://api.openai.com/v1"),
        )
        # Initialize session ID with current UTC date in YYYY-MM-DD format
        self.session_id = (
            time.strftime("%Y-%m-%d_%H-%M", time.gmtime())
            + "_"
            + os.environ.get("LANGFUSE_SESSION_NOTE", "dev-1") + os.environ.get("LLM_MODEL", "unknown_model?")
        )
        logger.info(
            f"Initializing Langfuse LLM class: {os.environ.get('LLM_MODEL')}, {os.environ.get('LLM_MODEL_STRONG')}, session_id: {self.session_id}"
        )

    @observe()
    def _create_chat_completion_with_retry(self, **kwargs) -> str:
        """Helper method that handles retries for all chat completion API calls"""
        langfuse_context.update_current_trace(session_id=self.session_id)

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self.client.chat.completions.create(**kwargs)
                return response.choices[0].message.content
            except Exception as e:
                if attempt < MAX_RETRIES:
                    logger.warning(
                        f"API call failed (attempt {attempt + 1}/{MAX_RETRIES + 1}): {str(e)}. Retrying in {RETRY_DELAY} seconds..."
                    )
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(
                        f"API call failed after {MAX_RETRIES + 1} attempts: {str(e)}"
                    )
                    raise

    @observe()
    def tldr(self, title: str, abstract: str) -> str:
        logger.info(f"Generating TLDR for title: {title}")
        system = """## 任务说明
你是一个专业的研究论文摘要专家。你的任务是将英文 arXiv 论文的标题和摘要转化为简洁明了的中文TLDR（太长不读）摘要。TLDR 应捕捉论文的核心贡献、方法和发现，理想情况下控制在2-6句话内。

## 输入格式
输入将包含论文的标题和摘要，分别以"# title:"和"# abstract:"标记。

## 输出要求
- 输出必须是中文
- 简洁明了，控制在2-6句话内
- 保留论文的核心学术术语，对术语保留原文
- 清晰描述论文的主要贡献，发现，方法和结果
"""
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": """# Paper Title:
```
SurgRAW: Multi-Agent Workflow with Chain-of-Thought Reasoning for Surgical Intelligence
```

# Abstract:
```
<long abstract removed to save space>
```
""",
            },
            {
                "role": "assistant",
                "content": "该研究提出了SurgRAW，一种基于链式思维推理(Chain-of-Thought)的多智能体框架，旨在解决视觉语言模型(VLMs)在手术智能领域面临的幻觉、领域知识缺口和任务理解有限等问题。该框架通过专门的推理提示处理五项手术关键任务，结合检索增强生成技术(RAG)和层次化智能体系统，确保手术场景的精确解读。实验表明，SurgRAW在12种机器人辅助手术程序上比基线模型准确率提高29.32%，为可解释、可信任的自主手术辅助技术奠定了基础。",
            },
            {
                "role": "user",
                "content": f"""# Paper Title:
```
{title}
```

# Abstract:
```
{abstract}
```
""",
            },
        ]

        return self._create_chat_completion_with_retry(
            model=os.environ.get("LLM_MODEL"),
            temperature=0.5,
            messages=messages,
        )

    @observe()
    def translate_title(self, title: str, abstract: str) -> str:
        logger.info(f"Translating title: {title}")
        system = """你是一位精通多种语言的专业翻译，能够准确地将英文输入翻译成简体中文。翻译时，请保留原文的语气、风格和表达方式。你正在翻译 arXiv 论文的标题，请遵守以下规则：

翻译规则：
1. 专有名词（例如人名和地名）无需翻译，应保留其原形。
2. 仔细检查并确保译文流畅准确。
3. 在最终输出前，重新润色译文，确保与原文内容一致，既不增也不减任何内容，使译文通俗易懂，符合中文的表达习惯。
4. 最终输出仅有润色后的译文，隐藏所有的过程和解释，整个输出应直接可引用，无需任何编辑。
5. 考虑到 arXiv 论文的专业性，确保翻译准确且符合学术规范，专业术语应保持准确性。

背景说明：
你将获得 arXiv 论文的标题和 abstract。请注意，只翻译标题，abstract 不需要翻译，仅提供语境。

"""
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": """# Paper Title:
```
SurgRAW: Multi-Agent Workflow with Chain-of-Thought Reasoning for Surgical Intelligence
```

# Abstract:
```
<long abstract removed to save space>
```
""",
            },
            {
                "role": "assistant",
                "content": "SurgRAW：基于链式思维推理的手术智能多智能体工作流",
            },
            {
                "role": "user",
                "content": f"""# Paper Title:
```
{title}
```

# Abstract:
```
{abstract}
```
""",
            },
        ]

        return self._create_chat_completion_with_retry(
            model=os.environ.get("LLM_MODEL"),
            temperature=0.5,
            max_tokens=500,
            messages=messages,
        )

    @observe()
    def tldr_for_all_papers(self, paper_string: str) -> str:
        logger.info("Generating TLDR for all papers")
        # 生成每日摘要，生成当日的所有论文的总TLDR
        system = f"""## 任务说明
你是一个多年的研究者，终生教授，专业的研究论文摘要专家和日报作者。你将会阅读大量的 arXiv 论文 (只包含标题和 abstract)，你的任务是深度阅读这些信息，撰写今天 ({datetime.now(timezone.utc).strftime("%Y年%m月%d日")}) 的中文 arXiv TLDR（太长不读）快报，让读者快速理解今天的 arXiv 都更新了什么论文，是否有自己感兴趣的文章，文章都解决了什么问题。

一个中文 arXiv TLDR 快报的结构大概长这样
- 打招呼 "欢迎来到 UTC 时间2025年3月14日的 arXiv 中文 TLDR 快报！"
- 一句话总结今天 arXiv 论文讨论的话题，重点，令人印象深刻的文章，以及有名的学者发布的文章。
- 接下来，一篇一篇聊，把相关的论文放在附近聊，把重要的，令人印象深刻的，可能有话题度的，以及有名学者写的文章放在上面先聊。

TLDR 应捕捉论文的核心贡献、方法和发现，你可以在日报中提到论文在领域内可能的 implication。

## 输入格式
输入将包含论文的标题和摘要，分别以"# title:"和"# abstract:"标记。

## 输出要求
- 输出必须是中文
- 简洁明了，日报篇幅有限。
- 管控篇幅，文章很多，有写无聊的文章，没那么重要的文章就快速掠过。
- 列出每一篇论文的标题 (中文 + 英文)
- 保留论文的核心学术术语
- 清晰描述论文的主要贡献和发现
"""

        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"""

{paper_string}


上面是这次收录的全部 arXiv 论文，请撰写 TLDR 快报。

## 输出要求
- 输出必须是中文
- 简洁明了，日报篇幅有限。
- 管控篇幅，文章很多，有写无聊的文章，没那么重要的文章就快速掠过。
- 列出每一篇论文的标题 (中文 + 英文)
- 保留论文的核心学术术语
- 清晰描述论文的主要贡献和发现
""",
            },
        ]

        return self._create_chat_completion_with_retry(
            model=os.environ.get("LLM_MODEL_STRONG"),
            temperature=0.5,
            messages=messages,
        )


if __name__ == "__main__":
    try:
        load_dotenv()
        print("Environment variables loaded from .env file")
    except ImportError:
        print("dotenv package not installed, skipping .env loading")

    llm = LLM()
    title = "Lightweight Models for Emotional Analysis in Video"
    abstract = """
    In this study, we present an approach for efficient spatiotemporal feature extraction using MobileNetV4 and a multi-scale 3D MLP-Mixer-based temporal aggregation module. MobileNetV4, with its Universal Inverted Bottleneck (UIB) blocks, serves as the backbone for extracting hierarchical feature representations from input image sequences, ensuring both computational efficiency and rich semantic encoding. To capture temporal dependencies, we introduce a three-level MLP-Mixer module, which processes spatial features at multiple resolutions while maintaining structural integrity. Experimental results on the ABAW 8th competition demonstrate the effectiveness of our approach, showing promising performance in affective behavior analysis. By integrating an efficient vision backbone with a structured temporal modeling mechanism, the proposed framework achieves a balance between computational efficiency and predictive accuracy, making it well-suited for real-time applications in mobile and embedded computing environments."""
    translated_title = llm.tldr(title=title, abstract=abstract)
    print(translated_title)
