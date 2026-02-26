"""cad3dify — compatibility shim.

Imports public API from the new backend package layout.
Original modules remain in cad3dify/ for backward compatibility;
new code should import from backend.* directly.
"""
from backend.v1.cad_code_refiner import CadCodeRefinerChain
from backend.v1.cad_code_generator import CadCodeGeneratorChain
from backend.infra.image import ImageData
from backend.pipeline.pipeline import generate_step_from_2d_cad_image
from backend.pipeline.pipeline import generate_step_v2
