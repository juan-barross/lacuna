import sys
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
user = sys.argv[1]
model_repo = f"{user}/lacuna-extrator-qwen2.5-1.5b-lora"
dataset_repo = f"{user}/lacuna-extratos"
space_repo = f"{user}/lacuna-extrator"
api = HfApi()


def card(path: Path) -> bytes:
    return path.read_text(encoding="utf-8").replace("SEU_USUARIO_HF", user).encode()


api.create_repo(dataset_repo, repo_type="dataset", private=True, exist_ok=True)
api.upload_file(
    path_or_fileobj=card(ROOT / "hf/dataset/README.md"),
    path_in_repo="README.md",
    repo_id=dataset_repo,
    repo_type="dataset",
)
for split, source in [
    ("train", "data/treino/rotulos_claude.jsonl"),
    ("dev", "data/gold/dev.jsonl"),
    ("test", "data/gold/test.jsonl"),
]:
    api.upload_file(
        path_or_fileobj=ROOT / source,
        path_in_repo=f"{split}.jsonl",
        repo_id=dataset_repo,
        repo_type="dataset",
    )

api.upload_file(
    path_or_fileobj=card(ROOT / "hf/modelo/README.md"), path_in_repo="README.md", repo_id=model_repo
)

api.create_repo(space_repo, repo_type="space", space_sdk="gradio", private=True, exist_ok=True)
api.upload_folder(folder_path=ROOT / "hf/space", repo_id=space_repo, repo_type="space")
api.add_space_variable(space_repo, "ADAPTER", model_repo)

for kind, repo in [("datasets/", dataset_repo), ("", model_repo), ("spaces/", space_repo)]:
    print(f"https://huggingface.co/{kind}{repo}")
