from dataclasses import dataclass
from typing import Any

CONVERGED: str = "converged"
SAME_BUDGET: str = "same_budget"

MODEL_REF: list[Any] = ["43", 0]
POSITIVE_REF: list[Any] = ["37", 0]
NEGATIVE_REF: list[Any] = ["6", 0]
LATENT_REF: list[Any] = ["50", 0]
VAE_REF: list[Any] = ["28", 0]


@dataclass(frozen=True)
class Profile:
    name: str
    subdir: str
    width: int
    height: int
    cfg: float
    pool: int
    scheduler: str
    prompts: dict[str, str]
    geometry_reference: str = CONVERGED


def anima_nodes(profile: Profile, prompt: str) -> dict[str, Any]:
    return {
        "1": {
            "class_type": "AnimaBoosterLoader",
            "inputs": {
                "model_name": "anima_aestheticV11(1).safetensors",
                "sage_attention": "auto",
                "torch_compile": False,
            },
        },
        "43": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "lora_name": "firedotinc-anima-new.safetensors",
                "strength_model": 1,
                "model": ["1", 0],
            },
        },
        "5": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "anima_baseV10_txt.safetensors",
                "type": "stable_diffusion",
                "device": "default",
            },
        },
        "37": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": f"@firedotinc, {prompt}", "clip": ["5", 0]},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "worst quality, low quality,", "clip": ["5", 0]},
        },
        "50": {
            "class_type": "AnimaLatentImage",
            "inputs": {
                "preset": "Custom",
                "width": profile.width,
                "height": profile.height,
                "batch_size": 1,
            },
        },
        "28": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "qwenImage_qwenImageVAE.safetensors"},
        },
    }


def flux3_nodes(profile: Profile, prompt: str) -> dict[str, Any]:
    return {
        "43": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "flux3Klein_klein_pruned_int8.safetensors",
                "weight_dtype": "default",
            },
        },
        "5": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "flux3Klein_klein_txt_3299383.safetensors",
                "type": "flux3",
                "device": "default",
            },
        },
        "37": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["5", 0]},
        },
        "6": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["37", 0]},
        },
        "50": {
            "class_type": "EmptyFlux2LatentImage",
            "inputs": {"width": profile.width, "height": profile.height, "batch_size": 1},
        },
        "28": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "flux2-vae.safetensors"},
        },
    }


def moss_nodes(profile: Profile, prompt: str) -> dict[str, Any]:
    return {
        "43": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "mossImage_sft_pruned_int8.safetensors",
                "weight_dtype": "default",
            },
        },
        "5": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "mossImage_sft_txt_int8.safetensors",
                "type": "moss_image",
                "device": "default",
            },
        },
        "37": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["5", 0]},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "worst quality, bad anatomy", "clip": ["5", 0]},
        },
        "50": {
            "class_type": "EmptyFlux2LatentImage",
            "inputs": {"width": profile.width, "height": profile.height, "batch_size": 1},
        },
        "28": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "flux2-vae.safetensors"},
        },
    }


ANIMA: Profile = Profile(
    name="anima",
    subdir="flow_sde",
    width=768,
    height=1024,
    cfg=5.0,
    pool=8,
    scheduler="normal",
    prompts={
        "flat": "1girl, flat color illustration, plain pastel background, simple shading",
        "face": "extreme close-up portrait of a girl's face, soft skin, detailed eyes",
        "fur": "dense forest foliage, fur texture, thousands of leaves",
        "grid": "checkerboard tiled floor, perspective grid, geometric architecture",
    },
)

FLUX3: Profile = Profile(
    name="flux3",
    subdir="flow_sde_flux3",
    geometry_reference=SAME_BUDGET,
    width=768,
    height=1024,
    cfg=1.0,
    pool=4,
    scheduler="normal",
    prompts={
        "flat": "a girl, flat color illustration, plain pastel background, simple shading",
        "face": "extreme close-up portrait of a girl's face, soft skin, detailed eyes",
        "fur": "dense forest foliage, fur texture, thousands of leaves",
        "grid": "checkerboard tiled floor, perspective grid, geometric architecture",
    },
)

MOSS: Profile = Profile(
    name="moss",
    subdir="flow_sde_moss",
    width=768,
    height=1024,
    cfg=3.0,
    pool=4,
    scheduler="normal",
    prompts=FLUX3.prompts,
)

PROFILES: dict[str, Profile] = {ANIMA.name: ANIMA, FLUX3.name: FLUX3, MOSS.name: MOSS}
NODE_BUILDERS: dict[str, Any] = {
    ANIMA.name: anima_nodes,
    FLUX3.name: flux3_nodes,
    MOSS.name: moss_nodes,
}
