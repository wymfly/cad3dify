import re
from typing import Any, Union

from langchain.chains import LLMChain, SequentialChain, TransformChain
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    PromptTemplate,
)
from langchain_core.prompts.image import ImagePromptTemplate
from loguru import logger

from ..chat_models import ChatModelParameters
from ..image import ImageData
from ..knowledge.part_types import DrawingSpec

# ---- 阶段 4a: VL 模型分析差异 ----

_COMPARE_PROMPT = """\
你是一位经验丰富的机械工程师。请对比以下两张图片：
1. 第一张是原始的 2D 工程图纸
2. 第二张是根据代码生成的 3D 模型渲染图

## 预期规格（来自图纸分析）
{drawing_spec}

## 当前代码
```python
{code}
```

## 任务
请仔细对比渲染结果与原始图纸，找出所有不一致的地方。对每个问题，给出：
1. 问题描述（什么地方不对）
2. 预期值（图纸上的尺寸）
3. 修改建议（需要怎么改代码）

输出格式：
```
问题1: [描述]
预期: [值]
修改: [建议]

问题2: [描述]
预期: [值]
修改: [建议]
```

如果渲染结果与图纸完全一致，输出 "PASS"。
"""

# ---- 阶段 4b: Coder 模型修改代码 ----

_FIX_CODE_PROMPT = """\
你是一位 CAD 程序员。以下代码生成的 3D 模型与预期不符，请根据修改指令修正代码。

## 当前代码
```python
{code}
```

## 修改指令
{fix_instructions}

## 要求
1. 只修改必要的部分，保持代码结构不变
2. 确保所有尺寸参数化
3. 保留 export 语句
4. 代码用 markdown 代码块包裹

请输出修正后的完整代码：
"""


def _parse_code(input: dict) -> dict:
    match = re.search(r"```(?:python)?\n(.*?)\n```", input["text"], re.DOTALL)
    if match:
        return {"result": match.group(1).strip()}
    return {"result": None}


def _extract_comparison(input: dict) -> dict:
    """提取对比结果"""
    text = input["text"]
    if "PASS" in text.upper() and len(text.strip()) < 20:
        return {"result": None}  # 完全匹配，无需修改
    return {"result": text}


class SmartCompareChain(SequentialChain):
    """阶段 4a: VL 模型对比原图和渲染图"""

    def __init__(self) -> None:
        prompt = ChatPromptTemplate(
            input_variables=[
                "drawing_spec", "code",
                "original_image_type", "original_image_data",
                "rendered_image_type", "rendered_image_data",
            ],
            messages=[
                HumanMessagePromptTemplate(
                    prompt=[
                        PromptTemplate(
                            input_variables=["drawing_spec", "code"],
                            template=_COMPARE_PROMPT,
                        ),
                        ImagePromptTemplate(
                            input_variables=["original_image_type", "original_image_data"],
                            template={"url": "data:image/{original_image_type};base64,{original_image_data}"},
                        ),
                        ImagePromptTemplate(
                            input_variables=["rendered_image_type", "rendered_image_data"],
                            template={"url": "data:image/{rendered_image_type};base64,{rendered_image_data}"},
                        ),
                    ]
                )
            ],
        )
        llm = ChatModelParameters.from_model_name("qwen-vl").create_chat_model()

        super().__init__(
            chains=[
                LLMChain(prompt=prompt, llm=llm),
                TransformChain(
                    input_variables=["text"],
                    output_variables=["result"],
                    transform=_extract_comparison,
                    atransform=None,
                ),
            ],
            input_variables=[
                "drawing_spec", "code",
                "original_image_type", "original_image_data",
                "rendered_image_type", "rendered_image_data",
            ],
            output_variables=["result"],
            verbose=True,
        )


class SmartFixChain(SequentialChain):
    """阶段 4b: Coder 模型根据修改指令修正代码"""

    def __init__(self) -> None:
        prompt = ChatPromptTemplate(
            input_variables=["code", "fix_instructions"],
            messages=[
                HumanMessagePromptTemplate(
                    prompt=[
                        PromptTemplate(
                            input_variables=["code", "fix_instructions"],
                            template=_FIX_CODE_PROMPT,
                        ),
                    ]
                )
            ],
        )
        llm = ChatModelParameters.from_model_name("qwen-coder").create_chat_model()

        super().__init__(
            chains=[
                LLMChain(prompt=prompt, llm=llm),
                TransformChain(
                    input_variables=["text"],
                    output_variables=["result"],
                    transform=_parse_code,
                    atransform=None,
                ),
            ],
            input_variables=["code", "fix_instructions"],
            output_variables=["result"],
            verbose=True,
        )


class SmartRefiner:
    """增强版改进器：VL 对比 + Coder 修正"""

    def __init__(self):
        self.compare_chain = SmartCompareChain()
        self.fix_chain = SmartFixChain()

    def refine(
        self,
        code: str,
        original_image: ImageData,
        rendered_image: ImageData,
        drawing_spec: DrawingSpec,
    ) -> str | None:
        """
        对比原图和渲染图，如有差异则修正代码。
        返回修正后的代码，如果 PASS 则返回 None。
        """
        # 4a: VL 对比
        comparison = self.compare_chain.invoke({
            "drawing_spec": drawing_spec.to_prompt_text(),
            "code": code,
            "original_image_type": original_image.type,
            "original_image_data": original_image.data,
            "rendered_image_type": rendered_image.type,
            "rendered_image_data": rendered_image.data,
        })["result"]

        if comparison is None:
            logger.info("Smart refiner: PASS — rendering matches drawing")
            return None

        logger.info(f"Smart refiner: found differences:\n{comparison}")

        # 4b: Coder 修正
        result = self.fix_chain.invoke({
            "code": code,
            "fix_instructions": comparison,
        })["result"]

        return result
