import tempfile
from string import Template

from loguru import logger

from .agents import execute_python_code
from .chat_models import MODEL_TYPE
from .image import ImageData
from .render import render_and_export_image
from .v1.cad_code_refiner import CadCodeRefinerChain
from .v1.cad_code_generator import CadCodeGeneratorChain
from .v2.drawing_analyzer import DrawingAnalyzerChain
from .v2.modeling_strategist import ModelingStrategist
from .v2.code_generator import CodeGeneratorChain
from .v2.smart_refiner import SmartRefiner

def index_map(index: int) -> str:
    if index == 0:
        return "1st"
    elif index == 1:
        return "2nd"
    elif index == 2:
        return "3rd"
    else:
        return f"{index + 1}th"


def generate_step_from_2d_cad_image(
    image_filepath: str,
    output_filepath: str,
    num_refinements: int = 3,
    model_type: MODEL_TYPE = "gpt",
):
    """Generate a STEP file from a 2D CAD image

    Args:
        image_filepath (str): Path to the 2D CAD image
        output_filepath (str): Path to the output STEP file
    """
    only_execute = (model_type == "llama")  # llamaだとagentがうまく動かない
    image_data = ImageData.load_from_file(image_filepath)
    chain = CadCodeGeneratorChain(model_type=model_type)

    result = chain.invoke(image_data)["result"]
    code = Template(result).substitute(output_filename=output_filepath)
    logger.info("1st code generation complete. Running code...")
    logger.debug("Generated 1st code:")
    logger.debug(code)
    output = execute_python_code(code, model_type=model_type, only_execute=only_execute)
    logger.debug(output)

    refiner_chain = CadCodeRefinerChain(model_type=model_type)

    for i in range(num_refinements):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            render_and_export_image(output_filepath, f.name)
            logger.info(f"Temporarily rendered image to {f.name}")
            rendered_image = ImageData.load_from_file(f.name)
            result = refiner_chain.invoke(
                {"code": code, "original_input": image_data, "rendered_result": rendered_image}
            )["result"]
            if result is None:
                logger.error(f"Refinement failed. Skipping to the next step.")
                continue
            code = Template(result).substitute(output_filename=output_filepath)
            logger.info("Refined code generation complete. Running code...")
            logger.debug(f"Generated {index_map(i)} refined code:")
            logger.debug(code)
            try:
                output = execute_python_code(code, model_type=model_type, only_execute=only_execute)
                logger.debug(output)
            except Exception as e:
                logger.error(f"Error occurred during code execution: {e}")
                continue


def generate_step_v2(
    image_filepath: str,
    output_filepath: str,
    num_refinements: int = 3,
    on_spec_ready: callable = None,
):
    """V2 增强管道：VL 读图 → 策略选择 → Coder 写码 → 智能改进

    Args:
        image_filepath: 输入图片路径
        output_filepath: 输出 STEP 文件路径
        num_refinements: 改进轮数（默认 3）
        on_spec_ready: DrawingSpec 就绪回调（可选，用于 UI 展示中间结果）
    """
    image_data = ImageData.load_from_file(image_filepath)

    # 阶段 1: VL 分析图纸
    logger.info("[V2] Stage 1: Analyzing drawing with VL model...")
    analyzer = DrawingAnalyzerChain()
    spec = analyzer.invoke(image_data)["result"]

    if spec is None:
        logger.error("[V2] Drawing analysis failed, falling back to v1 pipeline")
        return generate_step_from_2d_cad_image(
            image_filepath, output_filepath, num_refinements, model_type="qwen"
        )

    logger.info(f"[V2] Drawing spec: {spec.part_type}, dims={spec.overall_dimensions}")

    if on_spec_ready:
        on_spec_ready(spec)

    # 阶段 1.5: 选择建模策略
    logger.info("[V2] Stage 1.5: Selecting modeling strategy...")
    strategist = ModelingStrategist()
    context = strategist.select(spec)
    logger.info(f"[V2] Strategy selected for {spec.part_type}, {len(context.examples)} examples")

    # 阶段 2: Coder 生成代码
    logger.info("[V2] Stage 2: Generating CadQuery code with Coder model...")
    generator = CodeGeneratorChain()
    result = generator.invoke(context)["result"]

    if result is None:
        logger.error("[V2] Code generation failed")
        return

    code = Template(result).substitute(output_filename=output_filepath)
    logger.info("[V2] Code generation complete. Executing...")
    logger.debug(f"Generated code:\n{code}")

    # 阶段 3: 执行代码
    output = execute_python_code(code, model_type="qwen-coder", only_execute=False)
    logger.debug(output)

    # 阶段 4: 智能改进
    refiner = SmartRefiner()
    for i in range(num_refinements):
        logger.info(f"[V2] Stage 4: Smart refinement round {i+1}/{num_refinements}...")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            try:
                render_and_export_image(output_filepath, f.name)
            except Exception as e:
                logger.error(f"[V2] Rendering failed: {e}")
                continue

            rendered_image = ImageData.load_from_file(f.name)
            refined_code = refiner.refine(
                code=code,
                original_image=image_data,
                rendered_image=rendered_image,
                drawing_spec=spec,
            )

            if refined_code is None:
                logger.info(f"[V2] Refinement round {i+1}: PASS — no changes needed")
                break

            code = Template(refined_code).substitute(output_filename=output_filepath)
            logger.info(f"[V2] Refinement round {i+1}: applying fixes...")
            logger.debug(f"Refined code:\n{code}")

            try:
                output = execute_python_code(code, model_type="qwen-coder", only_execute=False)
                logger.debug(output)
            except Exception as e:
                logger.error(f"[V2] Execution failed after refinement: {e}")
                continue

    logger.info(f"[V2] Pipeline complete. Output: {output_filepath}")
